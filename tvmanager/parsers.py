"""Pure functions that parse `dumpsys`/`getprop`/`pm` output. Kept free of I/O for testing."""
import re
import urllib.parse

# Input ids that carry a picture straight from a port (HDMI etc.) rather than a tuner/app.
PASSTHRU = re.compile(r"(hdmi|passthrough|composite|component|vga|scart)", re.I)
INPUT_STATES = {0: "connected", 1: "standby", 2: "disconnected"}


def parse_wakefulness_raw(text):
    """'Awake', 'Dreaming' (screensaver: screen lit), 'Asleep', 'Dozing', or None."""
    m = re.search(r"mWakefulness=(\w+)", text or "")
    return m.group(1) if m else None


def parse_wakefulness(text):
    """True awake, False asleep/dozing, None if unknown."""
    m = re.search(r"mWakefulness=(\w+)", text or "")
    if not m:
        return None
    return m.group(1) == "Awake"


def parse_sessions(text):
    """Input ids with an active TV session, from `dumpsys tv_input` (sessionStateMap)."""
    return re.findall(r"^\s*inputId:\s*(\S+)\s*$", text or "", re.M)


def is_passthrough(input_id):
    return bool(PASSTHRU.search(input_id)) and "uner" not in input_id


def pick_passthrough(ids):
    return next((i for i in ids if is_passthrough(i)), None)


def parse_top_activity(text):
    """`pkg/Activity` of the resumed activity, or None."""
    m = re.search(r"(?:mResumedActivity|topResumedActivity)[^\n]*? u\d+ (\S+?)/(\S+) ", text or "")
    if not m:
        return None
    return m.group(1) + "/" + m.group(2)


def parse_inputs(text):
    """List of {id, state} for every TV input the framework knows (first occurrence wins)."""
    out, seen = [], set()
    for m in re.finditer(r"^\s+(\S+): info: TvInputInfo\{.*?\}; state: (\d+)", text or "", re.M):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append({"id": m.group(1), "state": INPUT_STATES.get(int(m.group(2)), "unknown")})
    if not out:  # older/vendor dumps without state
        for m in re.finditer(r"^\s+(\S+): TvInputInfo\{", text or "", re.M):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                out.append({"id": m.group(1), "state": "unknown"})
    return out


def parse_labels(value):
    """Parse Settings.Secure tv_input_custom_labels: `id,label:id,label` (both url-encoded)."""
    labels = {}
    if not value or value == "null":
        return labels
    for part in value.split(":"):
        if "," in part:
            k, v = part.split(",", 1)
            labels[urllib.parse.unquote(k)] = urllib.parse.unquote(v).strip()
    return labels


def short_input_name(input_id, labels=None):
    if labels and input_id in labels and labels[input_id]:
        return labels[input_id]
    seg = input_id.rsplit("/", 1)[-1]
    return seg or input_id


def parse_packages(text):
    return sorted({l.split(":", 1)[1].strip() for l in (text or "").splitlines() if l.startswith("package:")})


def parse_props(text):
    """Parse `getprop` lines `[key]: [value]`."""
    return dict(re.findall(r"^\[(.+?)\]: \[(.*?)\]$", text or "", re.M))


def parse_df(text):
    """Return (total_kb, used_kb) from the last line of `df -k`."""
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    f = lines[-1].split()
    try:
        return int(f[1]), int(f[2])
    except (IndexError, ValueError):
        return None


def parse_meminfo(text):
    d = {}
    for m in re.finditer(r"^(MemTotal|MemAvailable):\s+(\d+) kB", text or "", re.M):
        d[m.group(1)] = int(m.group(2))
    return d


SAFE_PKG = re.compile(r"^[A-Za-z][\w]*(\.[\w]+)+$")
SAFE_KEY = re.compile(r"^(KEYCODE_[A-Z0-9_]+|\d{1,3})$")
SAFE_ADDR = re.compile(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$")
SAFE_INPUT = re.compile(r"^[\w.$/\-]+$")
