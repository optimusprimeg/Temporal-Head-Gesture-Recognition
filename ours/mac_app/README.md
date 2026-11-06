# AirPods Check (macOS app)

Small Mac app to check that we really get AirPods motion data on a Mac, and to record it. Uses Apple's
`CMHeadphoneMotionManager` (the same source as Sensor Logger on iPhone).

**Status: written on Windows, not compiled or run yet.** The first person to build it, please send back what you
see (screenshot of the window + any build errors).

## Needs

- Mac with **macOS 14 Sonoma or newer** (e.g. MacBook Air M1 on macOS 14/15).
- Apple command line tools: `xcode-select --install` (once; full Xcode not needed).
- AirPods Pro (any generation), AirPods 3/4 or AirPods Max, **connected to this Mac** and **worn**.

## Build and run (on the Mac)

```
cd mac_app
bash build.sh
open AirPodsCheck.app
```

First start: macOS asks for **Motion & Fitness** permission → Allow. If you missed it:
System Settings → Privacy & Security → Motion & Fitness → enable "AirPods Check".

## What to check in the window

| Check | Good |
|---|---|
| status | "Receiving data OK" |
| rate | about 50 Hz (Apple allows up to 100; tell us the number you see) |
| earbud | left / right / default (tell us which; take one bud out and see if it switches) |
| \|g\| | about 9.81 |
| rotation rate | jumps when you nod / tilt, near 0 when still |

## Recording

- **Save to CSV**: writes `~/Documents/AirPodsCheck/airpods_<date>_<time>.csv`. Columns are the same as our
  collector's `stream.csv` plus `sensor_location`. Units: rad/s, m/s² (Apple's g × 9.80665), rad.
  Values are Apple's raw values, no axis flips (we will compare them with Sensor Logger's).
- **Send to collector**: type the URL `collector_v3.py` prints (`http://<PC IP>:8000/data`), switch on. Then the
  Mac replaces the iPhone + Sensor Logger and the normal session runs unchanged. The first time, macOS may ask for
  local network access → Allow.

## Sharing with someone

- Easiest: zip this `mac_app` folder and send it; they run `bash build.sh` on their own Mac.
- Sending a built `AirPodsCheck.app` also works, but macOS blocks unsigned downloaded apps. They then right-click →
  Open, or run `xattr -dr com.apple.quarantine AirPodsCheck.app`.

## If something fails

| Problem | Try |
|---|---|
| `swiftc not found` | `xcode-select --install` |
| "not available on this Mac" | update to macOS 14+ |
| permission DENIED | Privacy & Security → Motion & Fitness |
| connected but no data | wear both buds; check AirPods are the Mac's output in Control Center → Sound |
| no permission prompt at all | start it with `open AirPodsCheck.app` (not by running the binary inside it) |
