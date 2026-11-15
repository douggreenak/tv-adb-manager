import tempfile
import time
import unittest

from tests.fakes import FakeAdb
from tvmanager.monitor import Monitor, WAKE_SETTLE
from tvmanager.store import EventLog, Store

HDMI = "com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/HW5"
LAUNCHER = "    mResumedActivity: ActivityRecord{1 u0 com.leanbitlab.ltvL/.MainActivity t1}"
LIVETV = "    mResumedActivity: ActivityRecord{2 u0 com.mediatek.wwtv.tvcenter/.LiveTVMainActivity t2}"


def probe(awake, input_id=None, top=LAUNCHER):
    return "  mWakefulness=%s\n==\n%s\n==\n%s\n" % ("Awake" if awake else "Asleep",
                                                    ("      inputId: " + input_id) if input_id else "", top)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.events = EventLog()
        self.adb = FakeAdb()
        self.adb.responses.append(("getprop ro.product.manufacturer", "Hisense\n==\nSmartTV\n==\n11\n==\nnull\n==\ncom.leanbitlab.ltvL/.MainActivity\n"))
        self.dev = self.store.add_device("Lobby", "10.0.0.5")
        self.mon = Monitor(self.adb, self.store, self.events)
        self.cur = {"v": probe(True, HDMI, LIVETV)}
        self.adb.responses.append(("mWakefulness", lambda: self.cur["v"]))

    def tearDown(self):
        self.tmp.cleanup()

    def cycle(self, state="device"):
        self.mon.cycle(self.store.device(self.dev["id"]), state)

    def launches(self):
        return [c for c in self.adb.shells() if "passthrough" in c]

    def test_records_input_and_status(self):
        self.cycle()
        snap = self.mon.snapshot(self.dev["id"])
        self.assertEqual(snap["status"], "online")
        self.assertEqual(snap["model"], "SmartTV")
        self.assertEqual(self.store.device(self.dev["id"])["restore"]["last"], HDMI)

    def test_wake_restores_last_input_when_on_launcher(self):
        self.cycle()
        self.cur["v"] = probe(False)
        self.cycle()
        self.assertEqual(self.mon.snapshot(self.dev["id"])["status"], "asleep")
        self.cur["v"] = probe(True)           # woke onto the launcher
        self.cycle()
        self.assertEqual(self.launches(), [])  # settle delay not elapsed yet
        self.mon.states[self.dev["id"]]["wake_at"] = time.time() - 1
        self.cycle()
        self.assertEqual(len(self.launches()), 1)
        self.assertIn("HW5", self.launches()[0].replace("%2F", "/"))

    def test_no_restore_if_tv_woke_on_input_or_other_app(self):
        self.cycle()
        self.cur["v"] = probe(False); self.cycle()
        self.cur["v"] = probe(True, HDMI, LIVETV); self.cycle()
        self.mon.states[self.dev["id"]]["wake_at"] = time.time() - 1
        self.cycle()
        self.assertEqual(self.launches(), [])
        self.cur["v"] = probe(False); self.cycle()
        self.cur["v"] = probe(True, None, "    mResumedActivity: ActivityRecord{3 u0 com.netflix.ninja/.Main t3}"); self.cycle()
        self.mon.states[self.dev["id"]]["wake_at"] = time.time() - 1
        self.cycle()
        self.assertEqual(self.launches(), [])

    def test_disabled_restore_and_cold_boot(self):
        self.cycle()
        self.store.update_device(self.dev["id"], restore={"enabled": False, "last": HDMI})
        self.cycle("offline")
        self.cur["v"] = probe(True)
        self.cycle()
        self.mon.states[self.dev["id"]]["wake_at"] = time.time() - 1
        self.cycle()
        self.assertEqual(self.launches(), [])
        self.store.update_device(self.dev["id"], restore={"enabled": True, "last": HDMI})
        self.cycle("offline"); self.cycle()   # reconnect after power loss
        self.mon.states[self.dev["id"]]["wake_at"] = time.time() - 1
        self.cycle()
        self.assertEqual(len(self.launches()), 1)

    def test_unauthorized_and_offline_status(self):
        self.cycle("unauthorized")
        self.assertEqual(self.mon.snapshot(self.dev["id"])["status"], "unauthorized")
        self.cycle(None)
        self.assertEqual(self.mon.snapshot(self.dev["id"])["status"], "offline")

    def test_first_sight_never_restores(self):
        self.cur["v"] = probe(True)
        self.store.update_device(self.dev["id"], restore={"enabled": True, "last": HDMI})
        self.cycle()
        self.assertIsNone(self.mon.snapshot(self.dev["id"])["wake_at"])
        self.assertEqual(self.launches(), [])


if __name__ == "__main__":
    unittest.main()
