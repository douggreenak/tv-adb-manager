"""JSON persistence (devices, schedules) and the in-memory + on-disk event log."""
import json
import os
import re
import threading
import time
import uuid
from collections import deque

from .parsers import SAFE_ADDR
from .wol import normalize_mac


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
        self._migrate_names()

    def _load(self, name, default):
        try:
            with open(os.path.join(self.dir, name)) as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, name, data):
        _atomic_write(os.path.join(self.dir, name), data)

    def _migrate_names(self):
        """Devices named after their address (or the old importer's tv-50-196 style) follow the TV's own name."""
        changed = False
        for d in self._devices:
            if "auto_name" not in d:
                host = d["addr"].split(":")[0]
                d["auto_name"] = bool(re.match(r"^tv-\d+-\d+$", d["name"]) or d["name"] in (d["addr"], host))
                changed = True
        if changed:
            self._save("devices.json", self._devices)

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
            host = addr.split(":")[0]
            name = (name or "").strip()
            d = {"id": uuid.uuid4().hex[:8], "name": (name or addr)[:60], "addr": addr,
                 "auto_name": (not name) or name in (addr, host),     # blank: take the TV's own name once it is known
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
                    if fields.get("name") is not None and fields["name"].strip() and fields["name"].strip() != d["name"]:
                        d["auto_name"] = False                          # the user chose a name: stop overwriting it
                    if "auto_name" in fields and fields["auto_name"] is not None:
                        d["auto_name"] = bool(fields["auto_name"])
                    if "mac" in fields and fields["mac"] is not None:
                        d["mac"] = normalize_mac(fields["mac"])
                        d["mac_auto"] = False                           # typed by the user: don't overwrite
                    for k in ("name", "addr", "group", "restore"):
                        if k in fields and fields[k] is not None:
                            d[k] = fields[k].strip() if k == "name" else fields[k]
                    self._save("devices.json", self._devices)
                    return dict(d)
        return None

    def set_auto_name(self, dev_id, name):
        """Set the name learned from the TV, keeping names unique. Returns the stored name, or None if unchanged."""
        name = (name or "").strip()[:60]
        with self.lock:
            for d in self._devices:
                if d["id"] != dev_id or not d.get("auto_name") or not name:
                    continue
                if any(o["id"] != dev_id and o["name"] == name for o in self._devices):
                    name = "%s · .%s" % (name, d["addr"].split(":")[0].rsplit(".", 1)[-1])
                if d["name"] == name:
                    return None
                d["name"] = name
                self._save("devices.json", self._devices)
                return name
        return None

    def set_learned_mac(self, dev_id, mac):
        """Remember the MAC the TV reported, unless the user entered one. Returns True if it changed."""
        mac = normalize_mac(mac)
        with self.lock:
            for d in self._devices:
                if d["id"] == dev_id and mac and d.get("mac_auto", True) and d.get("mac") != mac:
                    d["mac"], d["mac_auto"] = mac, True
                    self._save("devices.json", self._devices)
                    return True
        return False

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
        self.max_bytes = 2 * 1024 * 1024

    def add(self, device, msg, level="info"):
        ev = {"ts": time.time(), "device": device, "level": level, "msg": msg}
        with self.lock:
            self.items.appendleft(ev)
            if self.path:
                try:
                    if os.path.exists(self.path) and os.path.getsize(self.path) > self.max_bytes:
                        os.replace(self.path, self.path + ".1")                 # keep one previous file
                    with open(self.path, "a") as f:
                        f.write(json.dumps(ev) + "\n")
                except OSError:
                    pass
        return ev

    def list(self, n=200):
        with self.lock:
            return list(self.items)[:n]
