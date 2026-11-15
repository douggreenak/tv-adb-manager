"""End-to-end: the real Monitor driving tools/fake_adb.py (a simulated TV fleet). No hardware."""
import os
import subprocess
import sys
import tempfile
import time
import unittest

from tvmanager.adb import Adb
from tvmanager.monitor import Monitor
from tvmanager.store import EventLog, Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE = os.path.join(ROOT, "tools", "fake_adb.py")
HW = "com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/"
A = "10.0.0.11:5555"   # Hisense A11, labelled inputs
UNAUTH, DEAD = "10.0.0.14:5555", "10.0.0.15:5555"


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["FAKE_ADB_STATE"] = os.path.join(self.tmp.name, "fleet.json")
        self.adb = Adb(FAKE)
        self.ctl("seed")
        self.store = Store(os.path.join(self.tmp.name, "data"))
        self.events = EventLog()
        self.mon = Monitor(self.adb, self.store, self.events)
        self.ids = {a: self.store.add_device(a, a)["id"] for a in (A, UNAUTH, DEAD, "10.0.0.13:5555")}

    def tearDown(self):
        self.tmp.cleanup()

    def ctl(self, *a):
        return subprocess.run([sys.executable, FAKE, "ctl", *a], capture_output=True, text=True, check=True).stdout

    def poll(self, settle=False):
        """One monitor round for every device (synchronously)."""
        states = self.adb.devices()
        for d in self.store.devices():
            self.mon.cycle(d, states.get(d["addr"]))
        if settle:  # skip the post-wake settle delay
            for st in self.mon.states.values():
                if st.get("wake_at"):
                    st["wake_at"] = time.time() - 1
            for d in self.store.devices():
                self.mon.cycle(d, self.adb.devices().get(d["addr"]))

    def snap(self, addr):
        return self.mon.snapshot(self.ids[addr])

    def top(self, addr):
        return [l for l in self.ctl("list").splitlines() if l.startswith(addr)][0]

    def test_statuses_across_fleet(self):
        self.adb.connect(A); self.adb.connect(UNAUTH)
        self.poll()
        self.assertEqual(self.snap(A)["status"], "online")
        self.assertEqual(self.snap(A)["model"], "SmartTV 4K")
        self.assertEqual(self.snap(UNAUTH)["status"], "unauthorized")
        self.assertEqual(self.snap(DEAD)["status"], "offline")
        self.ctl("approve", UNAUTH)
        self.poll()
        self.assertEqual(self.snap(UNAUTH)["status"], "online")

    def test_remembers_input_and_restores_after_standby(self):
        self.adb.connect(A); self.poll()
        self.ctl("input", A, HW + "HW2"); self.poll()
        self.assertEqual(self.store.device(self.ids[A])["restore"]["last"], HW + "HW2")
        self.assertEqual(self.snap(A)["labels"][HW + "HW2"], "Soundbar")
        self.ctl("standby", A); self.poll()
        self.assertEqual(self.snap(A)["status"], "asleep")
        self.ctl("wake", A)                                    # wakes onto the launcher, session gone
        self.assertIn("ltvL", self.top(A))
        self.poll(settle=True)
        self.assertIn("HW2", self.top(A))                      # put back on its input
        self.assertTrue(any("restored input" in e["msg"] for e in self.events.list()))

    def test_power_loss_cold_boot_restores(self):
        self.adb.connect(A); self.poll()
        self.ctl("input", A, HW + "HW3"); self.poll()
        self.ctl("power", A, "off"); self.poll()
        self.assertEqual(self.snap(A)["status"], "offline")
        self.ctl("power", A, "on"); self.adb.connect(A)       # TV boots to the launcher
        self.poll(settle=True)
        self.assertIn("HW3", self.top(A))

    def test_reboot_via_adb_then_restore(self):
        self.adb.connect(A); self.poll()
        self.ctl("input", A, HW + "HW1"); self.poll()
        self.adb.reboot(A)
        self.poll()
        self.assertEqual(self.snap(A)["status"], "offline")
        self.ctl("set", A, 'up_at=%s' % (time.time() - 1))     # reboot finished
        self.adb.connect(A); self.poll(settle=True)
        self.assertIn("HW1", self.top(A))

    def test_does_not_override_user_choice(self):
        self.adb.connect(A); self.poll()
        self.ctl("input", A, HW + "HW2"); self.poll()
        self.ctl("standby", A); self.poll()
        self.ctl("wake", A)
        self.ctl("set", A, 'top="com.netflix.ninja/.MainActivity"')   # user opened Netflix first
        self.poll(settle=True)
        self.assertIn("netflix", self.top(A))

    def test_package_and_shell_commands(self):
        self.adb.connect(A)
        sh = lambda c: self.adb.shell(A, c)[1]
        self.assertIn("com.google.android.tvlauncher", sh("pm list packages -d"))
        sh("pm disable-user --user 0 com.netflix.ninja")
        self.assertIn("com.netflix.ninja", sh("pm list packages -d"))
        sh("pm enable --user 0 com.netflix.ninja")
        self.assertNotIn("com.netflix.ninja", sh("pm list packages -d"))
        self.assertIn("Success", sh("pm uninstall --user 0 com.netflix.ninja"))
        self.assertNotIn("com.netflix.ninja", sh("pm list packages -3"))


if __name__ == "__main__":
    unittest.main()
