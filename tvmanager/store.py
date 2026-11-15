"""JSON persistence (devices, schedules) and the in-memory + on-disk event log."""
import json
import os
import threading
import time
import uuid
from collections import deque

from .parsers import SAFE_ADDR


def _atomic_write(path, data, mode=None):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def normalize_addr(addr):
    addr = (addr or "").strip()
    if not SAFE_ADDR.match(addr):
        raise ValueError("invalid address")
    if ":" not in addr:
        addr += ":5555"
    return addr


class Store:
    def __init__(self, data_dir):
        self.dir = data_dir
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.RLock()
        self._devices = self._load("devices.json", [])
        self._schedules = self._load("schedules.json", [])

    def _load(self, name, default):
        try:
            with open(os.path.join(self.dir, name)) as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, name, data):
        _atomic_write(os.path.join(self.dir, name), data)

    # ---- devices -------------------------------------------------------
    def devices(self):
        with self.lock:
            return [dict(d) for d in self._devices]

    def device(self, dev_id):
        with self.lock:
            for d in self._devices:
                if d["id"] == dev_id:
                    return dict(d)
        return None

    def add_device(self, name, addr, group=""):
        addr = normalize_addr(addr)
        with self.lock:
            if any(d["addr"] == addr for d in self._devices):
                raise ValueError("a device with that address already exists")
            d = {"id": uuid.uuid4().hex[:8], "name": (name or addr).strip()[:60], "addr": addr,
                 "group": (group or "").strip()[:40],
                 "restore": {"enabled": True, "last": None}}
            self._devices.append(d)
            self._save("devices.json", self._devices)
            return dict(d)

    def update_device(self, dev_id, **fields):
        with self.lock:
            for d in self._devices:
                if d["id"] == dev_id:
                    if "addr" in fields and fields["addr"] is not None:
                        fields["addr"] = normalize_addr(fields["addr"])
                    for k in ("name", "addr", "group", "restore"):
                        if k in fields and fields[k] is not None:
                            d[k] = fields[k]
                    self._save("devices.json", self._devices)
                    return dict(d)
        return None

    def delete_device(self, dev_id):
        with self.lock:
            n = len(self._devices)
            self._devices = [d for d in self._devices if d["id"] != dev_id]
            self._schedules = [dict(s, targets=[t for t in s.get("targets", []) if t != dev_id])
                               for s in self._schedules]
            self._save("devices.json", self._devices)
            self._save("schedules.json", self._schedules)
            return len(self._devices) != n

    # ---- schedules -----------------------------------------------------
    def schedules(self):
        with self.lock:
            return [dict(s) for s in self._schedules]

    def save_schedule(self, sched):
        with self.lock:
            for i, s in enumerate(self._schedules):
                if s["id"] == sched["id"]:
                    self._schedules[i] = sched
                    break
            else:
                self._schedules.append(sched)
            self._save("schedules.json", self._schedules)
            return dict(sched)

    def delete_schedule(self, sid):
        with self.lock:
            n = len(self._schedules)
            self._schedules = [s for s in self._schedules if s["id"] != sid]
            self._save("schedules.json", self._schedules)
            return len(self._schedules) != n


class EventLog:
    def __init__(self, data_dir=None, maxlen=500):
        self.items = deque(maxlen=maxlen)
        self.lock = threading.Lock()
        self.path = os.path.join(data_dir, "events.log") if data_dir else None

    def add(self, device, msg, level="info"):
        ev = {"ts": time.time(), "device": device, "level": level, "msg": msg}
        with self.lock:
            self.items.appendleft(ev)
            if self.path:
                try:
                    with open(self.path, "a") as f:
                        f.write(json.dumps(ev) + "\n")
                except OSError:
                    pass
        return ev

    def list(self, n=200):
        with self.lock:
            return list(self.items)[:n]
