"""Explicit Yuwen Yi clip plan and exact 60 Hz retiming.

The original Paper2D fields identify source animations, not named martial arts.
The following reuse/partitions are declared BBEE adaptations. Missing reaction
poses require authored art; there is no invisible or donor fallback.
"""
from __future__ import annotations

from fractions import Fraction

# Values are (NPCResources field, slot, optional selected source keyframe indices).
SOURCE_PLAN = {
    "stand": ("IdleRightFlipbook", None, None),
    "standby": ("FightIdleRightFlipbook", None, None),
    "run_start": ("RunRightFlipbook", None, [0, 1]),
    "run": ("RunRightFlipbook", None, None),
    "run_stop": ("RunRightFlipbook", None, [4, 5]),
    "jump": ("QingGongSSStartRightFlipbooks", None, None),
    "jump2": ("QingGongSSStartRightFlipbooks", None, None),
    "drop_start": ("QingGongSSLoopRightFlipbooks", None, None),
    "drop": ("QingGongSSLoopRightFlipbooks", None, None),
    "dropend": ("QingGongSSEndRightFlipbooks", None, None),
    "dash": ("QingGongSSLoopRightFlipbooks", None, None),
    "dash_air": ("QingGongSSLoopRightFlipbooks", None, None),
    "dash_end": ("QingGongSSEndRightFlipbooks", None, None),
    "born": ("IdleRightFlipbook", None, None),
    "born_fall": ("QingGongSSLoopRightFlipbooks", None, None),
    "born_land": ("QingGongSSEndRightFlipbooks", None, None),
    "burst": ("FistRightFlipbooks", 0, None),
    "transmit": ("QingGongSSStartRightFlipbooks", None, None),
    "sword1": ("SwordRightFlipbooks", 0, None),
    "sword2": ("SwordRightFlipbooks", 0, [2, 3, 4, 5]),
    "sword3": ("SwordRightFlipbooks", 0, None),
    "launcher": ("SwordRightFlipbooks", 0, [1, 2, 3, 4, 5]),
    "air1": ("SwordRightFlipbooks", 0, None),
    "air2": ("SwordRightFlipbooks", 0, [2, 3, 4, 5]),
    "zhenwu": ("SwordRightFlipbooks", 0, None),
    "chase": ("SwordRightFlipbooks", 0, [2, 3, 4, 5]),
    "taiji_fist": ("FistRightFlipbooks", 0, None),
    "circle_short": ("SwordRightFlipbooks", 0, None),
    "circle_full": ("SwordRightFlipbooks", 0, None),
    "ultra": ("FistRightFlipbooks", 0, None),
    "escape": ("QingGongSSLoopRightFlipbooks", None, None),
}
# These are new visible poses, never inferred from null source mapping slots.
AUTHORED_REQUIRED = ("squat", "squat_loop", "squat_to_stand", "behit", "behit_air", "tumble",
                     "down", "getup", "dead", "pose", "summon", "heal", "charge")
AUTHORED_PLAN = {
    "squat": ("crouch", [0, 1]),
    "squat_loop": ("crouch", [3]),
    "squat_to_stand": ("crouch", [3, 2, 1, 0]),
    "behit": ("behit", None), "behit_air": ("behit_air", None), "tumble": ("tumble", None),
    "down": ("down", None), "getup": ("getup", None), "dead": ("dead", None),
    "pose": ("salute", None), "summon": ("salute", None), "heal": ("meditate", None),
    "charge": ("guard_charge", None),
}
EFFECTS = ("sword_echo", "wuxiang", "taiji_counter", "zhenwu_wave", "qi_impact", "taiji_charge", "taiji_circle", "ultra_field")

# Original sword 0/1/2 are windup, 3/4/5 extend the sword. The exact BBEE
# exposures preserve every actual strike pose before the legal combo cancel.
# Original 1/10-second FrameRun/FPS weights remain in production provenance.
EXPLICIT_SOURCE_TICKS = {
    "sword1": [2, 2, 2, 4, 4, 10],
    "sword2": [3, 7, 7, 11],
    "sword3": [3, 3, 4, 8, 6, 12],
    "air1": [2, 2, 2, 6, 5, 10],
    "air2": [5, 8, 8, 12],
    "zhenwu": [2, 2, 3, 4, 3, 18],
}


def retime(frames, total_ticks):
    """Allocate at least one tick per source key, preserving relative duration.

Largest remainder on the remaining budget gives exactly the contract duration;
source order and every selected keyframe survive. Consecutive identical keys
may then be coalesced without losing their combined duration.
    """
    if type(total_ticks) is not int or total_ticks <= 0 or not frames or len(frames) > total_ticks:
        raise ValueError("clip duration cannot preserve every selected keyframe")
    if any("exact_ticks" in frame for frame in frames):
        ticks = [frame.get("exact_ticks") for frame in frames]
        if any(type(tick) is not int or tick <= 0 for tick in ticks) or sum(ticks) != total_ticks:
            raise ValueError("explicit keyframe exposure must exactly cover the clip")
        result = []
        for frame, tick in zip(frames, ticks):
            if result and result[-1][0] == frame["key"]:
                result[-1] = (frame["key"], result[-1][1] + tick)
            else:
                result.append((frame["key"], tick))
        return result
    weights = [Fraction(frame["weight"]) for frame in frames]
    if any(weight <= 0 for weight in weights):
        raise ValueError("clip has a nonpositive frame duration weight")
    budget = total_ticks - len(frames)
    shares = [budget * weight / sum(weights) for weight in weights]
    ticks = [1 + share.numerator // share.denominator for share in shares]
    rest = total_ticks - sum(ticks)
    order = sorted(range(len(frames)), key=lambda i: (-(shares[i] % 1), i))
    for index in order[:rest]:
        ticks[index] += 1
    result = []
    for frame, tick in zip(frames, ticks):
        if result and result[-1][0] == frame["key"]:
            result[-1] = (frame["key"], result[-1][1] + tick)
        else:
            result.append((frame["key"], tick))
    if sum(t for _, t in result) != total_ticks:
        raise ValueError("retiming did not preserve the exact contract duration")
    return result


def sequences(source=None):
    if source is None:
        from body_source import BodySource
        source = BodySource()
    contract, plan = source.contract, source.manifest["clip_frames"]
    if set(plan) != set(contract["clips"]):
        raise ValueError("production clip plan differs from the complete character contract")
    out = {}
    for name, definition in contract["clips"].items():
        out[name] = retime(plan[name], definition["ticks"])
    for alias, target in contract["cinematic_aliases"].items():
        if target not in out:
            raise ValueError("cinematic alias target does not exist: " + target)
        if alias in out:
            if alias != target:
                raise ValueError("cinematic alias overwrites a semantic clip")
            continue
        out[alias] = list(out[target])
    for name, sequence in out.items():
        if not sequence or any(key == "null" or key not in source.frames or tick <= 0 for key, tick in sequence):
            raise ValueError("incomplete/invisible frame sequence: " + name)
    return out
