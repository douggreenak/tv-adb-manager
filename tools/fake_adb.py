#!/usr/bin/env python3
"""A stand-in `adb` that simulates a fleet of Android TVs, for testing without hardware.

Point the manager at it:   TVM_ADB=/path/to/tools/fake_adb.py  FAKE_ADB_STATE=/tmp/fleet.json
Control the fleet:         fake_adb.py ctl seed | list | set ADDR key=value ... | power ADDR on|off
                           | approve ADDR | wake ADDR | standby ADDR | input ADDR <input-id>
It never talks to a network, so it cannot touch real devices.
"""
import fcntl, json, os, re, sys, time, urllib.parse

STATE = os.environ.get("FAKE_ADB_STATE", "/tmp/fake_adb_fleet.json")
LAUNCHER = "com.leanbitlab.ltvL/.MainActivity"
HISENSE_APP = "com.mediatek.wwtv.tvcenter/.LiveTVMainActivity"
HS = "com.hisense.tv.hitvinput/.hdmi.HdmiTvInputService/"


def hdmi_inputs(prefix, n):
    return [{"id": prefix + str(i), "state": "connected" if i == 1 else "standby"} for i in range(1, n + 1)]


def new_tv(model, mfr, android, inputs, labels=None, app=HISENSE_APP, state="device"):
    return {"reachable": True, "auth": state, "connected": False, "boot_at": time.time() - 3600, "up_at": 0,
            "awake": True, "session": None, "top": LAUNCHER, "mfr": mfr, "model": model, "android": android,
            "inputs": inputs, "labels": labels or {}, "tvapp": app, "launcher": LAUNCHER,
            "packages": {"com.leanbitlab.ltvL": {"disabled": False, "system": False},
                         "com.google.android.tvlauncher": {"disabled": True, "system": True},
                         "com.android.vending": {"disabled": True, "system": True},
                         "com.netflix.ninja": {"disabled": False, "system": False},
                         "com.google.android.youtube.tv": {"disabled": False, "system": False},
                         "com.android.settings": {"disabled": False, "system": True}}}


def seed():
    return {
        "10.0.0.11:5555": new_tv("SmartTV 4K", "Hisense", "11", hdmi_inputs(HS + "HW", 3) + [{"id": "com.hisense.tv.hitvinput/.tuner.TunerTvInputService/HW0", "state": "connected"}],
                                  {HS + "HW1": "Front Desk", HS + "HW2": "Soundbar"}),
        "10.0.0.12:5555": new_tv("SmartTV", "Hisense", "14", [{"id": "com.mediatek.tvinput/.hdmi.HDMIInputService/HDMI100004", "state": "connected"},
                                                              {"id": "com.mediatek.tvinput/.hdmi.HDMIInputService/HDMI100005", "state": "standby"}]),
        "10.0.0.13:5555": new_tv("Smart TV", "TCL", "12", hdmi_inputs("com.tcl.tvinput/.TvPassThroughService/HW", 2) + [{"id": "com.tcl.tvinput/.TunerInputService/HW2", "state": "connected"}],
                                  app="com.tcl.tv/com.tcl.player.TVActivity"),
        "10.0.0.14:5555": new_tv("SmartTV 4K", "Hisense", "11", hdmi_inputs(HS + "HW", 2), state="unauthorized"),
        "10.0.0.15:5555": dict(new_tv("SmartTV", "Hisense", "11", hdmi_inputs(HS + "HW", 2)), reachable=False),
    }


class Fleet:
    def __enter__(self):
        self.f = open(STATE + ".lock", "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        try:
            self.d = json.load(open(STATE))
        except Exception:
            self.d = seed()
        self.tick()
        return self

    def __exit__(self, *a):
        tmp = STATE + ".tmp"
        json.dump(self.d, open(tmp, "w"), indent=1)
        os.replace(tmp, STATE)
        fcntl.flock(self.f, fcntl.LOCK_UN)

    def tick(self):
        now = time.time()
        for t in self.d.values():
            if t.get("up_at") and now >= t["up_at"]:   # finished rebooting: cold boot
                t.update(up_at=0, reachable=True, awake=True, session=None, top=t["launcher"], boot_at=now)

    def link(self, t):
        if not t["connected"]:
            return None
        if not t["reachable"] or t["up_at"]:
            return "offline"
        return t["auth"]


def sessions_text(t):
    return ("  sessionStateMap: ITvInputSession -> SessionState\n    android.os.Binder@1: com.android.server.tv.TvInputManagerService$SessionState@2\n      inputId: %s\n" % t["session"]
            if t["session"] else "  sessionStateMap: ITvInputSession -> SessionState\n")


def tv_input_dump(t):
    st = {"connected": 0, "standby": 1, "disconnected": 2}
    out = ["TV Input Manager State:", "User Ids (Current user: 0):", "  inputMap: inputId -> TvInputState"]
    for i in t["inputs"]:
        out.append("    %s: info: TvInputInfo{id=%s, pkg=x, service=y}; state: %d" % (i["id"], i["id"], st[i["state"]]))
    out.append(sessions_text(t).rstrip("\n"))
    out.append("  mHardwareInputIdMap: deviceId -> inputId")
    return "\n".join(out) + "\n"


def top_text(t):
    if not t["awake"] or not t["top"]:
        return ""
    return "    mResumedActivity: ActivityRecord{1 u0 %s t1}\n" % t["top"]


def probe(t):
    return "  mWakefulness=%s\n==\n%s==\n%s" % ("Awake" if t["awake"] else "Asleep",
                                              ("      inputId: %s\n" % t["session"]) if t["session"] else "", top_text(t))


def labels_value(t):
    if not t["labels"]:
        return "null"
    return ":".join("%s,%s" % (urllib.parse.quote(k, safe=""), urllib.parse.quote(v)) for k, v in t["labels"].items())


def pkgs(t, flag):
    names = []
    for n, p in sorted(t["packages"].items()):
        if flag == "-d" and not p["disabled"]:
            continue
        if flag == "-3" and p["system"]:
            continue
        if flag == "-s" and not p["system"]:
            continue
        names.append("package:" + n)
    return "\n".join(names) + ("\n" if names else "")


def shell(t, cmd):
    """Return (rc, stdout). Matches the commands the manager issues plus common ones."""
    cmd = cmd.strip()
    m = re.match(r"input keyevent (\S+)$", cmd)
    if m:
        k = m.group(1)
        if k == "KEYCODE_WAKEUP":
            if not t["awake"]:
                t.update(awake=True, session=None, top=t["launcher"])
        elif k == "KEYCODE_SLEEP":
            t.update(awake=False, session=None)
        elif k == "KEYCODE_HOME" and t["awake"]:
            t["top"] = t["launcher"]
        return 0, ""
    if cmd.startswith("(dumpsys power"):
        return 0, probe(t)
    if "getprop ro.product.manufacturer" in cmd and "echo ==" in cmd:
        return 0, "%s\n==\n%s\n==\n%s\n==\n%s\n==\n%s\n" % (t["mfr"], t["model"], t["android"], labels_value(t), t["launcher"])
    if cmd.startswith("dumpsys tv_input"):
        return 0, tv_input_dump(t)
    m = re.match(r"am start -a android.intent.action.VIEW -d '([^']+)'", cmd)
    if m:
        iid = urllib.parse.unquote(m.group(1).rsplit("/passthrough/", 1)[-1])
        if not any(i["id"] == iid for i in t["inputs"]):
            return 0, "Error: Activity not started, unable to resolve Intent\n"
        t.update(session=iid, top=t["tvapp"], awake=True)
        return 0, "Starting: Intent { act=android.intent.action.VIEW dat=content://android.media.tv/passthrough/%s }\n" % iid
    m = re.match(r"pm list packages\s*(-\w)?$", cmd)
    if m:
        return 0, pkgs(t, m.group(1))
    m = re.match(r"pm (enable|disable-user|uninstall|clear)(?: --user 0)? (\S+)$", cmd)
    if m:
        op, pkg = m.groups()
        p = t["packages"].get(pkg)
        if not p:
            return 0, "Error: package %s not found\n" % pkg if op != "uninstall" else "Failure [DELETE_FAILED_INTERNAL_ERROR]\n"
        if op == "enable":
            p["disabled"] = False
            return 0, "Package %s new state: enabled\n" % pkg
        if op == "disable-user":
            p["disabled"] = True
            return 0, "Package %s new state: disabled-user\n" % pkg
        if op == "uninstall":
            del t["packages"][pkg]
            return 0, "Success\n"
        return 0, "Success\n"
    m = re.match(r"am force-stop (\S+)$", cmd)
    if m:
        return 0, ""
    if cmd.startswith("monkey -p"):
        m = re.search(r"monkey -p (\S+)", cmd)
        p = t["packages"].get(m.group(1))
        if p and not p["disabled"]:
            t["top"] = m.group(1) + "/.MainActivity"
            return 0, "Events injected: 1\n"
        return 0, "** No activities found to run, monkey aborted.\n"
    if cmd == "getprop":
        return 0, "".join("[%s]: [%s]\n" % kv for kv in [
            ("ro.product.manufacturer", t["mfr"]), ("ro.product.model", t["model"]), ("ro.build.version.release", t["android"]),
            ("ro.build.version.sdk", "30"), ("ro.serialno", "FAKE" + t["model"].replace(" ", "")), ("persist.sys.timezone", "America/Anchorage")])
    if cmd.startswith("getprop "):
        return 0, {"ro.product.model": t["model"], "ro.product.manufacturer": t["mfr"], "ro.build.version.release": t["android"]}.get(cmd.split()[1], "") + "\n"
    if cmd.startswith("df -k /data"):
        return 0, "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-3 12000000 5200000 6800000 44% /data\n"
    if cmd == "cat /proc/meminfo":
        return 0, "MemTotal:        2000000 kB\nMemFree:          200000 kB\nMemAvailable:     900000 kB\n"
    if cmd == "cat /proc/uptime":
        return 0, "%.2f 100.00\n" % (time.time() - t["boot_at"])
    if cmd.startswith("ip -f inet"):
        return 0, "3: wlan0: <UP>\n    inet %s/24 scope global wlan0\n" % t.get("ip", "10.0.0.99")
    if cmd == "uptime":
        return 0, " up %d min\n" % ((time.time() - t["boot_at"]) / 60)
    if cmd.startswith("dumpsys power"):
        return 0, "  mWakefulness=%s\n" % ("Awake" if t["awake"] else "Asleep")
    if cmd.startswith("settings get"):
        return 0, "null\n"
    return 127, "/system/bin/sh: %s: inaccessible or not found\n" % cmd.split()[0]


def run(argv):
    with Fleet() as F:
        args = list(argv)
        if args[:1] == ["devices"]:
            lines = ["List of devices attached"]
            for a, t in F.d.items():
                s = F.link(t)
                if s:
                    lines.append("%s\t%s" % (a, s))
            return 0, "\n".join(lines) + "\n", b""
        if args[:1] == ["connect"]:
            a = args[1] if ":" in args[1] else args[1] + ":5555"
            t = F.d.get(a)
            if not t or not t["reachable"] or t["up_at"]:
                return 1, "failed to connect to '%s': Connection timed out\n" % a, b""
            t["connected"] = True
            return 0, ("connected to %s\n" % a) if t["auth"] == "device" else ("failed to authenticate to %s\n" % a), b""
        if args[:1] == ["disconnect"]:
            t = F.d.get(args[1] if ":" in args[1] else args[1] + ":5555")
            if t:
                t["connected"] = False
            return 0, "disconnected\n", b""
        if args[:1] == ["-s"] and len(args) >= 3:
            a, op, rest = args[1], args[2], args[3:]
            t = F.d.get(a)
            link = F.link(t) if t else None
            if link is None:
                return 1, "error: device '%s' not found\n" % a, b""
            if link != "device":
                return 1, "error: device %s\n" % link, b""
            if op == "shell":
                rc, out = shell(t, " ".join(rest))
                return rc, out, b""
            if op == "exec-out" and rest[:1] == ["screencap"]:
                return 0, b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, b""
            if op == "install":
                return 0, "Performing Streamed Install\nSuccess\n", b""
            if op == "reboot":
                t.update(up_at=time.time() + 8, awake=False, session=None)
                return 0, "", b""
        return 1, "unsupported fake adb command: %s\n" % " ".join(args), b""


def ctl(args):
    with Fleet() as F:
        cmd = args[0]
        if cmd == "seed":
            F.d = seed()
        elif cmd == "list":
            for a, t in F.d.items():
                print(a, F.link(t), "awake" if t["awake"] else "asleep", t["session"] or "-", t["top"])
        elif cmd == "set":
            for kv in args[2:]:
                k, v = kv.split("=", 1)
                F.d[args[1]][k] = json.loads(v)
        elif cmd == "power":
            t = F.d[args[1]]
            on = args[2] == "on"
            t.update(reachable=on, awake=on, session=None, top=t["launcher"], boot_at=time.time() if on else t["boot_at"])
        elif cmd == "approve":
            F.d[args[1]]["auth"] = "device"
        elif cmd == "wake":
            shell(F.d[args[1]], "input keyevent KEYCODE_WAKEUP")
        elif cmd == "standby":
            shell(F.d[args[1]], "input keyevent KEYCODE_SLEEP")
        elif cmd == "input":
            print(shell(F.d[args[1]], "am start -a android.intent.action.VIEW -d 'content://android.media.tv/passthrough/%s'" % urllib.parse.quote(args[2], safe=""))[1].strip())


if __name__ == "__main__":
    if sys.argv[1:2] == ["ctl"]:
        ctl(sys.argv[2:])
    else:
        rc, out, err = run(sys.argv[1:])
        if isinstance(out, bytes):
            sys.stdout.buffer.write(out)
        else:
            sys.stdout.write(out)
        sys.stdout.flush()
        sys.exit(rc)
