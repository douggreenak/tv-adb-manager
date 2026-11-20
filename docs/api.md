# HTTP API

The web UI is a client of this JSON API, so you can script against it too. All `/api` paths except
`/api/session` and `/api/login` need the `tvm_session` cookie. Every non-GET request must carry the header
`X-Requested-With: tvm` (a CSRF guard). Errors are `{"error": "message"}` with a 4xx/5xx status.

```bash
curl -c jar -H 'X-Requested-With: tvm' -H 'Content-Type: application/json' \
     -d '{"password":"..."}' http://server:8420/api/login
curl -b jar http://server:8420/api/devices
curl -b jar -H 'X-Requested-With: tvm' -H 'Content-Type: application/json' \
     -d '{"action":"wake"}' http://server:8420/api/devices/<id>/action
```

## Auth

| Method & path | Body | Notes |
|---|---|---|
| `GET /api/session` | | `{authenticated, version}` (public) |
| `POST /api/login` | `{password}` | sets the cookie; 429 after 8 failures in 5 minutes |
| `POST /api/logout` | | |
| `POST /api/password` | `{current, new}` | new must be 8+ characters; signs out other sessions |

## Devices

| Method & path | Body / query | Returns |
|---|---|---|
| `GET /api/settings`, `PUT /api/settings` | `{keepalive: seconds, 0 = off, 2-300}` | server settings; devices also report `network` (true/false/null) |
| `GET /api/devices` | | `{devices:[…], groups:[…]}`; each device has `id, name, addr, group, status, awake, input, input_name, top, model, manufacturer, android, last_seen, mac, keep_on, restore:{enabled,last,last_name}` |
| `POST /api/devices` | `{name?, addr, group}` | 201 with the device; `addr` defaults to port 5555; an empty `name` follows the TV's own name |
| `PUT /api/devices/<id>` (also `{keep_on: bool}`) | any of `name, addr, group, restore:{enabled,last}` | updated device |
| `DELETE /api/devices/<id>` | | |
| `GET /api/devices/<id>/info` | | props, `storage_kb`, `memory_kb`, `uptime_s`, `ip` |
| `GET /api/devices/<id>/inputs` | | `{inputs:[{id,name,state,passthrough,active}]}` |
| `GET /api/devices/<id>/packages?filter=user\|system\|disabled\|all` | | `{packages:[{name,disabled}]}` |
| `POST /api/devices/<id>/packages/<pkg>` | `{action}` = `enable\|disable\|uninstall\|stop\|clear\|launch` | `{ok, output}` |
| `POST /api/devices/<id>/install?name=app.apk` | raw APK bytes (`application/octet-stream`) | `{ok, output}` |
| `GET /api/devices/<id>/screenshot` | | `image/png`, or 502 if the TV can't capture |
| `POST /api/devices/<id>/shell` | `{cmd}` | `{rc, output}` |

Devices also carry `tv_name` (the name the TV reports, or null) and `auto_name` (true while the manager follows it); `PUT` with a different `name` turns `auto_name` off, and `PUT {auto_name: true}` turns it back on.

`status` is one of `online`, `asleep`, `offline`, `unauthorized`, `unknown`.

### Live screen view

`GET /api/devices/<id>/live?quality=low|medium|high` returns a `multipart/x-mixed-replace` stream of JPEG frames (boundary
`frame`, each part has `Content-Length`), so it also works in a plain `<img src>`. Add `&raw=1` to get the same bytes as
`application/octet-stream`: Safari's `fetch()` refuses `multipart/x-mixed-replace`. Only the newest frame is sent, so a slow
client skips frames instead of lagging. Errors are normal JSON: `409` TV unreachable, `501` ffmpeg missing, `502` the TV
produced no video (the TV's own message is included), `429` too many live views. Sessions end after 30 minutes.

### Actions

`POST /api/devices/<id>/action` with `{action, ...}`:

| action | extra fields | effect |
|---|---|---|
| `wake`, `sleep`, `home`, `back` | | key events. `wake` on an offline TV with a known MAC sends Wake-on-LAN instead |
| `wol` | | send a Wake-on-LAN packet to the device's MAC (`mac` field; set with `PUT /api/devices/<id>` `{mac}`) |
| `key` | `key`: `KEYCODE_*` or a number | any key |
| `reboot` | | `adb reboot` |
| `input` | `input`: full input id | wakes the TV and launches the input |
| `restore` | | launch the remembered input now |
| `connect` | | `adb connect` again |

`POST /api/bulk` takes `{action, ids:[…], …same fields}` and returns `{results:{<id>:{ok,output}}}`.

## Schedules and activity

| Method & path | Body |
|---|---|
| `GET /api/schedules` | |
| `POST /api/schedules`, `PUT /api/schedules/<id>` | `{name, action: wake\|sleep\|reboot\|home\|input, time:"HH:MM", days:[0-6 Mon-Sun], targets:[deviceIds], input, enabled}` |
| `DELETE /api/schedules/<id>` | |
| `GET /api/events` | returns the last 300 events, newest first |
