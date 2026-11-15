"""Device names: follow the TV's own name unless the user chose one."""
import json
import os
import tempfile
import unittest

from tests.fakes import FakeAdb
from tvmanager.monitor import Monitor, display_name
from tvmanager.store import EventLog, Store

PROBE_OK = "  mWakefulness=Awake\n==\n\n==\n"


def static(tv_name, model="SmartTV 4K"):
    return "Hisense\n==\n%s\n==\n11\n==\nnull\n==\ncom.leanbitlab.ltvL/.MainActivity\n==\n%s\n" % (model, tv_name)


class NameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.events = EventLog()
        self.adb = FakeAdb()
        self.mon = Monitor(self.adb, self.store, self.events)
        self.tv = {}      # addr -> name the fake TV reports

    def tearDown(self):
        self.tmp.cleanup()

    def poll(self, dev):
        self.adb.responses[:] = [("getprop ro.product.manufacturer", lambda: static(self.tv[dev["addr"]])), ("mWakefulness", PROBE_OK)]
        d = self.store.device(dev["id"])
        self.mon.states.pop(dev["id"], None)          # a fresh connection: static info is read again
        self.mon.cycle(d, "device")
        return self.store.device(dev["id"])

    def test_blank_name_follows_the_tv(self):
        d = self.store.add_device("", "10.0.0.5")
        self.assertEqual((d["name"], d["auto_name"]), ("10.0.0.5:5555", True))
        self.tv["10.0.0.5:5555"] = "Front Desk"
        self.assertEqual(self.poll(d)["name"], "Front Desk")
        self.tv["10.0.0.5:5555"] = "Lobby TV"                      # renamed on the TV later
        self.assertEqual(self.poll(d)["name"], "Lobby TV")
        self.assertTrue(any("named from the TV" in e["msg"] for e in self.events.list()))

    def test_a_name_the_user_typed_is_never_overwritten(self):
        d = self.store.add_device("Reception", "10.0.0.6")
        self.assertFalse(d["auto_name"])
        self.tv["10.0.0.6:5555"] = "Something Else"
        self.assertEqual(self.poll(d)["name"], "Reception")
        # renaming an auto device by hand turns automatic naming off
        a = self.store.add_device("", "10.0.0.7")
        self.store.update_device(a["id"], name="My TV")
        self.tv["10.0.0.7:5555"] = "Other"
        r = self.poll(a)
        self.assertEqual((r["name"], r["auto_name"]), ("My TV", False))
        # saving the same name again (the Settings form does this) does not flip it
        b = self.store.add_device("", "10.0.0.8")
        self.store.update_device(b["id"], name=b["name"])
        self.assertTrue(self.store.device(b["id"])["auto_name"])

    def test_factory_default_names_are_told_apart(self):
        self.assertEqual(display_name("Android TV", "SmartTV", "172.16.50.196:5555"), "Android TV · .196")
        self.assertEqual(display_name("SmartTV 4K", "SmartTV 4K", "172.16.10.148:5555"), "SmartTV 4K · .148")
        self.assertEqual(display_name("1 and 2 grade", "Smart TV", "172.16.50.227:5555"), "1 and 2 grade")
        a, b = self.store.add_device("", "10.0.1.1"), self.store.add_device("", "10.0.1.2")
        self.tv.update({"10.0.1.1:5555": "Gym", "10.0.1.2:5555": "Gym"})   # two TVs with the same custom name
        self.assertEqual(self.poll(a)["name"], "Gym")
        self.assertEqual(self.poll(b)["name"], "Gym · .2")

    def test_missing_name_keeps_the_address(self):
        d = self.store.add_device("", "10.0.0.9")
        self.tv["10.0.0.9:5555"] = "null"
        self.assertEqual(self.poll(d)["name"], "10.0.0.9:5555")

    def test_legacy_import_names_migrate(self):
        legacy = [{"id": "a1", "name": "tv-50-196", "addr": "172.16.50.196:5555", "group": "", "restore": {"enabled": True, "last": None}},
                  {"id": "a2", "name": "Lobby", "addr": "10.0.0.2:5555", "group": "", "restore": {"enabled": True, "last": None}},
                  {"id": "a3", "name": "10.0.0.3:5555", "addr": "10.0.0.3:5555", "group": "", "restore": {"enabled": True, "last": None}}]
        with tempfile.TemporaryDirectory() as t:
            json.dump(legacy, open(os.path.join(t, "devices.json"), "w"))
            s = Store(t)
            self.assertEqual([d["auto_name"] for d in s.devices()], [True, False, True])
            self.assertEqual([d["name"] for d in Store(t).devices()][1], "Lobby")      # persisted, reloads fine


if __name__ == "__main__":
    unittest.main()
