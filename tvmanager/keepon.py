"""Keep-on: stop a TV from powering itself off or sleeping until the manager is told to (schedules, Standby button).

Android keeps these timers in system settings, so they can be read and set over ADB:
  secure  sleep_timeout             "Energy saver: automatically turn off when inactive" (hours; fully powers the TV off)
  system  screen_off_timeout        display off / screensaver timer
  global  stay_on_while_plugged_in  keep the screen on while on mains power
  global  no_signal_auto_power_off  TCL/Hisense "No signal auto power off" (only where the TV has it)
"""
NEVER = "2147483647"

SPECS = [("secure", "sleep_timeout", NEVER),
         ("system", "screen_off_timeout", NEVER),
         ("global", "stay_on_while_plugged_in", "7")]
OPTIONAL = [("global", "no_signal_auto_power_off", "0")]       # only changed if the TV has the setting

KEYS = [(t, k) for t, k, _ in SPECS + OPTIONAL]
READ_CMD = "; ".join("echo %s.%s=$(settings get %s %s)" % (t, k, t, k) for t, k in KEYS)
LABEL = {"sleep_timeout": "turn-off timer", "screen_off_timeout": "screen-off timer",
         "stay_on_while_plugged_in": "stay on", "no_signal_auto_power_off": "no-signal power-off"}


def parse(out):
    """'secure.sleep_timeout=123' lines -> {'secure.sleep_timeout': '123' | None}"""
    cur = {}
    for line in (out or "").splitlines():
        name, sep, val = line.strip().partition("=")
        if sep and name in {"%s.%s" % tk for tk in KEYS}:
            cur[name] = None if val.strip() in ("", "null") else val.strip()
    return cur


def plan(cur):
    """[(table, key, wanted)] for settings that differ from keep-on."""
    out = []
    for t, k, v in SPECS:
        if "%s.%s" % (t, k) in cur and cur["%s.%s" % (t, k)] != v:
            out.append((t, k, v))
    for t, k, v in OPTIONAL:
        c = cur.get("%s.%s" % (t, k))
        if c is not None and c != v:
            out.append((t, k, v))
    return out


def put_cmd(changes):
    return "; ".join("settings put %s %s %s" % c for c in changes)


def revert_cmd(prev):
    parts = []
    for name, val in prev.items():
        t, k = name.split(".", 1)
        parts.append("settings delete %s %s" % (t, k) if val is None else "settings put %s %s %s" % (t, k, val))
    return "; ".join(parts)


def describe(changes, cur):
    return ", ".join("%s %s→%s" % (LABEL.get(k, k), cur.get("%s.%s" % (t, k)) or "default",
                                    "never" if v == NEVER else v) for t, k, v in changes)
