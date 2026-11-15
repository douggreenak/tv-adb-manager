"""Live screen view: `adb screenrecord` (H.264) -> ffmpeg (JPEG) -> HTTP multipart stream.

Why transcode on the server: browsers decode H.264 only over HTTPS (WebCodecs) or with heavy JS decoders, while
JPEG frames work everywhere over plain HTTP.

Why not one long-running ffmpeg: TV encoders send a frame only when the picture changes, and ffmpeg's raw-H.264
reader holds back the latest frame until more data arrives, so a static screen would never appear. Instead we keep
the H.264 since the last key frame and decode that short sequence in a fresh ffmpeg whenever the stream goes quiet
(or a frame interval passes), which flushes the final frame. Only the newest frame is ever kept, so a slow
client drops frames instead of lagging.
"""
import shutil
import subprocess
import threading
import time
from collections import deque

PRESETS = {
    "low":    {"size": "854x480",   "fps": 4,  "q": 9, "bitrate": 2000000},
    "medium": {"size": "1280x720",  "fps": 6,  "q": 6, "bitrate": 4000000},
    "high":   {"size": "1920x1080", "fps": 10, "q": 4, "bitrate": 8000000},
}
MAX_SECONDS = 30 * 60      # a forgotten tab must not stream forever
MAX_SESSIONS = 4
IDLE = 0.08                # seconds of silence after which the latest frame is considered complete
MAX_GOP_BYTES = 4 << 20    # beyond this we only render once a second (heavy video the TVs rarely allow anyway)


def ffmpeg_path():
    return shutil.which("ffmpeg")


class LiveError(Exception):
    pass


def nal_types(buf, start=0):
    """[(offset_of_start_code, nal_type)] for every Annex-B start code at or after `start`."""
    out, i, n = [], buf.find(b"\x00\x00\x01", start), len(buf)
    while 0 <= i < n - 3:
        out.append((i, buf[i + 3] & 0x1F))
        i = buf.find(b"\x00\x00\x01", i + 3)
    return out


class LiveSession:
    def __init__(self, source_argv, preset, ffmpeg_bin, max_seconds=MAX_SECONDS):
        self.source_argv, self.preset, self.ffmpeg_bin, self.max_seconds = source_argv, preset, ffmpeg_bin, max_seconds
        self.stopped = threading.Event()
        self.cond = threading.Condition()
        self.seq, self.frame = 0, None
        self.errors = {"tv": deque(maxlen=12), "ffmpeg": deque(maxlen=12)}
        self.started = time.time()
        self.bytes_in = 0                 # raw video bytes received from the TV
        self.csd = b""                    # SPS/PPS: everything before the first key frame
        self.gop = bytearray()            # H.264 since the last key frame (what a decoder needs)
        self._scan_from = 0
        self._dirty = False               # data arrived that has not been rendered yet
        self._last_data = 0.0
        self._last_render = 0.0
        self._src = None

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        threading.Thread(target=self._feed, daemon=True).start()
        threading.Thread(target=self._render_loop, daemon=True).start()

    def stop(self):
        self.stopped.set()
        try:
            if self._src and self._src.poll() is None:
                self._src.kill()
        except OSError:
            pass
        with self.cond:
            self.cond.notify_all()

    def _drain(self, stream, who):
        try:
            for line in iter(stream.readline, b""):
                t = line.decode("utf-8", "replace").strip()
                if t:
                    self.errors[who].append(t)
        except (OSError, ValueError):
            pass

    # ---- TV side: collect H.264; screenrecord stops after 3 minutes, so restart it ----
    def _feed(self):
        try:
            while not self.stopped.is_set() and time.time() - self.started < self.max_seconds:
                src = self._src = subprocess.Popen(self.source_argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                threading.Thread(target=self._drain, args=(src.stderr, "tv"), daemon=True).start()
                t0, n = time.time(), 0
                while True:
                    data = src.stdout.read1(65536)
                    if not data:
                        break
                    n += len(data)
                    self._on_data(data)
                src.wait()
                if n == 0 or time.time() - t0 < 2:   # failed straight away: do not loop
                    break
        except (OSError, ValueError):
            pass
        finally:
            with self.cond:
                self.cond.notify_all()
            time.sleep(1.5)                           # let a last frame render, then end the session
            self.stop()

    def _on_data(self, data):
        with self.cond:
            self.bytes_in += len(data)
            self.gop += data
            tail = max(0, self._scan_from - 3)
            for off, t in nal_types(self.gop, tail):
                if t == 5:                            # key frame: a decoder can start here
                    if not self.csd:
                        self.csd = bytes(self.gop[:off])
                    start = off - 1 if off > 0 and self.gop[off - 1] == 0 else off     # 4-byte start code
                    del self.gop[:start]
                    self._scan_from = 0
                    break
            else:
                self._scan_from = len(self.gop)
            self._dirty = True
            self._last_data = time.time()
            self.cond.notify_all()

    # ---- decode side -----------------------------------------------------
    def _render_loop(self):
        interval = 1.0 / self.preset["fps"]
        while not self.stopped.is_set():
            with self.cond:
                while not self.stopped.is_set():
                    now = time.time()
                    if self._dirty and self.csd:
                        quiet = now - self._last_data >= IDLE
                        due = now - self._last_render >= (interval if len(self.gop) < MAX_GOP_BYTES else 1.0)
                        if quiet or due:
                            break
                        self.cond.wait(max(0.01, min(IDLE - (now - self._last_data), interval - (now - self._last_render))))
                    else:
                        self.cond.wait(0.25)
                if self.stopped.is_set():
                    return
                payload = self.csd + bytes(self.gop)
                self._dirty = False
            self._last_render = time.time()
            jpeg = self._decode(payload)
            if jpeg:
                with self.cond:
                    self.seq += 1
                    self.frame = jpeg
                    self.cond.notify_all()

    def _decode(self, payload):
        """Decode a self-contained H.264 sequence; EOF makes ffmpeg flush, so the final frame always comes out."""
        w = self.preset["size"].split("x")[0]
        argv = [self.ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "h264", "-i", "pipe:0",
                "-vf", "scale=%s:-2" % w, "-pix_fmt", "yuvj420p", "-q:v", str(self.preset["q"]),
                "-f", "mpjpeg", "-boundary_tag", "frame", "pipe:1"]
        try:
            p = subprocess.run(argv, input=payload, capture_output=True, timeout=15)
        except (subprocess.TimeoutExpired, OSError) as e:
            self.errors["ffmpeg"].append("decode failed: %s" % e)
            return None
        for line in p.stderr.decode("utf-8", "replace").splitlines()[-3:]:
            if line.strip():
                self.errors["ffmpeg"].append(line.strip())
        return self._last_jpeg(p.stdout)

    @staticmethod
    def _last_jpeg(data):
        """The newest complete JPEG in an mpjpeg stream."""
        last, pos = None, 0
        while True:
            he = data.find(b"\r\n\r\n", pos)
            if he < 0:
                break
            head = data[pos:he].lower()
            i = head.find(b"content-length:")
            if i < 0:
                pos = he + 4
                continue
            n = int(head[i + 15:].split(b"\r\n")[0].strip() or 0)
            if len(data) < he + 4 + n:
                break
            last = data[he + 4:he + 4 + n]
            pos = he + 4 + n
        return last

    # ---- consumer ------------------------------------------------------
    def next_frame(self, after_seq, timeout, repeat=False):
        """Block until a frame newer than after_seq exists. Returns (seq, jpeg), or (after_seq, None) when the session
        is over or (without repeat) on timeout. With repeat=True a timeout re-sends the latest frame as a keep-alive."""
        end = time.time() + timeout
        with self.cond:
            while self.seq <= after_seq:
                left = end - time.time()
                if self.stopped.is_set():
                    return after_seq, None
                if left <= 0:
                    return (self.seq, self.frame) if repeat and self.frame else (after_seq, None)
                self.cond.wait(left)
            return self.seq, self.frame

    def error_text(self):
        """The TV's own complaint if it gave one, otherwise ffmpeg's (the TV's is the useful one)."""
        lines = list(self.errors["tv"]) or list(self.errors["ffmpeg"])
        return " | ".join(lines[-3:])


class LiveManager:
    """At most one live session per TV, and a global cap."""

    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}

    def open(self, key, source_argv, preset, ffmpeg_bin):
        with self.lock:
            old = self.sessions.pop(key, None)
            if old:
                old.stop()
            if len(self.sessions) >= MAX_SESSIONS:
                raise LiveError("Too many live views are open (max %d). Close one first." % MAX_SESSIONS)
            s = LiveSession(source_argv, preset, ffmpeg_bin)
            self.sessions[key] = s
        s.start()
        return s

    def release(self, key, session):
        session.stop()
        with self.lock:
            if self.sessions.get(key) is session:
                del self.sessions[key]

    def count(self):
        with self.lock:
            return len(self.sessions)
