"""Calendar windows: 'these TVs are on from start to end'."""
import tempfile
import time
import unittest

from tvmanager.scheduler import Scheduler, duration, ends_now, occurrences, validate
from tvmanager.store import EventLog, Store

MON = 0


def lt(wday, hh, mm, sec=0):
    # 2026-11-16 is a Monday
    return time.localtime(time.mktime((2026, 11, 16 + wday, hh, mm, sec, 0, 0, -1)))


def win(**kw):
    d = {"kind": "window", "start": "07:00", "end": "17:00", "days": [0, 1, 2, 3, 4], "targets": ["a"], "id": "w1", "name": "Open", "enabled": True,
         "updated": 0}
    d.update(kw)
    return d


class MathTests(unittest.TestCase):
    def test_duration_and_overnight(self):
        self.assertEqual(duration(win()), 600)
        self.assertEqual(duration(win(start="22:00", end="06:00")), 480)

    def test_occurrences(self):
        s = win()
        now = lambda w, h, m: w * 1440 + h * 60 + m
        self.assertEqual(list(occurrences(s, now(MON, 7, 0))), [0])
        self.assertEqual(list(occurrences(s, now(MON, 12, 30))), [330])
        self.assertEqual(list(occurrences(s, now(MON, 17, 0))), [])
        self.assertEqual(list(occurrences(s, now(5, 12, 0))), [])                 # Saturday: not a day
        night = win(start="22:00", end="06:00", days=[4])                         # Friday night
        self.assertEqual(list(occurrences(night, now(5, 3, 0))), [300])           # still running Saturday 3am
        self.assertEqual(list(occurrences(night, now(6, 3, 0))), [])
        self.assertTrue(ends_now(night, now(5, 6, 0)))
        self.assertTrue(ends_now(win(), now(MON, 17, 0)))
        self.assertFalse(ends_now(win(), now(MON, 17, 1)))

    def test_validate(self):
        ok = validate({"kind": "window", "start": "7:30", "end": "17:00", "targets": ["a"], "days": [0, 6]})
        self.assertEqual((ok["start"], ok["end"], ok["days"]), ("07:30", "17:00", [0, 6]))
        for bad in ({"start": "07:00", "end": "07:00"}, {"start": "07:00", "end": "25:00"}, {"start": "07:00", "end": "08:00", "days": []},
                    {"start": "07:00", "end": "08:00", "targets": []}):
            with self.assertRaises(ValueError):
                validate(dict({"kind": "window", "targets": ["a"]}, **bad))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.ev = Store(self.tmp.name), EventLog()
        self.a = self.store.add_device("A", "10.0.0.1")
        self.b = self.store.add_device("B", "10.0.0.2")
        self.status, self.calls = {}, []
        self.sched = Scheduler(self.store, self.ev, self.do_action, get_status=lambda d: self.status.get(d["id"], "offline"))

    def tearDown(self):
        self.tmp.cleanup()

    def do_action(self, dev, action, args):
        self.calls.append((dev["id"], action))
        return True, ("Sent Wake-on-LAN to aa" if self.status.get(dev["id"], "offline") == "offline" and action == "wake" else "")

    def add(self, **kw):
        s = win(targets=[self.a["id"]], **kw)
        s = dict(s, id=kw.get("id", "w1"))
        self.store.save_schedule(s)
        return s

    def msgs(self):
        return [e["msg"] for e in self.ev.list()]

    def test_start_wakes_offline_tv_over_the_network_and_retries(self):
        self.add()
        t0 = time.mktime(lt(MON, 7, 0))
        self.sched.tick(lt(MON, 7, 0))
        self.assertEqual(self.calls, [(self.a["id"], "wake")])
        self.assertTrue(any("over the network" in m for m in self.msgs()))
        self.sched.tick(lt(MON, 7, 0, 10), t0 + 10)                          # too soon to retry
        self.assertEqual(len(self.calls), 1)
        self.sched.tick(lt(MON, 7, 0, 40), t0 + 40)                          # retries after 30 s
        self.assertEqual(len(self.calls), 2)
        self.status[self.a["id"]] = "online"                                 # it came up
        self.sched.tick(lt(MON, 7, 1), t0 + 60)
        self.assertNotIn(self.a["id"], self.sched.pending)
        self.assertTrue(any("TV is on" in m for m in self.msgs()))

    def test_asleep_tv_is_woken_over_adb(self):
        self.add()
        self.status[self.a["id"]] = "asleep"
        self.sched.tick(lt(MON, 7, 0))
        self.assertTrue(any("over ADB" in m for m in self.msgs()))

    def test_already_on_does_nothing(self):
        self.add()
        self.status[self.a["id"]] = "online"
        self.sched.tick(lt(MON, 7, 0))
        self.assertEqual(self.calls, [])

    def test_gives_up_after_15_minutes(self):
        self.add()
        t0 = time.mktime(lt(MON, 7, 0))
        self.sched.tick(lt(MON, 7, 0), t0)
        self.sched.tick(lt(MON, 7, 16), t0 + 16 * 60)
        self.assertTrue(any("did not come on" in m for m in self.msgs()))
        self.assertNotIn(self.a["id"], self.sched.pending)

    def test_end_puts_online_tv_in_standby(self):
        self.add()
        self.status[self.a["id"]] = "online"
        self.sched.tick(lt(MON, 17, 0))
        self.assertEqual(self.calls, [(self.a["id"], "sleep")])
        self.sched.tick(lt(MON, 17, 0, 15))
        self.assertEqual(len(self.calls), 1)                                  # once per minute

    def test_overlapping_window_keeps_it_on(self):
        self.add()
        self.add(id="w2", start="12:00", end="20:00", days=[0])
        self.status[self.a["id"]] = "online"
        self.sched.tick(lt(MON, 17, 0))
        self.assertNotIn((self.a["id"], "sleep"), self.calls)

    def test_missed_start_is_caught_up_shortly_after_but_not_hours_later(self):
        self.add()
        self.sched.tick(lt(MON, 7, 6))
        self.assertTrue(self.calls)
        self.calls.clear()
        self.add(id="w3", name="Later")
        self.sched.pending.clear()
        s = win(id="old", targets=[self.b["id"]], start="01:00", end="23:00")
        self.store.save_schedule(s)
        self.sched.tick(lt(1, 12, 0))                                          # Tuesday noon, long after the 01:00 start
        self.assertFalse(any(c[0] == self.b["id"] for c in self.calls))

    def test_window_drawn_while_running_starts_now(self):
        s = win(updated=time.mktime(lt(MON, 12, 0)) - 5, start="09:00", end="15:00")
        self.store.save_schedule(dict(s, targets=[self.a["id"]]))
        self.sched.tick(lt(MON, 12, 0))
        self.assertTrue(self.calls)

    def test_disabled_and_paused_do_nothing(self):
        self.add(enabled=False)
        self.sched.tick(lt(MON, 7, 0))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
