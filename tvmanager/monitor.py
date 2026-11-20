"""Background poller: tracks each TV's state and restores its last input after power-on.

Per device, every cycle:
  * make sure ADB is connected (reconnect with back-off)
  * one combined shell call -> wakefulness, active TV session, top activity
  * remember the active passthrough input while awake
  * on wake / reconnect (cold boot) schedule a restore of the remembered input
"""
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from . import parsers as P
from . import wol
from . import keepon

PROBE = ("(dumpsys power | grep -m1 mWakefulness=; echo ==; "
         "dumpsys tv_input | grep -A1 'SessionState@' | grep inputId; echo ==; "
         "dumpsys activity activities | grep -m1 -E 'mResumedActivity|topResumedActivity') 2>/dev/null; true")
STATIC_PROBE = ("getprop ro.product.manufacturer; echo ==; getprop ro.product.model; echo ==; "
                "getprop ro.build.version.release; echo ==; settings get secure tv_input_custom_labels; echo ==; "
                "cmd package resolve-activity --brief -a android.intent.action.MAIN "
                "-c android.intent.category.HOME 2>/dev/null | tail -1; echo ==; settings get global device_name; echo ==; "
                "for i in eth0 wlan0; do echo $i $(cat /sys/class/net/$i/address 2>/dev/null) "
                "$(ip -f inet addr show $i 2>/dev/null | grep -o 'inet [0-9.]*'); done")

GENERIC_NAMES = {"android tv", "google tv", "tv", "smart tv", "smarttv", "android", "android box"}


def display_name(tv_name, model, addr):
    """The TV's own name; factory-default names ("Android TV", or just the model) get the address tail so
    two TVs of the same make are told apart."""
    t = tv_name.strip()
    if t.lower() in GENERIC_NAMES or t.lower() == (model or "").strip().lower():
        return "%s · .%s" % (t, addr.split(":")[0].rsplit(".", 1)[-1])
    return t


def pick_mac(text, addr):
    """From lines like 'wlan0 aa:bb:.. inet 10.0.0.5' choose the MAC of the interface that carries `addr`."""
    host = addr.split(":")[0]
    found = []
    for line in text.splitlines():
        m = re.match(r"^\S+\s+((?:[0-9a-f]{2}:){5}[0-9a-f]{2})\s*(?:inet (\S+))?", line.strip(), re.I)
        if m:
            found.append((m.group(1).lower(), m.group(2)))
    for mac, ip in found:
        if ip == host:
            return mac
    return found[0][0] if len(found) == 1 else None


KEEP_ON_RECHECK = 600.0     # re-read the TV's timers this often (its own menus can rewrite them)
WAKE_SETTLE = 3.0       # seconds after waking before we look at what the TV did by itself
CONNECT_RETRY = 10.0
UNAUTH_RETRY = 30.0


def passthrough_uri(input_id):
    return "content://android.media.tv/passthrough/" + urllib.parse.quote(input_id, safe="")


def launch_input(adb, addr, input_id):
    cmd = "am start -a android.intent.action.VIEW -d '%s'" % passthrough_uri(input_id)
    rc, out = adb.shell(addr, cmd)
    return rc == 0 and "Error" not in out, out.strip()


class Monitor:
    def __init__(self, adb, store, events, poll=3.0, workers=16):
        self.adb, self.store, self.events, self.poll = adb, store, events, poll
        self.states = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.inflight = set()
        self._stop = threading.Event()
        self._thread = None
        self.last_tick = None          # heartbeat for the service watchdog

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True, name="monitor")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:  # never let the loop die
                self.events.add("-", "monitor error: %r" % e, "error")
            self.last_tick = time.time()
            self._stop.wait(self.poll)

    def tick(self):
        adb_states = self.adb.devices()
        devs = self.store.devices()
        ids = {d["id"] for d in devs}
        with self.lock:
            for k in [k for k in self.states if k not in ids]:
                del self.states[k]
        for d in devs:
            with self.lock:
                if d["id"] in self.inflight:
                    continue
                self.inflight.add(d["id"])
            self.pool.submit(self._run_cycle, d, adb_states.get(d["addr"]))

    def kick(self, dev):
        """Try an ADB reconnect now (used by the keepalive when the TV answers on the network)."""
        st = self._st(dev["id"])
        now = time.time()
        if st["status"] in ("offline", "unknown") and now - st["last_try"] > 3:
            st["last_try"] = now
            self.pool.submit(self.adb.connect, dev["addr"])

    def _run_cycle(self, dev, adb_state):
        try:
            self.cycle(dev, adb_state)
        except Exception as e:
            self.events.add(dev["name"], "poll error: %r" % e, "error")
        finally:
            with self.lock:
                self.inflight.discard(dev["id"])

    # ---- state ---------------------------------------------------------
    def _st(self, dev_id):
        with self.lock:
            return self.states.setdefault(dev_id, {
                "status": "unknown", "awake": None, "input": None, "top": None,
                "manufacturer": None, "model": None, "android": None, "labels": {}, "home": None,
                "last_seen": None, "seen_online": False, "wake_at": None, "last_try": 0.0,
            })

    def snapshot(self, dev_id):
        with self.lock:
            st = self.states.get(dev_id)
            return dict(st) if st else None

    # ---- one poll ------------------------------------------------------
    def cycle(self, dev, adb_state):
        st = self._st(dev["id"])
        addr, name = dev["addr"], dev["name"]
        now = time.time()

        if adb_state == "unauthorized":
            self._set_status(st, name, "unauthorized")
            if now - st["last_try"] > UNAUTH_RETRY:
                st["last_try"] = now
                self.adb.connect(addr)
            return
        if adb_state != "device":
            was_up = st["status"] in ("online", "asleep")
            if was_up:
                self.events.add(name, "went offline")
            self._set_status(st, name, "offline", quiet=True)
            st["static_loaded"] = False
            if now - st["last_try"] > CONNECT_RETRY:
                st["last_try"] = now
                self.adb.connect(addr)
            return

        rc, out = self.adb.shell(addr, PROBE)
        if rc != 0 or "mWakefulness=" not in out:
            return  # transient; keep the previous state
        parts = out.split("==")
        awake = P.parse_wakefulness(parts[0])
        sessions = P.parse_sessions(parts[1]) if len(parts) > 1 else []
        top = P.parse_top_activity(parts[2]) if len(parts) > 2 else None
        inp = P.pick_passthrough(sessions)

        if not st.get("static_loaded"):
            self._load_static(st, addr, dev)

        self.keep_on(dev, st)

        # Came back after being unreachable (e.g. power loss + cold boot) counts as a wake too.
        reconnected = st["seen_online"] and st["status"] in ("offline", "unauthorized")
        woke = bool(awake) and (st["awake"] is False or reconnected)
        st.update(awake=awake, wakefulness=P.parse_wakefulness_raw(parts[0]), input=inp, top=top, last_seen=now, seen_online=True)
        self._set_status(st, name, "online" if awake else "asleep", quiet=True)

        restore = dict(dev.get("restore") or {})
        if awake and inp and inp != restore.get("last"):
            restore["last"] = inp
            self.store.update_device(dev["id"], restore=restore)
            self.events.add(name, "remembered input %s" % P.short_input_name(inp, st["labels"]))
            dev = dict(dev, restore=restore)

        if woke:
            self.events.add(name, "woke up" if not reconnected else "came back online")
            st["wake_at"] = now + WAKE_SETTLE
        if st["wake_at"] and now >= st["wake_at"] and awake:
            st["wake_at"] = None
            self._restore(dev, st, inp, top)

    def keep_on(self, dev, st, force=False):
        """Make sure the TV's own power-off and sleep timers are off (unless turned off for this TV)."""
        if not dev.get("keep_on", True):
            return
        now = time.time()
        if not force and now - st.get("keepon_at", 0) < KEEP_ON_RECHECK:
            return
        st["keepon_at"] = now
        rc, out = self.adb.shell(dev["addr"], keepon.READ_CMD)
        cur = keepon.parse(out)
        if rc != 0 or not cur:
            st["keepon_at"] = 0
            return
        changes = keepon.plan(cur)
        if not changes:
            return
        rc, out = self.adb.shell(dev["addr"], keepon.put_cmd(changes))
        if rc != 0:
            self.events.add(dev["name"], "could not apply keep-on: %s" % out.strip()[:120], "error")
            return
        prev = dict(dev.get("keep_on_prev") or {})
        for t, k, _ in changes:
            prev.setdefault("%s.%s" % (t, k), cur.get("%s.%s" % (t, k)))      # remember the original, once
        self.store.update_device(dev["id"], keep_on_prev=prev)
        self.events.add(dev["name"], "keep-on: " + keepon.describe(changes, cur))

    def revert_keep_on(self, dev):
        """Put the TV's own timers back to what they were before keep-on changed them."""
        prev = dev.get("keep_on_prev") or {}
        if prev:
            rc, out = self.adb.shell(dev["addr"], keepon.revert_cmd(prev))
            if rc != 0:
                return False, out.strip()
        self.store.update_device(dev["id"], keep_on_prev={})
        self.events.add(dev["name"], "keep-on turned off; TV timers restored")
        return True, "restored"

    def _restore(self, dev, st, current_input, top):
        name = dev["name"]
        cfg = dev.get("restore") or {}
        last = cfg.get("last")
        if not cfg.get("enabled", True) or not last:
            return
        if current_input:
            self.events.add(name, "already on %s, nothing to restore" % P.short_input_name(current_input, st["labels"]))
            return
        home = st.get("home")
        on_home = bool(top) and ((home and top.startswith(home + "/")) or "auncher" in top)
        if not on_home:
            self.events.add(name, "not restoring input: TV is on %s" % (top or "unknown"))
            return
        ok, out = launch_input(self.adb, dev["addr"], last)
        label = P.short_input_name(last, st["labels"])
        self.events.add(name, ("restored input %s" % label) if ok else ("failed to restore %s: %s" % (label, out)),
                        "info" if ok else "error")

    def restore_now(self, dev):
        st = self._st(dev["id"])
        last = (dev.get("restore") or {}).get("last")
        if not last:
            return False, "no input remembered yet"
        ok, out = launch_input(self.adb, dev["addr"], last)
        self.events.add(dev["name"], "manual restore of %s: %s" % (P.short_input_name(last, st["labels"]), "ok" if ok else out),
                        "info" if ok else "error")
        return ok, out

    def apply_auto_name(self, dev_id):
        """If this device follows the TV's name, store the name the TV reports."""
        dev, st = self.store.device(dev_id), self.snapshot(dev_id)
        if not dev or not st or not dev.get("auto_name") or not st.get("tv_name"):
            return
        old = dev["name"]
        new = self.store.set_auto_name(dev_id, display_name(st["tv_name"], st.get("model"), dev["addr"]))
        if new:
            self.events.add(new, "named from the TV (was “%s”)" % old)

    def _load_static(self, st, addr, dev=None):
        rc, out = self.adb.shell(addr, STATIC_PROBE)
        parts = [p.strip() for p in out.split("==")]
        if rc == 0 and len(parts) >= 5:
            tv = parts[5] if len(parts) > 5 else ""
            st.update(manufacturer=parts[0], model=parts[1], android=parts[2],
                      labels=P.parse_labels(parts[3]),
                      home=(parts[4].split("/")[0] or None),
                      tv_name=(tv if tv and tv != "null" else None))
            st["static_loaded"] = True
            mac = pick_mac(parts[6] if len(parts) > 6 else "", addr) or wol.arp_mac(addr.split(":")[0])
            if mac:
                st["mac"] = mac
                if dev is not None and self.store.set_learned_mac(dev["id"], mac):
                    self.events.add(dev["name"], "learned MAC address %s (for Wake-on-LAN)" % mac)
            if dev is not None:
                self.apply_auto_name(dev["id"])

    def _set_status(self, st, name, status, quiet=False):
        if st["status"] != status:
            if not quiet:
                self.events.add(name, "status: %s" % status)
            st["status"] = status
