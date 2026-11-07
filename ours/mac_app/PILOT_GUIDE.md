# Pilot guide: Gesture Collector v3 (Mac + iPhone)

For the team members running pilot sessions. Read it once before you start.

Downloads: https://github.com/optimusprimeg/Temporal-Head-Gesture-Recognition/releases/tag/gesture-collector
- `GestureCollector.zip`: the **Mac** app (macOS 14 or newer)
- `GestureCollector-iOS.ipa`: the **iPhone** app (iOS 16 or newer)

Both apps run the same experiment, write the same files, and need AirPods with head tracking (AirPods Pro 1/2/3,
AirPods 3/4/5, AirPods Max). AirPods 1 and 2 do not work.

## 0. Participant numbers (important)

Each Mac and iPhone keeps its own list of participants, so **numbers must be agreed in the group**, or two people
end up as "P02". Use the team sheet:

| Number | Who | Device |
|---|---|---|
| P01 | Ghanshyam | (developer: test data only) |
| P02 | ... | iPhone + AirPods Pro 2 |
| P03 | ... | Mac + AirPods 5 |
| P04, P05 ... | next people | |

Type the number in the app when you add a participant. A person keeps the same number for every session.

## 1. Install

### Mac (AirPods 5 user)
1. Download `GestureCollector.zip` and unzip it.
2. Right-click `GestureCollector.app`, then **Open**. If macOS refuses, open System Settings > Privacy & Security,
   scroll down, and click **Open Anyway**. The app is not from the App Store, which is why macOS asks.
3. When asked, allow **Motion & Fitness**.
4. Connect the AirPods to this Mac.

### iPhone (AirPods Pro 2 user)
The iPhone app is not on the App Store, so you sign it with **your own Apple ID** before installing. The free
Apple ID signature lasts **7 days**; after that, install again the same way.

**Option A: Sideloadly (Windows or Mac)**
1. Install Sideloadly from sideloadly.io. On Windows, also install iTunes and iCloud from Apple's website (not the
   Microsoft Store versions).
2. Connect the iPhone with a cable and tap **Trust** on the iPhone.
3. Drag `GestureCollector-iOS.ipa` into Sideloadly, choose your iPhone, and type your Apple ID. You type it into
   Sideloadly yourself; never send your Apple ID password to anyone in the group. If you prefer not to use a
   third-party tool with your Apple ID, use Option B.
4. On the iPhone: Settings > General > VPN & Device Management, tap your Apple ID, then **Trust**.
5. iOS 16 and newer: Settings > Privacy & Security > **Developer Mode** on, then restart the iPhone.

**Option B: Xcode on a Mac.** Ask Ghanshyam for the source build steps (`ours/mac_app/GestureCollector`). Xcode signs
with your Apple ID directly.

Then open the app, allow **Motion & Fitness**, and connect the AirPods to the iPhone. The iPhone app keeps the
screen on during a session; keep the phone on the table in front of you.

## 2. Before a session
- About **60 minutes**, a chair, a quiet room, and space to walk around (stay within about 10 m of the Mac or
  iPhone).
- Both AirPods in, charged. Keep both in for the whole session.
- Give the participant the consent text in the app to read.

## 3. Running a session
1. **Experiment:** choose **Pilot v3** (the default). Do not edit the pilot file: every pilot session must run the
   same protocol.
2. **New participant:** first name, the **number from the team sheet**, age group, hand, glasses, consent. Then
   **Add participant**.
3. **Session:** choose the participant. **AirPods:** choose the model actually worn (the suggestion follows the
   crossover order; if only one model is available, choose the one you have). **Time available:** 60 min
   recommended. Below about 35 min the core does not fit and the session is marked incomplete.
4. **Device check:** rate about 50 Hz (25 on some models), |g| about 9.81, the 3D head follows the head. Then
   **Next: plan**.
5. **Plan review:** shows the core and the optional modules for this person. **Start session**.
6. Follow the spoken cues. The experimenter presses **Continue** on instruction screens and **Done** after re-wearing
   or a list of commands.

### What to tell the participant
- Every motion is **one smooth go and straight back to the front**. Don't hold at the far end.
- Start when you hear the motion's name; you don't have to wait for the beep.
- **Commands = two motions with a short still pause between them** (about half a second, head back at the front).
- "Small" means: as small as you think a computer could still notice.
- "Nothing": stay natural. No-gesture blocks: just do the activity; no gestures.

### If something goes wrong
- **Earbud switched** (one AirPod came out): put both back in. The app recalibrates and repeats the trial.
- **App closed or crashed:** open it again; the start screen offers **Resume**.
- **Participant must stop:** **End session**. Everything so far is saved; the rest is planned next time.
- Use **Add note** for anything unusual (someone walked in, cough, phone rang).

## 4. After the session: send the data
1. On the last screen press **Make zip of this session**, then **Send the zip** (AirDrop, WhatsApp, Drive...).
   On the Mac the zip is also shown in Finder.
2. Send it to Ghanshyam.
3. Do not rename the folder, and **never open the CSV files in Excel and save them** (Excel breaks the timestamps).
   Where the data is: Mac: Documents > GestureCollector. iPhone: Files app > On My iPhone > Gesture Collector.

## 5. Second session (another day)
Same participant number. If both AirPods models are available (for example, you swap for one session), use the
other model: then device and person are not mixed up in the analysis. If not, use the same model: the app then
plans only the optional modules not done yet on it.

## 6. Optional: Live recognizer
"Live recognizer: try commands" on the start screen shows what the system recognises in real time (Rules or Model
mode). It is for trying things out and demos, not part of the data collection. Its logs go to the `live` folder.

## 7. For developers: experiment files
Protocols are JSON files in the data folder's `experiments` folder (`pilot.json`, `selftest.json`). A new file
appears in the app's Experiment picker after **Reload experiment files**; a broken file is listed with what is wrong.
Every session saves a copy of the experiment it ran as `experiment.json`. Format: `Sources/Plan.swift` (top comment).
