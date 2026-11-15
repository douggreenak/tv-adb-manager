# Architecture

```
 browser ──HTTP/JSON──▶ tvmanager.server ──▶ Store (devices.json, schedules.json)
                              │
                              ├──▶ Monitor    polls every TV, tracks state, restores inputs
                              ├──▶ Scheduler  fires timed actions
                              └──▶ Adb        subprocess wrapper around the `adb` binary ──▶ TVs
```

| Module | Role |
|---|---|
| `adb.py` | The only code that runs `adb`. Methods: `devices`, `connect`, `shell`, `screencap`, `install`, `reboot`. Timeouts everywhere. Tests substitute a fake with the same methods. |
| `parsers.py` | Pure functions over `dumpsys`/`getprop`/`pm` output, plus the validators (`SAFE_PKG`, `SAFE_KEY`, `SAFE_ADDR`, `SAFE_INPUT`). No I/O. |
| `monitor.py` | A loop calls `adb devices` once, then polls each registered TV on a thread pool. Reconnects with back-off, reads state with one combined shell call, remembers inputs and runs the restore logic. |
| `store.py` | Atomic JSON files for devices and schedules, and the activity log. |
| `scheduler.py` | Checks schedules every 20 s and fires on a matching minute. |
| `auth.py` | scrypt-hashed password, in-memory sessions, login throttling. |
| `server.py` | Stdlib `ThreadingHTTPServer`, a small route table, static file serving with path-traversal protection and security headers. |

## One poll, per device

```
adb devices says: unauthorized → status "Needs approval", retry connect every 30 s
                  missing/offline → status "Offline", retry connect every 10 s
                  device → run PROBE:
    dumpsys power              → wakefulness (Awake / Asleep)
    dumpsys tv_input           → sessionStateMap: which input is active
    dumpsys activity           → resumed activity (mResumedActivity or topResumedActivity on A14)
```

Static details (manufacturer, model, Android version, the TV's custom input names, the home package) are
read once per connection from `getprop` and `Settings.Secure tv_input_custom_labels`.

## Live view pipeline

```
TV: screenrecord --output-format=h264  ->  adb exec-out  ->  ffmpeg (h264 -> JPEG, scaled, fps-limited)  ->  server keeps
the newest frame  ->  HTTP multipart stream  ->  browser parses frames and paints an <img>
```

`tvmanager/live.py` owns the pipeline. `screenrecord` stops after 3 minutes, so it is restarted into the same ffmpeg
(each run begins with fresh SPS/PPS and a key frame). The server transcodes because browsers only decode H.264 over
HTTPS (WebCodecs), while JPEG works everywhere over plain HTTP. The TV's own stderr is kept separate from ffmpeg's so
the message shown to the user is the TV's ("unable to get display capture"), not ffmpeg jargon.

## Restore state machine

```
awake on passthrough input ─▶ remember it (store.devices[].restore.last)
asleep ─▶ awake                    ┐
offline/unauthorized ─▶ reachable  ┴▶ schedule restore in 3 s
        ▼ (3 s later, still awake)
   on an input?            → nothing to do
   on launcher/home pkg?   → am start -a VIEW -d content://android.media.tv/passthrough/<id>
   in another app?         → leave it alone
```

The first time the manager sees a TV it never restores, so restarting the manager is harmless.

## Why it runs on a server and not on the TV

The first attempt was an on-device Android app (`experiments/android-last-input-app`). Hisense firmware
SIGKILLs background processes when the TV enters standby, and the accessibility service is then marked
crashed and never rebound, so nothing is alive to notice the wake. ADB stays reachable while the TV
sleeps, so the server can.

## Vendor quirks handled

* Android 11/12 Hisense report `mResumedActivity`; Android 14 reports `topResumedActivity`.
* TV input ids differ per vendor (`HdmiTvInputService/HW5`, `HDMIInputService/HDMI100004`,
  `TvPassThroughService/HW15`); tuner inputs are excluded from restore because they need a channel.
* Custom input names live in `tv_input_custom_labels` as URL-encoded `id,label` pairs separated by `:`.
* `grep` as the last command of the probe would exit non-zero on a miss, so the probe ends with `; true`.
