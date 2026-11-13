"""Write the app's experiment files for the teammates' gesture set -> ours/mac_app/experiments/

  v5.json       exactly collector_v5's 30 items (23 gestures + 4 short idles + 3 x 60 s idles), same labels and
                instructions, but in random ROUNDS (one take of each per round) with the app's checks
  v5_plus.json  v5 + single (1x) versions at half the reps + our extra gestures + near-miss cues (not commands)
                + modules (near-miss everyday block, while talking, small, walking, re-wear)
Sessions of either convert to collector_v5's CSV format with scripts/app_to_v5_csv.py.
  python scripts/make_v5_experiments.py         (from ours/algorithm)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "mac_app" / "experiments"


def M(id, group, instruction, spoken, how=None, avoid=None, expect=None, demo=None, every=None, check=None):
    d = {"id": id, "group": group, "instruction": instruction, "spoken": spoken}
    for k, v in dict(how=how, avoid=avoid, expect=expect, demo=demo, every=every, check=check).items():
        if v is not None:
            d[k] = v
    return d


STILL = "keep your head still"
V5 = [  # collector_v5 GESTURES, same ids and instruction text
    M("tilt_2x_left", "head", "Quick double head tilt to the LEFT (ear to shoulder)", "double tilt left",
      "left ear toward left shoulder and back, twice, quickly", "shoulders stay down; don't hold", 2, "tilt_left,tilt_left"),
    M("tilt_2x_right", "head", "Quick double head tilt to the RIGHT (ear to shoulder)", "double tilt right",
      "right ear toward right shoulder and back, twice, quickly", "shoulders stay down; don't hold", 2, "tilt_right,tilt_right"),
    M("nod_2x_front", "head", "Quick double nod FORWARD", "double nod",
      "chin down and back up, twice, quickly", "don't hold the chin down", 2, "nod_down,nod_down"),
    M("circle_cw", "head", "One brisk head circle CLOCKWISE (~2 s)", "circle clockwise",
      "nose draws one clock on the wall: 12, 3, 6, 9, 12", "only one circle", 1, "circle_cw"),
    M("circle_ccw", "head", "One brisk head circle COUNTER-CLOCKWISE (~2 s)", "circle counter clockwise",
      "nose draws one clock backwards: 12, 9, 6, 3, 12", "only one circle", 1, "circle_ccw"),
    M("rotate_left_chin_down", "head", "Turn head LEFT, then dip chin down", "turn left, chin down",
      "ONE merged motion: turn left and, while still turned, dip the chin; then back to the front",
      "not two separate moves; don't turn your body", 2, "none"),
    M("rotate_right_chin_down", "head", "Turn head RIGHT, then dip chin down", "turn right, chin down",
      "ONE merged motion: turn right and, while still turned, dip the chin; then back to the front",
      "not two separate moves; don't turn your body", 2, "none"),
    M("mouth_open_2x", "face", "Open mouth wide twice (head still)", "open mouth twice",
      "open wide and close, twice", STILL, 0, "none"),
    M("puff_cheeks_2x", "face", "Puff both cheeks twice (head still)", "puff cheeks twice",
      "fill both cheeks with air and release, twice", STILL, 0, "none"),
    M("jaw_shift_left_right", "face", "Slide jaw LEFT, then RIGHT, back to centre", "jaw left, right",
      "lower jaw slides left, then right, then centre", STILL, 0, "none"),
    M("smile_2x", "face", "Closed-mouth smile, both sides, twice", "smile twice",
      "lips closed, both corners up, twice", STILL, 0, "none"),
    M("molar_tap_2x", "face", "Tap back teeth together twice (quick, firm)", "teeth tap twice",
      "back teeth click together twice", "don't move your head", 0, "none"),
    M("jaw_forward_2x", "face", "Push lower jaw FORWARD twice", "jaw forward twice",
      "push the lower jaw out and back, twice", STILL, 0, "none"),
    M("jaw_clench_double", "face", "Clench back teeth firmly twice", "clench twice",
      "bite down hard for a moment, twice", STILL, 0, "none"),
    M("eyebrow_up_down_2x", "face", "Raise eyebrows and lower them, twice (head still)", "eyebrows twice",
      "eyebrows up and down, twice", STILL, 0, "none"),
    M("eyebrow_then_mouth_open", "combo", "Eyebrows up-down ONCE, pause ~1 s, open mouth wide ONCE", "eyebrows, then mouth",
      "eyebrows once, wait one second, mouth once", STILL, 0, "none"),
    M("mouth_open_then_eyebrow", "combo", "Open mouth wide ONCE, pause ~1 s, eyebrows up-down ONCE", "mouth, then eyebrows",
      "mouth once, wait one second, eyebrows once", STILL, 0, "none"),
    M("eyebrow_then_puff_cheeks", "combo", "Eyebrows up-down ONCE, pause ~1 s, puff cheeks ONCE", "eyebrows, then puff",
      "eyebrows once, wait one second, puff once", STILL, 0, "none"),
    M("mouth_open_then_puff_cheeks", "combo", "Open mouth wide ONCE, pause ~1 s, puff cheeks ONCE", "mouth, then puff",
      "mouth once, wait one second, puff once", STILL, 0, "none"),
    M("puff_cheeks_then_eyebrow", "combo", "Puff cheeks ONCE, pause ~1 s, eyebrows up-down ONCE", "puff, then eyebrows",
      "puff once, wait one second, eyebrows once", STILL, 0, "none"),
    M("jaw_left_then_eyebrow", "combo", "Slide jaw LEFT and back ONCE, pause ~1 s, eyebrows up-down ONCE", "jaw left, then eyebrows",
      "jaw left and back, wait one second, eyebrows once", STILL, 0, "none"),
    M("eyebrow_then_jaw_left", "combo", "Eyebrows up-down ONCE, pause ~1 s, slide jaw LEFT and back ONCE", "eyebrows, then jaw left",
      "eyebrows once, wait one second, jaw left and back", STILL, 0, "none"),
    M("jaw_right_then_eyebrow", "combo", "Slide jaw firmly RIGHT, hold briefly, back; pause ~1 s; eyebrows up-down ONCE", "jaw right, then eyebrows",
      "jaw right, hold, back; wait one second; eyebrows once", STILL, 0, "none"),
    # collector_v5 IDLE_VARIANTS (label idle + variant in the converted CSV)
    M("idle_still", "idle", "Sit still, breathe normally", "stay still", "relax, look ahead", "no gesture", 0, "none"),
    M("idle_talk", "idle", "Talk naturally (count aloud, read something)", "talk", "count aloud until the beep", "no gesture", 0, "none"),
    M("idle_chew", "idle", "Chew (gum or pretend)", "chew", "chew normally until the beep", "no gesture", 0, "none"),
    M("idle_swallow", "idle", "Swallow ONCE, otherwise still", "swallow", "one normal swallow", "no gesture", 0, "none"),
]
LONG_IDLE = {"id": "core.long_idle", "kind": "negatives", "title": "Long idle (60 s each)", "activities": [
    {"text": "SIT STILL: sit relaxed and still, look at the screen", "seconds": 60},
    {"text": "TALK: talk naturally the whole time (read aloud, chat)", "seconds": 60},
    {"text": "CHEW: chew gum (or pretend) the whole time", "seconds": 60}]}

ONE_X = [  # single versions: half the reps (every 2nd round); "check" = the single motion our rules know
    M("tilt_1x_left", "head", "ONE head tilt to the LEFT", "single tilt left", "left ear toward shoulder and back, once",
      "just once", 1, "tilt_left", 2, "tilt_left"),
    M("tilt_1x_right", "head", "ONE head tilt to the RIGHT", "single tilt right", "right ear toward shoulder and back, once",
      "just once", 1, "tilt_right", 2, "tilt_right"),
    M("nod_1x_front", "head", "ONE nod forward", "single nod", "chin down and back up, once", "just once", 1,
      "nod_down", 2, "nod_down"),
    M("mouth_open_1x", "face", "Open mouth wide ONCE (head still)", "open mouth once", "open wide and close, once", STILL, 0, "none", 2),
    M("puff_cheeks_1x", "face", "Puff both cheeks ONCE (head still)", "puff once", "fill both cheeks and release, once", STILL, 0, "none", 2),
]
EXTRA_EVERY = 3   # candidates: few trials (every 3rd round) until a pilot shows they are clearly separable
EXTRA = [
    M("small_tilt_2x_left", "head", "SMALL double tilt LEFT (covert)", "small double tilt left",
      "two tiny quick tilts, as if aiming", "keep it small", 2, "tilt_left,tilt_left"),
    M("small_tilt_2x_right", "head", "SMALL double tilt RIGHT (covert)", "small double tilt right",
      "two tiny quick tilts, as if aiming", "keep it small", 2, "tilt_right,tilt_right"),
    M("tilt_hold_left", "head", "Tilt LEFT and HOLD 1 s, then back", "tilt left and hold",
      "tilt, count one, come back", "don't bounce", 1, "tilt_left"),
    M("tilt_hold_right", "head", "Tilt RIGHT and HOLD 1 s, then back", "tilt right and hold",
      "tilt, count one, come back", "don't bounce", 1, "tilt_right"),
    M("smirk_left", "face", "SMIRK LEFT: left mouth corner up, then release", "smirk left", "only the left corner", STILL, 0, "none"),
    M("smirk_right", "face", "SMIRK RIGHT: right mouth corner up, then release", "smirk right", "only the right corner", STILL, 0, "none"),
    M("earlobe_pull_left", "touch", "PULL LEFT EARLOBE gently down once", "left earlobe", "two fingers, a short gentle pull",
      "don't touch the AirPod", 0, "none"),
    M("earlobe_pull_right", "touch", "PULL RIGHT EARLOBE gently down once", "right earlobe", "two fingers, a short gentle pull",
      "don't touch the AirPod", 0, "none"),
    M("tongue_cheek_left", "face", "TONGUE pushes the LEFT cheek out, once", "tongue left", "mouth closed, tongue bulges the cheek",
      STILL, 0, "none"),
    M("tongue_cheek_right", "face", "TONGUE pushes the RIGHT cheek out, once", "tongue right", "mouth closed, tongue bulges the cheek",
      STILL, 0, "none"),
    M("sniff_2x", "face", "SNIFF twice, quickly", "sniff twice", "two short sniffs through the nose", STILL, 0, "none"),
    M("tap_cheek_2x_left", "touch", "TAP LEFT CHEEK twice with one finger", "tap cheek twice", "two light taps", "don't touch the AirPod", 0, "none"),
    M("tap_chin_2x", "touch", "TAP CHIN twice with one finger", "tap chin twice", "two light taps under the chin", "", 0, "none"),
]
for _m in EXTRA:
    _m["every"] = EXTRA_EVERY
NEAR_MISS = [  # NOT commands: everyday motions the recogniser must ignore (every 2nd round)
    M("slow_peek_left", "nearmiss", "LOOK LEFT slowly, as if checking something, then back", "look left slowly",
      "a natural, slow look", "this is NOT a gesture", 0, "turn_left", 2),
    M("slow_peek_right", "nearmiss", "LOOK RIGHT slowly, as if checking something, then back", "look right slowly",
      "a natural, slow look", "this is NOT a gesture", 0, "turn_right", 2),
    M("nod_while_talking", "nearmiss", "Say 'yes, okay' and nod along naturally", "talk and nod",
      "like agreeing in a conversation", "this is NOT a gesture", 0, "nod_down", 2),
    M("scratch_head", "nearmiss", "SCRATCH your head or ear briefly", "scratch", "a natural scratch", "this is NOT a gesture", 0, "none", 2),
    M("yawn", "nearmiss", "YAWN (or pretend to)", "yawn", "a full yawn", "this is NOT a gesture", 0, "none", 2),
    M("deep_breath", "nearmiss", "Take one DEEP BREATH in and out", "deep breath", "slow and deep", "this is NOT a gesture", 0, "none", 2),
]

TIMING = {"readyS": 0.8, "windowS": 3.0, "commandWindowS": 6.0, "gapMinS": 2.0, "gapMaxS": 3.5, "idlePerRound": 0,
          "breakEveryRounds": 4, "speechS": 1.3, "retakeOnce": True, "smallPeakRot": 0.15, "postureJumpDeg": 25}


# "Confused?" button in the app: opens a web search of real people doing it (GIPHY for common expressions and head
# moves, YouTube for jaw/teeth/tongue). Links only: nothing is downloaded or stored, so no licence issue.
from urllib.parse import quote_plus  # noqa: E402

GIPHY = {"tilt": "head tilt", "nod": "nodding", "circle": "head roll", "rotate": "look away down",
         "mouth_open": "open mouth wide", "puff_cheeks": "puff cheeks", "smile": "closed mouth smile",
         "eyebrow": "raise eyebrows", "smirk": "smirk", "sniff": "sniff", "yawn": "yawn", "scratch": "scratch head",
         "peek": "side eye look", "idle_still": "sitting still", "idle_talk": "talking", "idle_chew": "chewing gum",
         "idle_swallow": "gulp swallow", "earlobe": "pull earlobe", "tap": "tap cheek", "breath": "deep breath"}
YOUTUBE = {"jaw_shift": "jaw lateral movement exercise side to side", "jaw_left": "jaw lateral movement exercise",
           "jaw_right": "jaw lateral movement exercise", "jaw_forward": "jaw protrusion exercise push jaw forward",
           "molar_tap": "tap back teeth together", "clench": "clench jaw teeth exercise",
           "tongue": "tongue in cheek push exercise", "rotate": "turn head and tuck chin stretch"}


def ref_for(mid):
    for k, q in YOUTUBE.items():           # face-muscle moves first: GIPHY has no real demos of these
        if k in mid:
            return "https://www.youtube.com/results?search_query=" + quote_plus(q)
    for k, q in GIPHY.items():
        if k in mid:
            return "https://giphy.com/search/" + quote_plus(q).replace("+", "-")
    return None


def write(name, plan):
    for m in plan["motions"]:
        r = ref_for(m["id"])
        if r and "ref" not in m:
            m["ref"] = r
    ids = [m["id"] for m in plan["motions"]]
    assert len(ids) == len(set(ids)), "duplicate motion id"
    (OUT / name).write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(name, len(ids), "motions")


OUT.mkdir(parents=True, exist_ok=True)
write("v5.json", {
    "name": "Teammates v5 (rounds)", "version": "v5-rounds-1",
    "about": "collector_v5's 30 items with the same labels: 23 gestures + 4 short idles in random rounds (each once per "
             "round, 3 s window), then 3 x 60 s idle. Converts to the v5 CSV with app_to_v5_csv.py. About 3.5 min per round.",
    "motions": V5, "commands": [], "timing": TIMING, "practicePerMotionFirst": 1, "practicePerMotionLater": 0,
    "core": [{"id": "core.rounds", "kind": "rounds", "title": "Rounds", "condition": "sitting", "rounds": 20, "minRounds": 2},
             LONG_IDLE],
    "modules": [], "fillModule": None})
plus_mod = [
    {"id": "N", "title": "Near-miss, no gestures", "tests": "false triggers from everyday motion", "rotate": True, "blocks": [
        {"id": "N.negatives", "kind": "negatives", "title": "No gestures: everyday motions", "activities": [
            {"text": "TALK: chat with the experimenter, nod along when you agree", "seconds": 60},
            {"text": "LOOK AROUND the room slowly, as if searching", "seconds": 30},
            {"text": "TOUCH YOUR FACE: scratch, rub your ear, adjust hair or glasses", "seconds": 30},
            {"text": "YAWN, take a DEEP BREATH, stretch your neck", "seconds": 30},
            {"text": "DRINK water, eat a snack", "seconds": 45}]}]},
    {"id": "T", "title": "While talking", "tests": "gestures with speech", "rotate": True, "blocks": [
        {"id": "T.rounds", "kind": "rounds", "title": "While talking", "condition": "keep talking or counting aloud", "rounds": 1}]},
    {"id": "S", "title": "Small (covert)", "tests": "how small still works", "rotate": True, "blocks": [
        {"id": "S.rounds", "kind": "rounds", "title": "Small (covert)", "condition": "as small as a computer could still notice", "rounds": 1}]},
    {"id": "W", "title": "Walking", "tests": "body motion", "rotate": True, "blocks": [
        {"id": "W.rounds", "kind": "rounds", "title": "Walking", "condition": "walking slowly around the room", "rounds": 1},
        {"id": "W.negatives", "kind": "negatives", "title": "Walking, no gestures", "activities": [
            {"text": "WALK around the room, turning at the corners, no gestures", "seconds": 60}]}]},
    {"id": "R", "title": "Re-wear", "tests": "earbud put back differently", "rotate": True, "blocks": [
        {"id": "R.rewear", "kind": "rewear", "title": "Re-wear"},
        {"id": "R.rounds", "kind": "rounds", "title": "After re-wear", "condition": "sitting (after re-wear)", "rounds": 1}]},
    {"id": "G", "title": "Extra rounds", "tests": "more repetitions", "rotate": False, "blocks": [
        {"id": "G.rounds", "kind": "rounds", "title": "Extra rounds", "condition": "sitting", "rounds": 1}]},
]
write("v5_plus.json", {
    "name": "v5 plus (1x, extras, near-miss)", "version": "v5-plus-1",
    "about": "The 30 v5 items + single (1x) versions at half the reps + our extra (candidate) gestures every 3rd round + near-miss cues (NOT "
             "commands) in random rounds, then 3 x 60 s idle; extra modules fill the time (near-miss block first). "
             "About 6 min per round. Converts to the v5 CSV with app_to_v5_csv.py (extra labels kept as they are).",
    "motions": V5 + ONE_X + EXTRA + NEAR_MISS, "commands": [], "timing": TIMING,
    "practicePerMotionFirst": 1, "practicePerMotionLater": 0,
    "core": [{"id": "core.rounds", "kind": "rounds", "title": "Rounds", "condition": "sitting", "rounds": 12, "minRounds": 2},
             LONG_IDLE],
    "modules": plus_mod, "requireOneOf": [["N"]], "modulesPerDevice": True, "fillModule": "G"})
