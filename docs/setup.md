# Setup guide

## 1. Prepare the TVs

On each TV:

1. **Settings → Device Preferences → About**: click *Build* seven times to unlock Developer options.
2. **Developer options**: turn on **USB debugging**. On many sets this also enables ADB over the network
   on port 5555; if your TV has a separate *Network debugging* / *ADB over network* switch, enable it too.
3. Give the TV a fixed IP address (DHCP reservation on your router is best).

Check from the server: `adb connect <tv-ip>:5555`. The TV shows *Allow USB debugging?*; tick **Always allow
from this computer** and press Allow. `adb devices` should then list it as `device`. (`unauthorized`
means the prompt is still pending.)

## 2. Install the manager

Requirements: Python 3.9+ and `adb` (`sudo apt install adb`, or Google's platform-tools).

```bash
git clone https://github.com/douggreenak/tv-adb-manager
cd tv-adb-manager
python3 -m tvmanager
```

It listens on `0.0.0.0:8420`. The first start prints a generated password, which is also stored hashed in
`data/auth.json`. To choose your own, start with `TVM_PASSWORD=...` or change it in **Settings**.

Optional: for the live **Screen** view install ffmpeg (`sudo apt install ffmpeg`). Everything else works without it.

## 3. Run it as a service

Edit `User=`, `WorkingDirectory=` and `ExecStart=` in `deploy/tv-adb-manager.service`, then:

```bash
sudo cp deploy/tv-adb-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tv-adb-manager
journalctl -u tv-adb-manager -f
```

### What the service does for you

| Situation | What happens |
|---|---|
| The server boots | systemd starts it after the network is up (`enable` makes this permanent) |
| The process crashes or is killed | restarted after 3 seconds, with no limit on how many times |
| The process hangs (alive but frozen) | it stops sending health pings (a ping needs the poller ticking *and* the web server answering); systemd declares a watchdog timeout after 60 s, kills it and restarts it |
| A TV goes offline | retried every 10 s, and its input is restored when it returns |
| `adb` dies | its server is respawned on the next poll |
| Weeks of uptime | the activity log rotates at 2 MB (one old file kept); devices, schedules and the password hash live in `data/` and survive restarts |

It runs as a system service under systemd, so nothing depends on anyone being logged in. Check it with
`systemctl status tv-adb-manager` (the *Status:* line shows the port it serves).

The service user needs a home directory where `~/.android/adbkey` can live. TVs authorize that key,
so run the manager as the same user every time, or you will be asked to approve again on every TV.

## 4. Add your TVs

*Devices → + Add device*, enter name, IP and optional group. Status turns to **On** within a few
seconds. **Needs approval on TV** means the debugging prompt is waiting on the screen.

## 5. Optional: HTTPS

The server speaks plain HTTP. For anything beyond a trusted LAN, bind to localhost
(`TVM_HOST=127.0.0.1`) and put a TLS reverse proxy in front. Example Caddyfile:

```
tvs.example.com {
    reverse_proxy 127.0.0.1:8420
}
```

Large APK uploads need the proxy's request-body limit raised (the manager allows up to 600 MB).

## Upgrading

`git pull` and `sudo systemctl restart tv-adb-manager`. Data in `data/` (devices, schedules, password
hash, activity log) is kept across upgrades.
