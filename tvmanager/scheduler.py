"""Minute-resolution scheduler for power/input actions across devices."""
import threading
import time
import uuid

ACTIONS = ("wake", "sleep", "reboot", "home", "input")


WEEK = 7 * 1440
BRING_UP_FOR = 15 * 60        # keep trying to bring a TV up for this long after a window starts
RETRY_EVERY = 30
CATCH_UP = 10                 # minutes after a window's start in which a missed start (restart, slow tick) still counts


def parse_hm(t):
    hh, mm = str(t).split(":")
    hh, mm = int(hh), int(mm)
    assert 0 <= hh < 24 and 0 <= mm < 60
    return hh * 60 + mm


def hm(minutes):
    return "%02d:%02d" % (minutes // 60 % 24, minutes % 60)


def duration(s):
    """Minutes a window lasts; an end at or before the start means it runs past midnight."""
    d = (parse_hm(s["end"]) - parse_hm(s["start"])) % 1440
    return d or 1440


def occurrences(s, now_min):
    """For a window schedule, yield (minutes since it started) for every day-start that is currently running."""
    dur = duration(s)
    for d in s.get("days", []):
        elapsed = (now_min - (d * 1440 + parse_hm(s["start"]))) % WEEK
        if elapsed < dur:
            yield elapsed


def ends_now(s, now_min):
    """True in the minute a window ends."""
    start, dur = parse_hm(s["start"]), duration(s)
    return any((now_min - (d * 1440 + start + dur)) % WEEK == 0 for d in s.get("days", []))


def validate_window(data, existing_id=None):
    try:
        sm, em = parse_hm(data.get("start")), parse_hm(data.get("end"))
    except Exception:
        raise ValueError("start and end must be times like 07:30")
    if sm == em:
        raise ValueError("the end must be different from the start")
    days = sorted({int(d) for d in data.get("days", range(7)) if 0 <= int(d) <= 6})
    if not days:
        raise ValueError("pick at least one day")
    targets = [str(x) for x in data.get("targets", [])]
    if not targets:
        raise ValueError("pick at least one TV")
    return {"id": existing_id or uuid.uuid4().hex[:8], "kind": "window", "name": str(data.get("name") or "")[:60],
            "start": hm(sm), "end": hm(em), "days": days, "targets": targets,
            "enabled": bool(data.get("enabled", True)), "updated": time.time()}


def validate(data, existing_id=None):
    if data.get("kind") == "window" or ("start" in data and "end" in data and "action" not in data):
        return validate_window(data, existing_id)
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
    def __init__(self, store, events, run_action, get_status=None):
        """run_action(device_dict, action, args_dict) -> (ok, message); get_status(device_dict) -> status string"""
        self.store, self.events, self.run_action = store, events, run_action
        self.get_status = get_status or (lambda dev: "unknown")
        self._stop = threading.Event()
        self._fired = {}
        self._handled = set()          # (schedule id, occurrence start minute) already started
        self.pending = {}              # device id -> bring-up job

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
            self._stop.wait(10)

    def tick(self, lt, now_ts=None):
        now_ts = now_ts if now_ts is not None else time.mktime(lt)
        self._tick_actions(lt)
        self._tick_windows(lt, now_ts)
        self._service_pending(now_ts)

    # ---- windows: "these TVs are on from start to end" -------------------
    def _tick_windows(self, lt, now_ts):
        now_min = lt.tm_wday * 1440 + lt.tm_hour * 60 + lt.tm_min
        windows = [s for s in self.store.schedules() if s.get("kind") == "window" and s.get("enabled", True)]
        for s in windows:
            for elapsed in occurrences(s, now_min):
                start_ts = now_ts - elapsed * 60 - lt.tm_sec
                key = (s["id"], int(start_ts // 60))
                if key in self._handled:
                    continue
                self._handled.add(key)
                if elapsed <= CATCH_UP or s.get("updated", 0) >= start_ts - 60:      # on time, or drawn while it was running
                    self._begin(s, now_ts)
        stamp = time.strftime("%Y-%m-%d %H:%M", lt)
        for s in windows:
            if ends_now(s, now_min) and self._fired.get(("end", s["id"])) != stamp:
                self._fired[("end", s["id"])] = stamp
                self._end(s, windows, now_min)
        if len(self._handled) > 500:
            self._handled = set(sorted(self._handled, key=lambda k: k[1])[-200:])

    def _begin(self, s, now_ts):
        label = s.get("name") or "schedule"
        for dev_id in s["targets"]:
            if self.store.device(dev_id):
                self.pending[dev_id] = {"label": label, "until": now_ts + BRING_UP_FOR, "next": 0, "tries": 0}

    def _service_pending(self, now_ts):
        """Bring each TV up, working out how: over ADB if it is reachable, over the network if it is fully off."""
        for dev_id, job in list(self.pending.items()):
            dev = self.store.device(dev_id)
            if not dev:
                del self.pending[dev_id]
                continue
            if self.get_status(dev) == "online":
                self.events.add(dev["name"], "schedule '%s': TV is on%s" % (job["label"], "" if job["tries"] else " already"))
                del self.pending[dev_id]
            elif now_ts >= job["until"]:
                self.events.add(dev["name"], "schedule '%s': the TV did not come on within %d minutes" % (job["label"], BRING_UP_FOR // 60), "error")
                del self.pending[dev_id]
            elif now_ts >= job["next"]:
                job["tries"] += 1
                job["next"] = now_ts + RETRY_EVERY
                ok, msg = self.run_action(dev, "wake", {})
                if job["tries"] == 1:
                    how = "over the network" if "Wake-on-LAN" in (msg or "") else "over ADB"
                    self.events.add(dev["name"], "schedule '%s': waking the TV %s%s" % (job["label"], how, "" if ok else " failed: %s" % msg),
                                    "info" if ok else "error")

    def _end(self, s, windows, now_min):
        label = s.get("name") or "schedule"
        for dev_id in s["targets"]:
            dev = self.store.device(dev_id)
            if not dev:
                continue
            if any(o["id"] != s["id"] and dev_id in o["targets"] and any(True for _ in occurrences(o, now_min)) for o in windows):
                continue                                   # another window keeps this TV on
            self.pending.pop(dev_id, None)
            if self.get_status(dev) == "online":
                ok, msg = self.run_action(dev, "sleep", {})
                self.events.add(dev["name"], "schedule '%s' ended: standby%s" % (label, "" if ok else " failed: %s" % msg), "info" if ok else "error")

    # ---- single timed actions (older style) ------------------------------
    def _tick_actions(self, lt):
        stamp = time.strftime("%Y-%m-%d %H:%M", lt)
        hhmm = time.strftime("%H:%M", lt)
        for s in self.store.schedules():
            if s.get("kind") == "window" or not s.get("enabled", True) or s["time"] != hhmm or lt.tm_wday not in s.get("days", []):
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
