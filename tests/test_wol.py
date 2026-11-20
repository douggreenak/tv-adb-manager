"""Wake-on-LAN: packet, MAC handling, learning the MAC from the TV, and waking an offline TV."""
import tempfile
import unittest

from tests.fakes import FakeAdb
from tvmanager import wol
from tvmanager.monitor import Monitor, pick_mac
from tvmanager.store import EventLog, Store


class FakeSock:
    sent = []

    def __init__(self, *a):
        pass

    def setsockopt(self, *a):
        pass

    def sendto(self, data, addr):
        FakeSock.sent.append((data, addr))

    def close(self):
        pass


class WolTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(wol.normalize_mac("AA-BB-CC-DD-EE-FF"), "aa:bb:cc:dd:ee:ff")
        self.assertEqual(wol.normalize_mac("aabbccddeeff"), "aa:bb:cc:dd:ee:ff")
        self.assertEqual(wol.normalize_mac(""), "")
        for bad in ("aa:bb:cc", "zz:bb:cc:dd:ee:ff", "00:00:00:00:00:00", "aa:bb-cc:dd:ee:ff"):
            with self.assertRaises(ValueError):
                wol.normalize_mac(bad)

    def test_packet(self):
        p = wol.magic_packet("aa:bb:cc:dd:ee:ff")
        self.assertEqual(len(p), 102)
        self.assertEqual(p[:6], b"\xff" * 6)
        self.assertEqual(p[6:12], bytes.fromhex("aabbccddeeff"))

    def test_send_targets(self):
        FakeSock.sent = []
        n = wol.send("aa:bb:cc:dd:ee:ff", "172.16.10.148", sock_factory=FakeSock)
        self.assertEqual(n, 6)
        self.assertEqual({a[0] for _, a in FakeSock.sent}, {"255.255.255.255", "172.16.10.255", "172.16.10.148"})

    def test_pick_mac_matches_interface_with_the_tv_address(self):
        text = "eth0 11:22:33:44:55:66\nwlan0 aa:bb:cc:dd:ee:ff inet 172.16.10.148\n"
        self.assertEqual(pick_mac(text, "172.16.10.148:5555"), "aa:bb:cc:dd:ee:ff")
        self.assertIsNone(pick_mac("eth0\nwlan0\n", "1.2.3.4:5555"))
        self.assertEqual(pick_mac("eth0 11:22:33:44:55:66 inet 9.9.9.9\n", "1.2.3.4:5555"), "11:22:33:44:55:66")


class ArpTests(unittest.TestCase):
    def test_arp_table(self):
        with tempfile.NamedTemporaryFile("w", suffix=".arp") as f:
            f.write("IP address       HW type     Flags       HW address            Mask     Device\n"
                    "172.16.50.196    0x1         0x2         AA:BB:CC:DD:EE:01     *        eno1\n"
                    "172.16.50.227    0x1         0x0         00:00:00:00:00:00     *        eno1\n")
            f.flush()
            self.assertEqual(wol.arp_mac("172.16.50.196", f.name), "aa:bb:cc:dd:ee:01")
            self.assertIsNone(wol.arp_mac("172.16.50.227", f.name))      # incomplete entry
            self.assertIsNone(wol.arp_mac("172.16.50.1", f.name))


class LearnTests(unittest.TestCase):
    def test_mac_learned_then_user_value_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            d = store.add_device("TV", "10.0.0.5")
            self.assertTrue(store.set_learned_mac(d["id"], "AA:BB:CC:DD:EE:FF"))
            self.assertEqual(store.device(d["id"])["mac"], "aa:bb:cc:dd:ee:ff")
            store.update_device(d["id"], mac="11:22:33:44:55:66")
            self.assertFalse(store.set_learned_mac(d["id"], "aa:bb:cc:dd:ee:ff"))
            self.assertEqual(store.device(d["id"])["mac"], "11:22:33:44:55:66")
            with self.assertRaises(ValueError):
                store.update_device(d["id"], mac="nope")

    def test_monitor_learns_mac(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, adb = Store(tmp), FakeAdb()
            mon = Monitor(adb, store, EventLog())
            d = store.add_device("TV", "10.0.0.5")
            adb.responses[:] = [("getprop ro.product.manufacturer",
                                 "Hisense\n==\nM\n==\n11\n==\nnull\n==\nx/.y\n==\nTV\n==\n"
                                 "eth0\nwlan0 aa:bb:cc:dd:ee:ff inet 10.0.0.5\n"),
                                ("mWakefulness", "  mWakefulness=Awake\n==\n\n==\n")]
            mon.cycle(d, "device")
            self.assertEqual(store.device(d["id"])["mac"], "aa:bb:cc:dd:ee:ff")


if __name__ == "__main__":
    unittest.main()
