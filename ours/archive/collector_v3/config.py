"""What gets recorded: motions, their instructions, session plans and the command dictionary.

Edit MAIN_MOTIONS and COMMANDS after the pilot. Everything else reads from here.
"""

# Single motions. Every motion is ONE go-and-return movement (no doubles, no counting), in one smooth go:
# do NOT hold at the far end. Pause only with the head back at the front. (Mac test 2026-11-07: holding the chin
# down for 2 s split every nod into a "down" and an "up" motion.)
INSTRUCTIONS = {
    "nod_down":   "NOD DOWN once: chin down and straight back up to the front (don't hold it down)",
    "look_up":    "LOOK UP once: chin up and straight back to the front (don't hold it up)",
    "tilt_left":  "TILT LEFT once: left ear toward left shoulder and straight back (don't hold)",
    "tilt_right": "TILT RIGHT once: right ear toward right shoulder and straight back (don't hold)",
    "turn_left":  "TURN LEFT once: look left and straight back to the front (don't hold)",
    "turn_right": "TURN RIGHT once: look right and straight back to the front (don't hold)",
    "circle_cw":  "CIRCLE CLOCKWISE once: your nose draws ONE clock on the wall in front, 12-3-6-9-12, then stop at front",
    "circle_ccw": "CIRCLE COUNTER-CLOCKWISE once: your nose draws ONE clock, 12-9-6-3-12, then stop at front",
    "jaw_clench": "JAW CLENCH once: bite down firmly, release",
    "idle":       "NOTHING: stay natural (you may breathe, blink, look around a little)",
}

PILOT_MOTIONS = ["nod_down", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right",
                 "circle_cw", "circle_ccw", "jaw_clench"]
MAIN_MOTIONS = ["nod_down", "look_up", "tilt_left", "tilt_right", "turn_left", "turn_right",
                "circle_cw", "circle_ccw"]          # placeholder until the pilot decides

# (first, then) -> message. Placeholder: replace with the 20 pairs chosen after the pilot.
COMMANDS = {
    ("tilt_left", "nod_down"): "GO FORWARD",
    ("tilt_right", "nod_down"): "FALL BACK",
    ("tilt_left", "tilt_right"): "HOLD POSITION",
    ("tilt_right", "tilt_left"): "MOVE",
    ("circle_cw", "nod_down"): "NEED BACKUP",
    ("circle_ccw", "nod_down"): "ABORT",
    ("turn_left", "nod_down"): "ENEMY LEFT",
    ("turn_right", "nod_down"): "ENEMY RIGHT",
    ("look_up", "nod_down"): "ACK",
    ("look_up", "tilt_left"): "YES",
    ("look_up", "tilt_right"): "NO",
    ("circle_cw", "tilt_left"): "MOVE LEFT",
    ("circle_cw", "tilt_right"): "MOVE RIGHT",
    ("turn_left", "look_up"): "WAIT",
    ("turn_right", "look_up"): "READY",
    ("nod_down", "circle_cw"): "REGROUP",
    ("nod_down", "circle_ccw"): "COVER ME",
    ("tilt_left", "circle_ccw"): "STOP",
    ("tilt_right", "circle_cw"): "CLEAR",
    ("look_up", "circle_ccw"): "REPEAT",
}

# Timing (seconds)
WINDOW_S = 4.0            # time after the GO beep reserved for the motion
GAP_S = (2.5, 5.0)        # random quiet gap after the window
IDLE_PER_ROUND = 2
PAIR_GAPS_S = (0.3, 0.6, 1.0)  # pilot: pause between two motions of a back-to-back pair

NEGATIVES_PILOT = [("talk: read aloud or chat", 3), ("listen and nod along naturally while someone talks", 2),
                   ("chew gum", 2), ("walk around the room", 2), ("use your phone, look around", 1)]
NEGATIVES_MAIN = [("talk: read aloud or chat", 2), ("listen and nod along naturally", 1), ("chew gum", 2),
                  ("drink water", 1), ("walk around", 1), ("use your phone, look around", 1)]

# Session plans: list of blocks. Block kinds are handled in collector_v3.py.
PLANS = {
    "pilot": [  # about 45 min, team of 5, decides the vocabulary
        {"kind": "calibration"},
        {"kind": "rounds", "name": "main", "rounds": 15, "condition": "sitting", "motions": "pilot"},
        {"kind": "rounds", "name": "small", "rounds": 1, "condition": "small (as small as still recognisable)",
         "motions": "pilot"},
        {"kind": "rounds", "name": "slow", "rounds": 1, "condition": "slow", "motions": "pilot"},
        {"kind": "pairs", "name": "back_to_back", "pairs_per_gap": 4, "motions": "pilot"},
        {"kind": "negatives", "activities": "pilot"},
    ],
    "main": [  # about 50 min, one device per session, two sessions per person
        {"kind": "calibration"},
        {"kind": "rounds", "name": "enrollment", "rounds": 3, "condition": "sitting, slow and clear",
         "motions": "main"},
        {"kind": "rounds", "name": "main_a", "rounds": 8, "condition": "sitting", "motions": "main"},
        {"kind": "rewear"},
        {"kind": "calibration"},
        {"kind": "rounds", "name": "main_b", "rounds": 8, "condition": "sitting", "motions": "main"},
        {"kind": "rounds", "name": "standing", "rounds": 2, "condition": "standing", "motions": "main"},
        {"kind": "rounds", "name": "walking", "rounds": 2, "condition": "walking in place", "motions": "main"},
        {"kind": "rounds", "name": "head_offset", "rounds": 2,
         "condition": "head already tilted/turned before each motion", "motions": "main"},
        {"kind": "rounds", "name": "slow", "rounds": 1, "condition": "slow", "motions": "main"},
        {"kind": "rounds", "name": "fast", "rounds": 1, "condition": "fast", "motions": "main"},
        {"kind": "rounds", "name": "small", "rounds": 1, "condition": "small", "motions": "main"},
        {"kind": "commands", "name": "commands", "n": 10},
        {"kind": "self_paced", "name": "self_paced", "lists": 2, "per_list": 5},
        {"kind": "negatives", "activities": "main"},
    ],
}
