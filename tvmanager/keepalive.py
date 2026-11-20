"""Network keepalive: a tiny TCP probe to every TV every few seconds.

It does two things:
  * keeps traffic flowing to each TV so a Wi-Fi radio in standby is less likely to doze off the network
  * tells "still on the network, ADB just dropped" apart from "gone from the network", and reconnects ADB
    straight away in the first case
It cannot stop a TV that powers itself fully off (see docs/features.md).
"""
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DEFAULT_INTERVAL = 5
MIN_INTERVAL, MAX_INTERVAL = 2, 300


def clamp(v):
    """0 = off, otherwise MIN..MAX seconds."""
    v = int(v)
    return 0 if v <= 0 else max(MIN_INTERVAL, min(MAX_INTERVAL, v))


def probe(addr, timeout=3.0, connect=socket.create_connection):
    """True if the TV answers on the network: an accepted OR refused connection both mean it is up."""
    host, _, port = addr.partition(":")
    try:
        s = connect((host, int(port or 5555)), timeout=timeout)
        s.close()
        return True
    except ConnectionRefusedError:
        return True
    except (OSError, ValueError):
        return False


class KeepAlive:
    def __init__(self, store, monitor, events, probe_fn=probe):
        self.store, self.monitor, self.events, self.probe = store, monitor, events, probe_fn
        self.net = {}                       # device id -> {"up": bool, "since": ts, "last_reply": ts}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=8)
        self._stop = threading.Event()

    def interval(self):
        return clamp(self.store.settings().get("keepalive", DEFAULT_INTERVAL))

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="keepalive").start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            iv = self.interval()
            if iv:
                try:
                    self.tick()
                except Exception as e:
                    self.events.add("-", "keepalive error: %r" % e, "error")
            self._stop.wait(iv or 2)

    def tick(self):
        devs = self.store.devices()
        for d, up in zip(devs, self.pool.map(lambda d: self.probe(d["addr"]), devs)):
            self.record(d, up)

    def record(self, dev, up, now=None):
        now = now or time.time()
        if not up and (self.monitor.snapshot(dev["id"]) or {}).get("status") in ("online", "asleep"):
            up = True                # ADB is talking to it, so it is on the network (a slow probe is not an outage)
        with self.lock:
            prev = self.net.get(dev["id"])
            changed = prev is not None and prev["up"] != up          # the first probe is not a change
            cur = {"up": up, "since": prev["since"] if prev and not changed else now,
                   "last_reply": now if up else (prev["last_reply"] if prev else None)}
            self.net[dev["id"]] = cur
        if changed:
            self.events.add(dev["name"], "is back on the network" if up else "left the network")
        if up:
            st = self.monitor.snapshot(dev["id"]) or {}
            if st.get("status") == "offline":
                self.monitor.kick(dev)       # on the network but ADB isn't connected: reconnect now

    def view(self, dev_id):
        with self.lock:
            n = self.net.get(dev_id)
            return dict(n) if n else None
