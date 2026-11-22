import os
import tempfile
import unittest

from tests.fakes import FakeAdb
from tvmanager import firetv
from tvmanager.server import App, ApiError

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


class FakeTV(firetv.FireTV):
    def __init__(self, pin="1234"):
        self.calls, self.pin, self.shown = [], pin, False
        super().__init__(https=self._https, plain_post=lambda url, timeout=5: 201)

    def _https(self, method, url, headers, body=None, timeout=8):
        self.calls.append((method, url.split(":8080")[1], headers.get("X-Client-Token"), body))
        if url.endswith("/pin/display"):
            self.shown = True
            return 200, {"description": "OK"}
        if url.endswith("/pin/verify"):
            return (200, {"description": "TOKEN1"}) if body["pin"] == self.pin and self.shown else (400, {"description": "bad pin"})
        if headers.get("X-Client-Token") != "TOKEN1":
            return 401, {"description": "Unauthorized"}
        if url.endswith("action=wake"):                       # not a real action
            return 400, {"description": "Bad arguments supplied."}
        return 200, {"description": "OK"}


class FireTVTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tv = FakeTV()
        self.app = App(self.tmp.name, WEB, adb=FakeAdb(), env_password="x", start_threads=False, firetv=self.tv)
        self.dev = self.app.store.add_device("Fire", "10.0.0.9", "", "firetv")

    def tearDown(self):
        self.tmp.cleanup()

    def test_added_as_unpaired_firetv_on_remote_service_port(self):
        self.assertEqual(self.dev["addr"], "10.0.0.9:8009")
        v = self.app.device_view(self.dev)
        self.assertEqual((v["kind"], v["paired"]), ("firetv", False))
        self.assertNotIn("token", v)

    def test_commands_refused_until_paired(self):
        ok, out = self.app.run_action(self.dev, "wake")
        self.assertFalse(ok)
        self.assertIn("not paired", out)

    def test_pin_flow_stores_token(self):
        ok, _ = self.tv.show_pin("10.0.0.9")
        self.assertTrue(ok)
        self.assertEqual(self.tv.verify_pin("10.0.0.9", "0000"), (False, "bad pin"))
        self.assertFalse(self.tv.verify_pin("10.0.0.9", "12")[0])
        ok, tok = self.tv.verify_pin("10.0.0.9", "1234")
        self.assertEqual((ok, tok), (True, "TOKEN1"))

    def paired(self):
        return self.app.store.update_device(self.dev["id"], token="TOKEN1")

    def test_wake_and_sleep_map_to_firetv_actions_and_track_state(self):
        dev = self.paired()
        st = self.app.monitor._st(dev["id"])
        st["status"] = "online"
        self.assertTrue(self.app.run_action(dev, "sleep")[0])
        self.assertEqual(self.tv.calls[-1][1], "/v1/FireTV?action=sleep")
        self.assertEqual(self.app.monitor.snapshot(dev["id"])["status"], "online")      # never shown as asleep
        self.assertTrue(self.app.run_action(dev, "wake")[0])
        self.assertEqual(self.tv.calls[-1][1], "/v1/FireTV?action=wakeup")
        self.assertEqual(self.app.monitor.snapshot(dev["id"])["status"], "online")

    def test_remote_keys_and_unsupported_actions(self):
        dev = self.paired()
        self.assertTrue(self.app.key(dev, "KEYCODE_DPAD_UP")[0])
        self.assertEqual(self.tv.calls[-1][1], "/v1/FireTV?action=dpad_up")
        self.assertTrue(self.app.key(dev, "KEYCODE_MEDIA_PLAY_PAUSE")[0])
        self.assertEqual(self.tv.calls[-1][1], "/v1/media?action=play")
        self.assertFalse(self.app.key(dev, "KEYCODE_VOLUME_UP")[0])
        self.assertFalse(self.app.run_action(dev, "reboot")[0])

    def test_rejected_token_says_to_pair_again(self):
        dev = self.app.store.update_device(self.dev["id"], token="OLD")
        ok, out = self.app.key(dev, "KEYCODE_HOME")
        self.assertFalse(ok)
        self.assertIn("Pair this Fire TV again", out)

    def test_no_adb_pages(self):
        with self.assertRaises(ApiError):
            self.app.require_adb_device(self.dev["id"])

    def test_status_follows_network_and_pairing(self):
        import tvmanager.monitor as M
        mon, dev = self.app.monitor, self.dev
        st = mon._st(dev["id"])
        mon.firetv_cycle(dev, st, 1.0)
        self.assertEqual(st["status"], "unauthorized")
        dev = self.paired()
        orig = M.net_probe
        try:
            M.net_probe = lambda addr, timeout=2.0: True
            mon.firetv_cycle(dev, st, 2.0)
            self.assertEqual(st["status"], "online")
            M.net_probe = lambda addr, timeout=2.0: False
            mon.firetv_cycle(dev, st, 3.0)
            self.assertEqual(st["status"], "offline")
        finally:
            M.net_probe = orig

    def test_schedule_always_sends_the_wake_once(self):
        from tvmanager.scheduler import Scheduler
        dev = self.paired()
        self.app.monitor._st(dev["id"])["status"] = "online"          # looks on, but a Fire TV can't say
        sent = []
        sch = Scheduler(self.app.store, self.app.events, lambda d, a, args=None: (sent.append(a) or True, "ok"),
                        get_status=lambda d: "online")
        sch.pending[dev["id"]] = {"label": "t", "until": 10 ** 12, "next": 0, "tries": 0}
        sch._service_pending(1.0)
        self.assertEqual(sent, ["wake"])
        sch._service_pending(2.0)
        self.assertNotIn(dev["id"], sch.pending)


if __name__ == "__main__":
    unittest.main()


class RetryTests(unittest.TestCase):
    def test_refused_connection_starts_service_waits_and_retries(self):
        seen, started = [], []

        def https(method, url, headers, body=None, timeout=8):
            seen.append(1)
            if len(seen) < 3:
                raise ConnectionRefusedError()
            return 200, {"description": "OK"}
        tv = firetv.FireTV(https=https, plain_post=lambda url, timeout=5: started.append(url) or 201)
        naps = []
        st, body = tv._call("h", "POST", "/x", "T", sleep=naps.append)
        self.assertEqual((st, len(started), len(naps)), (200, 2, 2))

    def test_gives_up_without_raising(self):
        tv = firetv.FireTV(https=lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()), plain_post=lambda u, timeout=5: 201)
        st, body = tv._call("h", "POST", "/x", "T", sleep=lambda s: None)
        self.assertEqual(st, 0)
        self.assertFalse(tv.press("h", "T", "KEYCODE_HOME")[0])
