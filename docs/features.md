# Using the dashboard

## Screen (live view)

The **Screen** tab streams what the TV is showing. Press **Start live view**, pick *Low (480p, 6 fps)*,
*Medium (720p, 10 fps)* or *High (1080p, 15 fps)*, save a snapshot with the camera button, or go fullscreen.
Below the picture is a mini remote (Back, arrows, OK, Home) and a keyboard switch, so you can navigate while watching.

* It works by recording the TV's screen with `screenrecord`, so it needs a TV whose firmware allows screen capture.
  Many TVs show the interface and apps fine but block the video layer, so **HDMI inputs and DRM video such as Netflix
  are usually black or not capturable**. The tab says so when a TV refuses.
* A live view ends by itself after 30 minutes (press **Resume**), at most 4 TVs can be watched at once, and starting and
  ending a view is written to *Activity*.

## Look and feel

The UI follows Google's Material 3 Expressive guidelines: a navigation rail on wide screens that turns into a
bottom bar on phones, one contextual floating action button (Add device / New schedule), large rounded
shapes that morph on press, connected button groups, and avatars whose shape reflects the TV's state.

**Settings → Appearance** chooses *Auto / Light / Dark* and an **accent colour** (blue, teal, green, amber,
rose, violet). The whole palette is generated from that seed hue, in both light and dark. The choice is kept in
the browser, so each person can have their own. Motion respects the OS "reduce motion" setting.

## When a TV is offline

Cards for TVs that are offline or waiting for approval show what to do instead of dead controls, with a
**Reconnect / Try again** button. The drawer's Remote, Inputs, Apps, Install, Shell and Info tabs show the same
explanation, and refresh themselves the moment the TV comes back. Settings and the power-on options stay usable.

## Devices

Each card shows the TV's state (**On**, **Standby**, **Offline**, **Needs approval on TV**), model and
Android version, the active **Input**, the foreground app (**Showing**), the remembered **Last input**
and when it was last seen. Quick buttons send Wake, Standby and Home. Click a card for the details drawer.

Use the search box and group chips to filter. Tick cards (or *Select all*) to get a bulk bar:
Wake, Standby, Home, Restore input, Reboot.

## The details drawer

| Tab | What it does |
|---|---|
| **Remote** | D-pad, Back/Home/Menu/Info/Input, volume, media keys, Wake/Standby/Reboot. A screenshot panel (refresh or auto-refresh every 3 s). Tick *Use keyboard* to drive it with arrows, Enter, Backspace (Back) and H (Home). |
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

## Schedules

*Schedules → + New schedule*: pick an action (wake, standby, reboot, go Home, switch input), a time, days
of the week and the target TVs. Times use the **server's** clock. Each schedule can be toggled on and off.
A schedule fires at most once per minute even if the scheduler wakes twice.

For *Switch input* schedules, pick the input by name from a list loaded from the first selected TV; the raw
input id is filled in for you and can still be edited.

## Activity

The last 300 events as a dated timeline, with icons by type and filters for *All*, *Errors* and each device:
status changes, restores, schedule runs, power actions, installs and every shell command with the device it ran on. The full log is appended to `data/events.log`.
