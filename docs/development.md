# Development

```bash
python3 -m unittest discover -s . -p "test_*.py" -t .     # 28 tests, about 5 s, no hardware
python3 tests/e2e_ui.py                                    # browser test; pip install playwright
```

Live view tests (`tests/test_live.py`) run real ffmpeg against a simulated `screenrecord` and are skipped if ffmpeg is missing.
`tools/fake_adb.py` has three capture modes: `10.0.0.11` supports everything, `10.0.0.12` only `screenrecord`, `10.0.0.13` nothing.

Test layers:

* `tests/test_parsers.py`: parsers and validators, using real `dumpsys` captures as fixtures.
* `tests/test_monitor.py`: the restore state machine against a scripted fake adb.
* `tests/test_api.py`: the HTTP server on an ephemeral port (auth, CSRF, validation, traversal, bulk, install, schedules).
* `tests/test_fake_fleet.py`: the real `Monitor` and `Adb` classes driving `tools/fake_adb.py` through standby, power loss, reboot and "user opened an app" scenarios.
* `tests/e2e_ui.py`: Chromium drives the real UI against a throwaway manager and the fake fleet, and fails if a literal
  `null`/`undefined` ever appears on a page.
* `tests/e2e_live_webkit.py`: the live view in WebKit. Safari's `fetch()` cannot read `multipart/x-mixed-replace` ("Load failed"), so
  the viewer requests `?raw=1` and falls back to an `<img>`; only a WebKit run catches regressions there
  (`playwright install webkit`, plus `playwright install-deps webkit` on Linux).

## The fake fleet

`tools/fake_adb.py` is a stand-in `adb` binary with five simulated TVs (two Hisense generations, a TCL, an
unapproved one, an unreachable one). It keeps state in `FAKE_ADB_STATE` (a JSON file) and never touches a
network. Control it with `ctl`:

```bash
export FAKE_ADB_STATE=/tmp/fleet.json
python3 tools/fake_adb.py ctl seed                              # reset
python3 tools/fake_adb.py ctl list
python3 tools/fake_adb.py ctl power 10.0.0.11:5555 off|on      # plug / unplug
python3 tools/fake_adb.py ctl approve 10.0.0.14:5555           # accept the on-TV prompt
python3 tools/fake_adb.py ctl wake|standby 10.0.0.11:5555
python3 tools/fake_adb.py ctl input 10.0.0.11:5555 <input-id>
python3 tools/fake_adb.py ctl set 10.0.0.11:5555 'top="com.netflix.ninja/.MainActivity"'
TVM_ADB=$PWD/tools/fake_adb.py TVM_DATA=/tmp/tvm-demo TVM_PORT=8431 TVM_POLL=1 python3 -m tvmanager
```

`web/sso.js` redirects signed-out visitors to the Services Hub. Add `?nosso` to the URL to see the manager's own
login page (the browser tests do this).

To support a new command, add a branch in `shell()`; to model a new TV, add an entry in `seed()`.

## Adding support for a new TV brand

1. Capture `dumpsys tv_input`, `dumpsys activity activities | grep -E "mResumed|topResumed"` and
   `dumpsys power | grep mWakefulness` while the TV is on a known input and on its launcher.
2. Add them as fixtures in `tests/test_parsers.py` and make the parsers handle any difference.
3. If the input id doesn't match `PASSTHRU` in `parsers.py`, extend it.
4. Verify that `am start -a android.intent.action.VIEW -d content://android.media.tv/passthrough/<id>` switches the input.

## Theming

`web/style.css` defines Material 3 tonal roles (`--primary`, `--surface-container`, ...) as `oklch()` values
derived from one hue variable `--h`, declared three times: light, dark via `prefers-color-scheme`, and dark via
`[data-theme="dark"]`. To retune the palette change the lightness/chroma numbers there; to add an accent
option add a pair to `HUES` in `web/app.js`. Icons are inline Material path data in `ICONS`, built with
`createElementNS` (no `innerHTML`). The only bundled asset is the Roboto Flex variable font in `web/fonts/`.

## Conventions

Standard library only on the server; plain JS in the UI; every dynamic string rendered through `textContent`;
every value that reaches a shell command validated by an allow-list regex in `parsers.py`.
