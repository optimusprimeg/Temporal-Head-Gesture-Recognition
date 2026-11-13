"""Draw a looping cartoon demo clip (GIF) for every gesture -> ours/mac_app/experiments/media/<id>.gif

  python scripts/make_gesture_clips.py            (from ours/algorithm)

The app (v3.3) plays <data folder>/experiments/media/<motion id>.gif on the run screen and in the WATCH step;
copy the media folder next to the experiment files. Our own drawings: no third-party footage, no licences.
A gesture = a list of (primitive, seconds). Each primitive moves a few face/head parameters with a smooth
go-and-back bump; clips end with a short rest so the loop reads as 'do it, then still'.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[2] / "mac_app" / "experiments" / "media"
W, H, FPS = 240, 270, 15
SKIN, LINE, DARK, PINK, BLUE = (247, 214, 186), (60, 45, 40), (40, 30, 30), (225, 120, 130), (70, 120, 220)
HAND = (240, 200, 170)
try:
    FONT = ImageFont.truetype("arial.ttf", 15)
    BIG = ImageFont.truetype("arialbd.ttf", 19)
except OSError:
    FONT = BIG = ImageFont.load_default()

BASE = dict(pitch=0, roll=0, yaw=0, mouth=0, puff=0, jaw=0, smileL=0, smileR=0, brow=0, teeth=0, jawfwd=0,
            clench=0, tongue=0, sniff=0, eyes=1, hand=None, handp=0, throat=0, talk=0, lip=0)


# the red word shown at the top while a part of the gesture plays (numbered: 1., 2. ...)
ACTION = {"puff": "puff cheeks", "eyebrow": "eyebrows up", "mouth_open": "open mouth", "jaw_left": "jaw left",
          "jaw_right": "jaw right", "jaw_right_hold": "jaw right, hold", "molar_tap": "tap teeth",
          "jaw_forward": "jaw forward", "clench": "clench", "smile": "smile", "chin_down_left": "chin down",
          "chin_down_right": "chin down", "turn_left_hold": "turn left", "turn_right_hold": "turn right",
          "back_from_left": "back", "back_from_right": "back", "nod_down": "nod", "circle_cw": "circle",
          "circle_ccw": "circle", "rotate_left": "turn L + chin down",
          "rotate_right": "turn R + chin down"}


def bump(u):
    return math.sin(math.pi * min(1, max(0, u)))


# primitive -> function(u) returning parameter changes
P = {
    "tilt_left": lambda u: dict(roll=-22 * bump(u)), "tilt_right": lambda u: dict(roll=22 * bump(u)),
    "small_tilt_left": lambda u: dict(roll=-9 * bump(u)), "small_tilt_right": lambda u: dict(roll=9 * bump(u)),
    "hold_tilt_left": lambda u: dict(roll=-18 * min(1, 3 * u, 3 * (1 - u))),
    "hold_tilt_right": lambda u: dict(roll=18 * min(1, 3 * u, 3 * (1 - u))),
    "nod_down": lambda u: dict(pitch=1 * bump(u)), "look_up": lambda u: dict(pitch=-1 * bump(u)),
    "turn_left": lambda u: dict(yaw=-1 * bump(u)), "turn_right": lambda u: dict(yaw=1 * bump(u)),
    "turn_left_hold": lambda u: dict(yaw=-min(1, 4 * u)), "turn_right_hold": lambda u: dict(yaw=min(1, 4 * u)),
    "chin_down_left": lambda u: dict(yaw=-1, pitch=0.9 * bump(u)), "chin_down_right": lambda u: dict(yaw=1, pitch=0.9 * bump(u)),
    "back_from_left": lambda u: dict(yaw=-(1 - u)), "back_from_right": lambda u: dict(yaw=-(u - 1)),
    "circle_cw": lambda u: dict(pitch=-0.8 * math.cos(2 * math.pi * u) * min(1, 5 * u, 5 * (1 - u)),
                                yaw=0.8 * math.sin(2 * math.pi * u) * min(1, 5 * u, 5 * (1 - u))),
    "circle_ccw": lambda u: dict(pitch=-0.8 * math.cos(2 * math.pi * u) * min(1, 5 * u, 5 * (1 - u)),
                                 yaw=-0.8 * math.sin(2 * math.pi * u) * min(1, 5 * u, 5 * (1 - u))),
    "slow_peek_left": lambda u: dict(yaw=-0.7 * bump(u)), "slow_peek_right": lambda u: dict(yaw=0.7 * bump(u)),
    "mouth_open": lambda u: dict(mouth=bump(u)), "puff": lambda u: dict(puff=bump(u)),
    "jaw_left": lambda u: dict(jaw=-bump(u)), "jaw_right": lambda u: dict(jaw=bump(u)),
    "jaw_right_hold": lambda u: dict(jaw=min(1, 4 * u, 4 * (1 - u))),
    "smile": lambda u: dict(smileL=bump(u), smileR=bump(u)),
    "smirk_left": lambda u: dict(smileL=bump(u)), "smirk_right": lambda u: dict(smileR=bump(u)),
    "eyebrow": lambda u: dict(brow=bump(u)), "molar_tap": lambda u: dict(teeth=bump(u) ** 4),
    "jaw_forward": lambda u: dict(jawfwd=bump(u)), "clench": lambda u: dict(clench=bump(u)),
    "tongue_left": lambda u: dict(tongue=-bump(u)), "tongue_right": lambda u: dict(tongue=bump(u)),
    "tongue_roof": lambda u: dict(lip=bump(u)), "pout": lambda u: dict(lip=bump(u)),
    "sniff": lambda u: dict(sniff=bump(u)), "swallow": lambda u: dict(throat=bump(u)),
    "yawn": lambda u: dict(mouth=1.3 * bump(u), eyes=1 - bump(u)), "blink_breath": lambda u: dict(),
    "talk": lambda u: dict(talk=abs(math.sin(9 * math.pi * u)) * 0.6),
    "chew": lambda u: dict(mouth=0.25 * abs(math.sin(6 * math.pi * u)), jaw=0.2 * math.sin(6 * math.pi * u)),
    "deep_breath": lambda u: dict(pitch=-0.15 * bump(u), sniff=0.5 * bump(u)),
    "earlobe_left": lambda u: dict(hand="earL", handp=bump(u)), "earlobe_right": lambda u: dict(hand="earR", handp=bump(u)),
    "tap_cheek_left": lambda u: dict(hand="cheekL", handp=bump(u) ** 3), "tap_cheek_right": lambda u: dict(hand="cheekR", handp=bump(u) ** 3),
    "tap_chin": lambda u: dict(hand="chin", handp=bump(u) ** 3), "scratch": lambda u: dict(hand="head", handp=0.5 + 0.5 * abs(math.sin(5 * math.pi * u))),
    "rotate_left": lambda u: dict(yaw=-min(1, 4 * u, 4 * (1 - u)), pitch=0.9 * bump((u - 0.2) / 0.55)),
    "rotate_right": lambda u: dict(yaw=min(1, 4 * u, 4 * (1 - u)), pitch=0.9 * bump((u - 0.2) / 0.55)),
    "rest": lambda u: dict(),
}


def frame(p, caption, action=""):
    img = Image.new("RGB", (W, H), (255, 255, 255))
    face = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(face)
    cx, cy = W // 2, W // 2 + 5
    yaw, pitch = p["yaw"], p["pitch"]
    fx, fy = cx + 28 * yaw, cy + 22 * pitch                     # where the face points
    rx, ry = 78, 92
    # ears (the far ear hides when turning)
    for side in (-1, 1):
        vis = 1 - max(0, side * -yaw) * 0.9
        if vis > 0.15:
            ex = cx + side * (rx - 4) + 10 * yaw * (side == 1 and yaw > 0 or side == -1 and yaw < 0)
            d.ellipse([ex - 10 * vis, cy - 18, ex + 10 * vis, cy + 18], fill=SKIN, outline=LINE, width=2)
    puffw = 26 * p["puff"]
    d.ellipse([cx - rx - puffw, cy - ry, cx + rx + puffw, cy + ry + 20 * p["jawfwd"]], fill=SKIN, outline=LINE, width=3)
    # hair
    d.chord([cx - rx, cy - ry, cx + rx, cy - ry + 95 - 30 * pitch], 180, 360, fill=(90, 60, 40))
    if p["clench"] > 0.05:                                     # jaw muscle lines
        for side in (-1, 1):
            x = cx + side * (rx - 14)
            for k in range(3):
                d.line([x + side * 4 * k, cy + 25, x + side * 4 * k, cy + 45], fill=(200, 80, 80), width=2)
    # eyes + brows
    eo = 8 * p["eyes"] * (1 + 0.45 * p["brow"]) + 1
    for side in (-1, 1):
        ex, ey = fx + side * 28, fy - 12
        d.ellipse([ex - 9, ey - eo, ex + 9, ey + eo], fill="white", outline=LINE, width=2)
        if p["eyes"] > 0.2:
            d.ellipse([ex - 4 + 4 * yaw, ey - 4 + 3 * pitch, ex + 4 + 4 * yaw, ey + 4 + 3 * pitch], fill=DARK)
        by = ey - 20 - 13 * p["brow"]
        d.line([ex - 12, by + 2, ex + 12, by - 2 * side * 0], fill=LINE, width=4)
        if p["brow"] > 0.3:                                    # red "up" arrow over each brow
            d.polygon([(ex, by - 16), (ex - 7, by - 6), (ex + 7, by - 6)], fill=(220, 60, 60))
    # nose + sniff
    d.line([fx, fy, fx - 6, fy + 18, fx + 4, fy + 20], fill=LINE, width=2)
    if p["sniff"] > 0.05:
        for side in (-1, 1):
            d.arc([fx - 8 + side * 6 - 4, fy + 14, fx - 8 + side * 6 + 8, fy + 26], 0, 180, fill=BLUE, width=2)
        d.line([fx - 26, fy + 22, fx - 14, fy + 20], fill=BLUE, width=2)
        d.line([fx + 26, fy + 22, fx + 14, fy + 20], fill=BLUE, width=2)
    # cheeks
    if p["puff"] > 0.05:
        for side in (-1, 1):
            r = 14 + 10 * p["puff"]
            d.ellipse([fx + side * (44 + 14 * p["puff"]) - r, fy + 31 - r, fx + side * (44 + 14 * p["puff"]) + r, fy + 31 + r], fill=(245, 175, 160))
    if abs(p["tongue"]) > 0.05:
        s = 1 if p["tongue"] > 0 else -1
        d.ellipse([fx + s * 40 - 10, fy + 26, fx + s * 40 + 10 + 4 * abs(p["tongue"]), fy + 44], fill=(240, 160, 150), outline=LINE)
    # mouth
    mx, my = fx + 34 * p["jaw"], fy + 45 + 16 * p["jawfwd"]
    open_ = max(p["mouth"], p["talk"])
    if open_ > 0.05:
        d.ellipse([mx - 18, my - 4, mx + 18, my + 50 * open_], fill=(120, 30, 40), outline=LINE, width=2)
    else:
        lw = 18 + 6 * p["lip"]
        yl, yr = my - 18 * p["smileL"], my - 18 * p["smileR"]
        d.line([mx - lw, yl, mx - 6, my + 3 * max(p["smileL"], p["smileR"]), mx + 6, my + 3 * max(p["smileL"], p["smileR"]), mx + lw, yr],
               fill=LINE, width=3, joint="curve")
        if p["lip"] > 0.1:
            d.ellipse([mx - 10, my - 5, mx + 10, my + 7], outline=PINK, width=3)
    if p["teeth"] > 0.3:
        d.rectangle([mx - 14, my - 3, mx + 14, my + 5], fill="white", outline=LINE)
        d.line([mx - 22, my - 10, mx - 30, my - 18], fill=(230, 150, 30), width=3)
        d.line([mx + 22, my - 10, mx + 30, my - 18], fill=(230, 150, 30), width=3)
    if p["jaw"] != 0:
        d.line([cx - 24 + 34 * p["jaw"], cy + ry - 4, cx + 24 + 34 * p["jaw"], cy + ry - 4], fill=LINE, width=3)
        s = 1 if p["jaw"] > 0 else -1
        if abs(p["jaw"]) > 0.3:
            d.polygon([(cx + s * 70, cy + ry - 14), (cx + s * 52, cy + ry - 22), (cx + s * 52, cy + ry - 6)], fill=(220, 60, 60))
    # hand
    if p["hand"]:
        tgt = {"earL": (cx - rx + 2, cy + 22), "earR": (cx + rx - 2, cy + 22), "cheekL": (fx - 44, fy + 30),
               "cheekR": (fx + 44, fy + 30), "chin": (fx, cy + ry - 6), "head": (cx + 40, cy - ry + 20)}[p["hand"]]
        start = (tgt[0] + (-60 if tgt[0] < cx else 60), tgt[1] + 70)
        k = p["handp"]
        hx, hy = start[0] + (tgt[0] - start[0]) * min(1, 1.6 * k), start[1] + (tgt[1] - start[1]) * min(1, 1.6 * k)
        if p["hand"].startswith("ear"):
            hy += 10 * max(0, k - 0.6)                         # the pull down
        d.ellipse([hx - 13, hy - 13, hx + 13, hy + 13], fill=HAND, outline=LINE, width=2)
        d.line([hx, hy + 12, hx + (8 if hx < cx else -8), hy + 45], fill=HAND, width=12)
    # neck / throat
    face = face.rotate(-p["roll"], resample=Image.BICUBIC, center=(cx, cy + ry))
    img.paste(face, (0, 0), face)
    dd = ImageDraw.Draw(img)
    if p["throat"] > 0.05:
        dd.ellipse([cx - 6, W - 20 - 8 * p["throat"], cx + 6, W - 8 - 8 * p["throat"]], outline=BLUE, width=2)
    if action:
        aw = dd.textlength(action, font=BIG)
        dd.text(((W - aw) / 2, 2), action, fill=(210, 40, 40), font=BIG)
    tw = dd.textlength(caption, font=FONT)
    dd.text(((W - tw) / 2, W + 8), caption, fill=LINE, font=FONT)
    return img


def clip(steps, caption):
    frames = []
    k = 0
    for prim, secs in steps + [("rest", 0.8)]:
        n = max(1, int(secs * FPS))
        if prim != "rest":
            k += 1
        name = ACTION.get(prim, prim.replace('_', ' ')).upper()
        parts = sum(1 for q, _ in steps if q != "rest")
        word = "" if prim == "rest" else (name if parts == 1 else f"{k}. {name}")
        for i in range(n):
            p = dict(BASE)
            p.update(P[prim]((i + 0.5) / n))
            frames.append(frame(p, caption, word))
    return frames


T, D, G = 0.8, 0.45, 0.6     # one motion, the quick second of a double, the ~1 s pause in combos
GESTURES = {
    # ---- the 30 of collector_v5 (23 gestures + 7 idle)
    "tilt_2x_left": [("tilt_left", T), ("rest", 0.1), ("tilt_left", T)],
    "tilt_2x_right": [("tilt_right", T), ("rest", 0.1), ("tilt_right", T)],
    "nod_2x_front": [("nod_down", T), ("rest", 0.1), ("nod_down", T)],
    "circle_cw": [("circle_cw", 2.0)], "circle_ccw": [("circle_ccw", 2.0)],
    "rotate_left_chin_down": [("rotate_left", 1.8)],      # ONE merged motion: turn and, still turned, dip the chin
    "rotate_right_chin_down": [("rotate_right", 1.8)],
    "mouth_open_2x": [("mouth_open", T), ("mouth_open", T)], "puff_cheeks_2x": [("puff", T), ("puff", T)],
    "jaw_shift_left_right": [("jaw_left", T), ("jaw_right", T)], "smile_2x": [("smile", T), ("smile", T)],
    "molar_tap_2x": [("molar_tap", D), ("molar_tap", D)], "jaw_forward_2x": [("jaw_forward", T), ("jaw_forward", T)],
    "jaw_clench_double": [("clench", T), ("clench", T)], "eyebrow_up_down_2x": [("eyebrow", T), ("eyebrow", T)],
    "eyebrow_then_mouth_open": [("eyebrow", T), ("rest", G), ("mouth_open", T)],
    "mouth_open_then_eyebrow": [("mouth_open", T), ("rest", G), ("eyebrow", T)],
    "eyebrow_then_puff_cheeks": [("eyebrow", T), ("rest", G), ("puff", T)],
    "mouth_open_then_puff_cheeks": [("mouth_open", T), ("rest", G), ("puff", T)],
    "puff_cheeks_then_eyebrow": [("puff", T), ("rest", G), ("eyebrow", T)],
    "jaw_left_then_eyebrow": [("jaw_left", T), ("rest", G), ("eyebrow", T)],
    "eyebrow_then_jaw_left": [("eyebrow", T), ("rest", G), ("jaw_left", T)],
    "jaw_right_then_eyebrow": [("jaw_right_hold", 1.0), ("rest", G), ("eyebrow", T)],
    "idle_still": [("rest", 2.0)], "idle_talk": [("talk", 2.5)], "idle_chew": [("chew", 2.5)],
    "idle_swallow": [("rest", 0.6), ("swallow", 0.9)],
    "idle_still_long": [("rest", 2.0)], "idle_talk_long": [("talk", 2.5)], "idle_chew_long": [("chew", 2.5)],
    # ---- single (1x) versions: "not a command" + building blocks
    "tilt_1x_left": [("tilt_left", T)], "tilt_1x_right": [("tilt_right", T)], "nod_1x_front": [("nod_down", T)],
    "mouth_open_1x": [("mouth_open", T)], "puff_cheeks_1x": [("puff", T)],
    # ---- our extras
    "small_tilt_2x_left": [("small_tilt_left", 0.5), ("small_tilt_left", 0.5)],
    "small_tilt_2x_right": [("small_tilt_right", 0.5), ("small_tilt_right", 0.5)],
    "tilt_hold_left": [("hold_tilt_left", 1.6)], "tilt_hold_right": [("hold_tilt_right", 1.6)],
    "smirk_left": [("smirk_left", T)], "smirk_right": [("smirk_right", T)],
    "earlobe_pull_left": [("earlobe_left", 1.2)], "earlobe_pull_right": [("earlobe_right", 1.2)],
    "tongue_cheek_left": [("tongue_left", 1.0)], "tongue_cheek_right": [("tongue_right", 1.0)],
    "sniff_2x": [("sniff", 0.4), ("sniff", 0.4)], "tap_cheek_2x_left": [("tap_cheek_left", 0.4), ("tap_cheek_left", 0.4)],
    "tap_chin_2x": [("tap_chin", 0.4), ("tap_chin", 0.4)],
    # ---- near-miss (not commands)
    "slow_peek_left": [("slow_peek_left", 2.0)], "slow_peek_right": [("slow_peek_right", 2.0)],
    "nod_while_talking": [("talk", 0.6), ("nod_down", 0.7), ("talk", 0.6)],
    "scratch_head": [("scratch", 1.6)], "yawn": [("yawn", 2.0)], "deep_breath": [("deep_breath", 2.0)],
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for gid, steps in GESTURES.items():
        frames = clip(steps, gid.replace("_", " "))
        path = OUT / f"{gid}.gif"
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0, optimize=True)
        total += path.stat().st_size
    print(f"{len(GESTURES)} clips -> {OUT} ({total / 1e6:.1f} MB)")
