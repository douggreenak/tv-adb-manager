"""Network keepalive: probing, ADB nudge, settings."""
import tempfile
import unittest

from tvmanager.keepalive import KeepAlive, clamp, probe
from tvmanager.store import EventLog, Store


class FakeMon:
    def __init__(self):
        self.status, self.kicked = "offline", []

    def snapshot(self, i):
        return {"status": self.status}

    def kick(self, d):
        self.kicked.append(d["addr"])


class Conn:
    def __init__(self, exc=None):
        self.exc = exc

    def __call__(self, addr, timeout=None):
        if self.exc:
            raise self.exc
        return self

    def close(self):
        pass


class KeepAliveTests(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual([clamp(v) for v in (0, -3, 1, 5, 9999)], [0, 0, 2, 5, 300])

    def test_probe(self):
        self.assertTrue(probe("10.0.0.5:5555", connect=Conn()))
        self.assertTrue(probe("10.0.0.5:5555", connect=Conn(ConnectionRefusedError())))   # up, adbd down
        self.assertFalse(probe("10.0.0.5:5555", connect=Conn(TimeoutError())))
        self.assertFalse(probe("10.0.0.5:5555", connect=Conn(OSError())))

    def test_tick_records_and_nudges_adb(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, mon, ev = Store(tmp), FakeMon(), EventLog()
            d = store.add_device("TV", "10.0.0.5")
            ka = KeepAlive(store, mon, ev, probe_fn=lambda a: True)
            ka.tick()
            self.assertTrue(ka.view(d["id"])["up"])
            self.assertEqual(ev.list(), [])                          # first probe isn't an event
            self.assertEqual(mon.kicked, ["10.0.0.5:5555"])          # reachable but ADB offline -> reconnect
            ka.probe = lambda a: False
            ka.tick()
            self.assertFalse(ka.view(d["id"])["up"])
            self.assertTrue(any("left the network" in e["msg"] for e in ev.list()))
            ka.probe = lambda a: True
            ka.tick()
            self.assertTrue(any("back on the network" in e["msg"] for e in ev.list()))

    def test_settings_default_and_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            ka = KeepAlive(store, FakeMon(), EventLog())
            self.assertEqual(ka.interval(), 5)
            store.set_settings(keepalive=0)
            self.assertEqual(KeepAlive(Store(tmp), FakeMon(), EventLog()).interval(), 0)    # persisted


if __name__ == "__main__":
    unittest.main()
