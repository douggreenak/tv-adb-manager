"""Minute-resolution scheduler for power/input actions across devices."""
import threading
import time
import uuid

ACTIONS = ("wake", "sleep", "reboot", "home", "input")


def validate(data, existing_id=None):
    action = data.get("action")
    if action not in ACTIONS:
        raise ValueError("action must be one of %s" % ", ".join(ACTIONS))
    t = str(data.get("time", ""))
    try:
        hh, mm = t.split(":")
        assert 0 <= int(hh) < 24 and 0 <= int(mm) < 60
    except Exception:
        raise ValueError("time must be HH:MM")
    days = sorted({int(d) for d in data.get("days", range(7)) if 0 <= int(d) <= 6})
    if not days:
        raise ValueError("pick at least one day")
    targets = [str(x) for x in data.get("targets", [])]
    if not targets:
        raise ValueError("pick at least one device")
    if action == "input" and not data.get("input"):
        raise ValueError("input action needs an input id")
    return {"id": existing_id or uuid.uuid4().hex[:8], "name": str(data.get("name") or action)[:60],
            "action": action, "time": "%02d:%02d" % (int(hh), int(mm)), "days": days, "targets": targets,
            "input": data.get("input") or None, "enabled": bool(data.get("enabled", True))}


class Scheduler:
    def __init__(self, store, events, run_action):
        """run_action(device_dict, action, args_dict) -> (ok, message)"""
        self.store, self.events, self.run_action = store, events, run_action
        self._stop = threading.Event()
        self._fired = {}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="scheduler").start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick(time.localtime())
            except Exception as e:
                self.events.add("-", "scheduler error: %r" % e, "error")
            self._stop.wait(20)

    def tick(self, lt):
        stamp = time.strftime("%Y-%m-%d %H:%M", lt)
        hhmm = time.strftime("%H:%M", lt)
        for s in self.store.schedules():
            if not s.get("enabled", True) or s["time"] != hhmm or lt.tm_wday not in s.get("days", []):
                continue
            if self._fired.get(s["id"]) == stamp:
                continue
            self._fired[s["id"]] = stamp
            for dev_id in s["targets"]:
                dev = self.store.device(dev_id)
                if not dev:
                    continue
                ok, msg = self.run_action(dev, s["action"], {"input": s.get("input")})
                self.events.add(dev["name"], "schedule '%s': %s %s" % (s["name"], s["action"], "ok" if ok else "failed: %s" % msg),
                                "info" if ok else "error")
