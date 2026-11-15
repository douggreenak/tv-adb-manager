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
| `GET /api/devices` | | `{devices:[…], groups:[…]}`; each device has `id, name, addr, group, status, awake, input, input_name, top, model, manufacturer, android, last_seen, restore:{enabled,last,last_name}` |
| `POST /api/devices` | `{name, addr, group}` | 201 with the device; `addr` defaults to port 5555 |
| `PUT /api/devices/<id>` | any of `name, addr, group, restore:{enabled,last}` | updated device |
| `DELETE /api/devices/<id>` | | |
| `GET /api/devices/<id>/info` | | props, `storage_kb`, `memory_kb`, `uptime_s`, `ip` |
| `GET /api/devices/<id>/inputs` | | `{inputs:[{id,name,state,passthrough,active}]}` |
| `GET /api/devices/<id>/packages?filter=user\|system\|disabled\|all` | | `{packages:[{name,disabled}]}` |
| `POST /api/devices/<id>/packages/<pkg>` | `{action}` = `enable\|disable\|uninstall\|stop\|clear\|launch` | `{ok, output}` |
| `POST /api/devices/<id>/install?name=app.apk` | raw APK bytes (`application/octet-stream`) | `{ok, output}` |
| `GET /api/devices/<id>/screenshot` | | `image/png`, or 502 if the TV can't capture |
| `POST /api/devices/<id>/shell` | `{cmd}` | `{rc, output}` |

`status` is one of `online`, `asleep`, `offline`, `unauthorized`, `unknown`.

### Actions

`POST /api/devices/<id>/action` with `{action, ...}`:

| action | extra fields | effect |
|---|---|---|
| `wake`, `sleep`, `home`, `back` | | key events |
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
