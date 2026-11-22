# Using the dashboard

## Screen (live view)

The **Screen** tab streams what the TV is showing. Press **Start live view**, pick *Low (480p, 6 fps)*,
*Medium (720p, 10 fps)* or *High (1080p, 15 fps)*, save a snapshot with the camera button, or go fullscreen.
Below the picture is a mini remote (Back, arrows, OK, Home) and a keyboard switch, so you can navigate while watching.

* It works by recording the TV's screen with `screenrecord`, so it needs a TV whose firmware allows it. On the TVs this was
  built against (Hisense/MediaTek and TCL/Realtek) the capture works, but **an HDMI input, and DRM video such as Netflix,
  comes out black** because TVs draw that video on a hardware layer that capture cannot read. The tab warns you when a TV is
  on an HDMI input, and explains when a TV sends no picture at all. A static screen sends one frame and then nothing, so
  the picture only changes when something on screen changes.
* A live view ends by itself after 30 minutes (press **Resume**), at most 4 TVs can be watched at once, and starting and
  ending a view is written to *Activity*.

## Look and feel

The UI follows Google's Material 3 Expressive guidelines: a navigation rail on wide screens that turns into a
bottom bar on phones, one contextual floating action button (Add device / New schedule), large rounded
shapes that morph on press, connected button groups, and avatars whose shape reflects the TV's state.

**Settings → Appearance** chooses *Auto / Light / Dark* and an **accent colour** (blue, teal, green, amber,
rose, violet). The whole palette is generated from that seed hue, in both light and dark. The choice is kept in
the browser, so each person can have their own. Motion respects the OS "reduce motion" setting.

## Device names

Leave the name empty when adding a TV and the manager uses the name set on the TV itself (Android's *device name*, shown in
the TV's own settings). If the TV still has a factory-default name such as "Android TV" or just its model, the last part of
its address is added so identical models can be told apart ("Android TV · .196"). If you rename the TV later, the manager
follows. Type your own name in a device's **Settings** tab and it is kept: the manager never overwrites a name you chose,
and **Use it** switches back to the TV's name.

## When a TV is offline

Cards for TVs that are offline or waiting for approval show what to do instead of dead controls, with a
**Reconnect / Try again** button. The drawer's Remote, Inputs, Apps, Install, Shell and Info tabs show the same
explanation, and refresh themselves the moment the TV comes back. Settings and the power-on options stay usable.

## Wake-on-LAN (TVs that are fully off)

A TV that is fully powered off has no ADB connection, so Wake can't reach it. If the TV has a MAC address on
record, **Wake over network** (offline cards and the drawer) sends a Wake-on-LAN packet, and the normal
**Wake** button and scheduled wakes fall back to it automatically when the TV is offline. Once the TV is up
again, power-on restore puts it back on its last input.

- The MAC is filled in automatically for TVs on the server's own subnet (read from the ARP table when the TV
  connects). Android 11 TVs won't report it over ADB, so for other subnets type it in the TV's **Settings** tab.
- Whether a TV answers depends on the TV: standby usually works, fully off often doesn't, and Wi-Fi-only TVs
  rarely do. Enable "Wake on LAN / Wake on Wi-Fi" or "Quick start" in the TV's own menu. The server sends to
  the broadcast address, the TV's /24 broadcast and the TV itself, so routed subnets need directed broadcasts allowed.
- The manager's own **Standby** button sends the standby key, so it never causes a full power-off.

## Network keepalive

*Settings → Network keepalive* (default every 5 s; Off, 2, 5, 10 or 30 s). The server opens a tiny TCP connection to
each TV at that interval. This keeps a TV in standby on the network, and it tells apart a TV that is **on the
network but whose ADB dropped** (the manager reconnects immediately, and the card says so) from one that has **left
the network** (logged in Activity). It cannot stop a TV that powers itself fully off; for that, change the TV's own
timers (below).

## Keep on

Each TV has a **Keep this TV on** switch (drawer → Settings, on by default). The manager sets the TV's own timers so it
stays on until you use Standby or a schedule, and re-checks them every 10 minutes because the TV's own menus can
rewrite them. It changes only what differs and logs it in Activity ("keep-on: turn-off timer 28800000→never …").

| Setting | Meaning | Set to |
|---|---|---|
| `secure sleep_timeout` | Energy saver, "Automatically turn off when inactive" (fully powers the TV off; 8–24 h by default) | never (2147483647) |
| `system screen_off_timeout` | display-off / screensaver timer | never |
| `global stay_on_while_plugged_in` | keep the screen on on mains power | 7 |
| `global no_signal_auto_power_off` | "No signal auto power off" (TCL, 15 min), only where the TV has it | 0 (Off) |

Turning the switch off puts back the values the TV had before (the originals are remembered). The TV's own
Energy saver menu has no "Never" choice and rewrites unknown values to a listed one, so avoid opening it.
Unplugging the TV, a power cut, or someone long-pressing the remote's power button still turns it off; Wake-on-LAN
and the keepalive help it back.

## Sleep

**Sleep** (next to **Wake** on every card, in the drawer, in the bulk bar and in schedules) sends the sleep key, which
puts the TV to sleep with its screen off while its network stays up, so it can be woken again over ADB or Wake-on-LAN.
It is not the remote's power button, which on these TVs can power the TV fully off. About 25 seconds after every sleep
the manager checks the TV is still reachable and says so in Activity ("asleep and still on the network"); if the TV
dropped off the network instead, Activity flags it so you can use **Wake over network**.

At the end of a calendar block every TV that is on, **including one sitting on its screensaver**, is put to sleep. If the
server was down at the end time, the sleep still happens when it is back up within 10 minutes.

## Fire TV (no ADB)

Fire TVs don't offer ADB, so they are added with **Add device → Fire TV** and paired once: the manager shows a 4-digit PIN on the TV and you type it in. After that the card has Wake, Sleep and Home, the Remote tab works (arrows, OK, back, home, play/pause), and calendar schedules wake and sleep it like any other TV. The manager uses the local API the Fire TV phone remote app uses (HTTPS on port 8080, started through port 8009); the pairing token is stored in `data/devices.json`.

- A Fire TV can't report whether it is on, so its status is what the manager last sent it ("On / Asleep (last command)"). A schedule always sends the wake once at the start of a block.
- Sleep keeps it on the network. The keepalive probes port 8009.
- Not available: screen view, inputs, apps, install, shell, keep-on, Wake-on-LAN. If the TV stops responding, use **Settings → Pair again**.

## Devices

Each card shows the TV's state (**On**, **Asleep**, **Offline**, **Needs approval on TV**), model and
Android version, the active **Input**, the foreground app (**Showing**), the remembered **Last input**
and when it was last seen. Quick buttons send Wake, Sleep and Home. Click a card for the details drawer.

Use the search box and group chips to filter. Tick cards (or *Select all*) to get a bulk bar:
Wake, Sleep, Home, Restore input, Reboot.

## The details drawer

| Tab | What it does |
|---|---|
| **Remote** | D-pad, Back/Home/Menu/Info/Input, volume, media keys, Wake/Sleep/Reboot. A screenshot panel (refresh or auto-refresh every 3 s). Tick *Use keyboard* to drive it with arrows, Enter, Backspace (Back) and H (Home). |
| **Inputs** | Every TV input the framework reports, using the names you set on the TV. **Switch** launches it; **Set as power-on** chooses what gets restored. Also the restore switch, *Restore now* and *Forget*. |
| **Apps** | Installed, disabled, system or all packages with a filter box. Open, Stop, Disable/Enable, Clear data, Remove (uninstall for user 0). |
| **Install** | Upload an `.apk`; it is installed with `adb install -r`, so existing apps are updated in place. |
| **Shell** | Run `adb shell` commands. Up/Down recall history; chips offer common diagnostics. Output is capped at 60 KB and commands at 30 s. |
| **Info** | Storage and memory bars, uptime, IP and key build properties. |
| **Settings** | Rename, change address or group, reconnect ADB, remove the device from the manager (nothing changes on the TV). |

## Power-on restore

Stock Android TV launchers remember the last input and return to it when the TV powers on. If you disable
that launcher (for example to remove ads), the feature goes with it. This manager brings it back:

1. While a TV is awake on an HDMI-style input, the input is remembered.
2. When the TV wakes from standby, reboots, or comes back after a power cut, the manager waits about
   three seconds and looks at what the TV did on its own.
3. If the TV is sitting on its launcher, the remembered input is launched. If the TV already went to an
   input, or the user opened an app, nothing is done.

Turn it off per TV on the **Inputs** tab. Events appear in **Activity** ("remembered input…",
"restored input…", "not restoring input: TV is on …").

## Schedules (calendar)

*Schedules* is a week calendar. A block means **these TVs are on from here to here**. You never choose how a
TV is woken: the manager works that out.

- **Draw a block:** drag on a day (or click or tap for one hour). A dialog asks which TVs, which days it repeats
  on (**Weekdays** / **Every day** shortcuts) and an optional name, and writes out what will happen
  ("Lobby turns on at 9:00 AM and goes to sleep at 11:00 AM, Mon–Fri.").
- **Change a block:** drag it to move it (sideways changes the day), drag its top or bottom edge to resize it,
  or click it to edit, pause (the *Enabled* switch) or delete it. A block that repeats shows on every day and
  changes everywhere at once. Use the TV chips above the calendar to see one TV's schedule. An end earlier than the
  start runs past midnight and is drawn on both days.
- **At the start** each TV is brought up the way it needs: an asleep or screensaver TV gets a wake key over
  ADB, a fully off TV gets Wake-on-LAN (if its MAC is known). It retries every 30 seconds for 15 minutes and
  Activity says what happened. Once it is up, power-on restore puts it on its last input. A TV that is already on is left alone.
- **At the end** each TV that is on (including one showing its screensaver) is put to sleep, unless another block covering the same TV is still running
  (so back-to-back blocks don't blink the TV).
- **Restarts and late edits:** a block that started in the last 10 minutes still counts after a server restart,
  and a block you draw while its time is already running starts straight away. Older blocks aren't re-run.
- Times use the **server's** clock; the page shows its zone and current time. Keyboard: Tab to a block, Enter to edit;
  *New schedule* opens the same dialog without dragging.

Schedules made before the calendar (a single timed action such as reboot or switch input) still run and appear
under *Single timed actions*, where they can be paused or deleted.

## Activity

The last 300 events as a dated timeline, with icons by type and filters for *All*, *Errors* and each device:
status changes, restores, schedule runs, power actions, installs and every shell command with the device it ran on. The full log is appended to `data/events.log`.
