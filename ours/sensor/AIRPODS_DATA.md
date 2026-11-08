# What the AirPods give us (via Sensor Logger)

Source of the data: Apple's `CMHeadphoneMotionManager` (iOS 14+, also macOS 14+). Each update is a
`CMDeviceMotion` from **one** earbud at a time, already fused on the AirPods (accelerometer + gyroscope).
Sensor Logger ("Headphone motion", a paid feature) forwards it. Raw accelerometer/gyroscope are **not**
available, only the fused outputs below.

Units and relations below were **checked on our own recordings** (`check_fields.py`, subjects 2 and 3 of the old
data), because online sources disagree on units.

## Columns

| Our column | Sensor Logger key | Physical quantity | Unit | Frame |
|---|---|---|---|---|
| `quatW, quatX, quatY, quatZ` | quaternionW/X/Y/Z | head (earbud) orientation | unit quaternion (norm 1.0000) | earbud → reference frame |
| `yaw, pitch, roll` | yaw, pitch, roll | same orientation as Euler angles | rad | Apple order Z-X-Y: yaw about Z, pitch about X, roll about Y |
| `rotX, rotY, rotZ` | rotationRateX/Y/Z | angular velocity, gyro bias removed | rad/s | earbud axes |
| `accX, accY, accZ` | accelerationX/Y/Z | user acceleration (gravity removed) | **m/s²** | earbud axes |
| `gravX, gravY, gravZ` | gravityX/Y/Z | gravity direction | **m/s²** (magnitude 9.807) | earbud axes |
| `timestamp` | time | phone timestamp | ns since 1970 | |

**Sample rate: 50 Hz** (median step 20.0 ms; under 1 % of steps > 30 ms). Apple allows up to 100 Hz; the
files were named "100hz" but are 50 Hz.

## How they relate (checked)

1. **Euler = quaternion.** yaw/pitch/roll are exactly Apple's Z-X-Y Euler angles of the quaternion (error 0.0000
   rad). Same information twice; use the quaternion (no gimbal lock, no ±π jumps).
2. **Reference frame of the quaternion: Z vertical, heading arbitrary.** Gravity expressed in the reference frame
   is exactly −Z with zero spread. So pitch and roll are tilt relative to gravity (but still include how the bud
   sits in the ear), and yaw is relative to an arbitrary start heading and can drift. That is why we never use
   absolute yaw, and why the calibration nod is needed to know where "forward" is.
3. **Vector columns use the earbud axes with X and Z flipped relative to the quaternion's body frame**
   (a 180° turn about Y): with `F = diag(-1, 1, -1)`, gravity_in_reference = R(q) · F · grav exactly (z = −1.0000,
   spread 0.0000, all 4 subjects), and rotation rate matches F · (angular velocity from the quaternion) with the same
   magnitude (median ratio 1.000; per-axis correlation 0.87-0.96, limited by differentiating the quaternion). Only matters if you
   mix quaternion maths with the vector columns; our head-frame code uses only the vectors, so it is unaffected.
   **This flip is Sensor Logger's, not Apple's.** Our Mac app (raw `CMHeadphoneMotionManager`, 2026-11-07,
   `data/internal GG 01`, AirPods on a MacBook) has **no flip**: gravity = R(q)ᵀ · (0, 0, −9.81) with error 0.0000,
   and rotation rate vs quaternion derivative correlates +0.999 / +0.998 / +0.999 on x / y / z with no sign change.
   Head-frame features are unaffected (the frame comes from gravity and the calibration nods), but **raw-axis (R0)
   features differ in the sign of X and Z between Sensor Logger and Mac recordings**: never pool them on raw axes.
   **Earbud switch (Mac test 2026-11-07):** only one bud streams. Taking the streaming bud out gives a 1.07 s gap,
   then the stream continues from the other bud and **stays there** when the first goes back in. After the switch
   the yaw/quaternion reference restarts at 0 and gravity points differently in sensor axes (about 30° here: the
   buds sit at different angles), so the head frame must be recalibrated. `gesturekit.io.find_earbud_switches`
   finds switches (from `sensor_location`, or from gap + yaw restart + gravity jump when the column is missing, as
   in collector streams); the pipeline then falls back to the gravity frame and flags the events, and QC fails
   until a new calibration follows. The Mac app's push to the collector does not send `sensor_location` yet.
4. **Total acceleration = gravity + user acceleration** (both m/s², earbud axes). Checked physically: user
   acceleration ≈ radius × angular acceleration gives a radius of 7 cm in m/s² (65 cm if it were g, impossible).
5. **Rotation rate** is the derivative of orientation (in earbud axes); integrating it gives orientation change,
   which is what the quaternion already does on the AirPods.

## What this means for us

- Use **rotation rate** (main signal), **gravity** (for the head frame), **user acceleration** (jaw, impacts).
  The quaternion/Euler add nothing new, except pitch/roll as absolute tilt.
- Units bug found and fixed: `phase0/airpods.py` treated user acceleration as g. The old gesture_lab code
  (`prior_work/gesture_lab/src/gesturelab/config.py`) has the same wrong comment ("in g"). Phase 0 results were re-run.
- One bud at a time: Apple reports which bud (`sensorLocation`, iOS 17+), Sensor Logger does not export it. If
  the active bud switches (one taken out), the axes change → calibrate again (our protocol does after re-wear).
  Ask both devices' Sensor Logger exports to check this column on the newer AirPods.

## Android

**Not with Sensor Logger or any normal Android app.** `CMHeadphoneMotionManager` is Apple-only (iOS, macOS);
Android has no API for AirPods motion. The open-source **LibrePods** project talks Apple's private AirPods
protocol on Android and supports AirPods **head gestures** (nod/shake to answer calls), and a 2026 GitHub issue
reports head-orientation data arriving over that channel, but it is a proposal, not a feature: no rotation rate
or acceleration stream, may need root depending on Android version. Not usable for data collection.
→ **Recording needs an iPhone (or a Mac with macOS 14+).**

Sources: Apple WWDC23 "What's new in Core Motion"; AWARE AirPods module; LibrePods README and issue #719
(links in the chat log of 2026-11-06).
