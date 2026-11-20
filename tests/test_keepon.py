"""Keep-on: read the TV's timers, change only what differs, remember originals, restore on request."""
import tempfile
import unittest

from tests.fakes import FakeAdb
from tvmanager import keepon
from tvmanager.monitor import Monitor
from tvmanager.store import EventLog, Store

HISENSE = "secure.sleep_timeout=28800000\nsystem.screen_off_timeout=600000\nglobal.stay_on_while_plugged_in=0\nglobal.no_signal_auto_power_off=null\n"
TCL = "secure.sleep_timeout=86400000\nsystem.screen_off_timeout=300000\nglobal.stay_on_while_plugged_in=0\nglobal.no_signal_auto_power_off=3\n"


class KeepOnTests(unittest.TestCase):
    def test_plan(self):
        keys = [(t, k) for t, k, _ in keepon.plan(keepon.parse(HISENSE))]
        self.assertEqual(keys, [("secure", "sleep_timeout"), ("system", "screen_off_timeout"), ("global", "stay_on_while_plugged_in")])
        self.assertIn(("global", "no_signal_auto_power_off", "0"), keepon.plan(keepon.parse(TCL)))     # only where it exists
        done = HISENSE.replace("28800000", keepon.NEVER).replace("600000", keepon.NEVER).replace("plugged_in=0", "plugged_in=7")
        self.assertEqual(keepon.plan(keepon.parse(done)), [])

    def test_revert_cmd(self):
        self.assertEqual(keepon.revert_cmd({"secure.sleep_timeout": "28800000", "global.no_signal_auto_power_off": None}),
                         "settings put secure sleep_timeout 28800000; settings delete global no_signal_auto_power_off")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.adb, self.ev = Store(self.tmp.name), FakeAdb(), EventLog()
        self.mon = Monitor(self.adb, self.store, self.ev)
        self.dev = self.store.add_device("TV", "10.0.0.5")

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_remember_and_revert(self):
        self.adb.responses[:] = [("echo secure.sleep_timeout", TCL), ("settings put", "")]
        st = self.mon._st(self.dev["id"])
        self.mon.keep_on(self.store.device(self.dev["id"]), st)
        put = [c[2] for c in self.adb.calls if "settings put" in c[-1]][0]
        self.assertIn("settings put secure sleep_timeout 2147483647", put)
        self.assertIn("settings put global no_signal_auto_power_off 0", put)
        self.assertEqual(self.store.device(self.dev["id"])["keep_on_prev"]["secure.sleep_timeout"], "86400000")
        self.assertTrue(any("keep-on:" in e["msg"] for e in self.ev.list()))
        n = len(self.adb.calls)
        self.mon.keep_on(self.store.device(self.dev["id"]), st)               # rechecked only every 10 minutes
        self.assertEqual(len(self.adb.calls), n)
        ok, _ = self.mon.revert_keep_on(self.store.device(self.dev["id"]))
        self.assertTrue(ok)
        self.assertIn("settings put secure sleep_timeout 86400000", self.adb.calls[-1][2])
        self.assertEqual(self.store.device(self.dev["id"])["keep_on_prev"], {})

    def test_disabled_per_tv(self):
        self.store.update_device(self.dev["id"], keep_on=False)
        self.mon.keep_on(self.store.device(self.dev["id"]), self.mon._st(self.dev["id"]))
        self.assertEqual(self.adb.calls, [])


if __name__ == "__main__":
    unittest.main()
