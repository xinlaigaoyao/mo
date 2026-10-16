"""Generate Yuwen Yi's complete native kit from immutable, build-bound stock data.

Preparation only. Importers consume frozen gen files; they never call this module.
Reading stock ActionLogicGroup layouts does not import Ragna's attacks or body art.
The registry, Action/RID graph, native skill rows, hitboxes and damage are owned here.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# prepare executes this file by absolute path; cwd is not a Python import path.
sys.path.insert(0, str(ROOT))
ACTOR = 200901
BULLET = 20090101
FP = 1 << 32
# Each ordinary follow-up opens after that action's final native hit window.
# Dash is a separate defensive cancel, not part of these attack recovery times.
ATTACK_CANCEL = {
    "ywy_sword1": 16/60, "ywy_sword2": 20/60, "ywy_sword3": 27/60,
    "ywy_launcher": 16/60, "ywy_air1": 20/60, "ywy_air2": 24/60,
    "ywy_zhenwu": 17/60, "ywy_chase": 23/60, "ywy_taiji_fist": 32/60,
    "ywy_circle_short": 24/60, "ywy_circle_full": 35/60, "ywy_ultra": 75/60,
}
INPUT_BUFFER = .48


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if not path.exists() or path.read_bytes() != raw:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def fixed(x):
    return {"value": round(x * FP)}


def time_range(start, end):
    return {"Start": fixed(start), "Finish": fixed(end)}


def expr(x):
    return {"UseExpression": 0, "ConstValue": fixed(x), "Expression": {"Source": ""}}


def cond(*rids):
    return {"Combine": 0, "Conditions": [{"rid": r} for r in rids]}


def once(time, function, params=""):
    return {"TimeConfig": {"StartType": 1, "Start": fixed(time), "End": fixed(0),
                           "Interval": fixed(-1), "NonTimeType": 1},
            "ConditionGroup": cond(), "Call": {"Function": function, "Params": params}}


def on_exit(function, events=6):
    call = once(0,function)
    # Native Other / TimeEnd|Interrupt, from ActionLogicStartEndType (2|4).
    call["TimeConfig"].update(StartType=3,NonTimeType=events)
    return call


def clear_conditions(value):
    """Retained physical defaults must not retain any donor-potential managed RID."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "ConditionGroup": value[key] = cond()
            else: clear_conditions(item)
    elif isinstance(value, list):
        for item in value: clear_conditions(item)


class Logic:
    def __init__(self, stock, contract):
        self.stock = stock
        self.by_name = {a["Name"]: a for a in stock["_actions"]}
        self.contract = contract
        self.refs = []
        self.rid = 9109000000000000000

    def ref(self, cls, data):
        self.rid += 1
        self.refs.append({"rid": self.rid, "type": {"class": cls, "ns": "GamePlay", "asm": "Assembly-CSharp"}, "data": data})
        return self.rid

    def input(self, key, mode=0, sticky=INPUT_BUFFER, end=.8):
        return self.ref("ActionLogicCondition_Input", {"Invert": 0, "InputKey": key, "InputKeyMode": mode,
            "InputStickyTime": fixed(sticky), "InputStickyTimeEnd": fixed(end)})

    def script(self, params):
        return self.ref("ActionLogicCondition_Script", {"Invert": 0, "Call": {"Function": "YwyGate", "Params": params}})

    def direction(self, axis, invert=0):
        return self.ref("ActionLogicCondition_InputDir", {"Invert":invert,"CheckLR":0,
            "CheckDown":1 if axis=="down" else 0,"CheckFront":0,"CheckBack":0,"CheckUp":1 if axis=="up" else 0})

    def switch(self, action, group, at, key, *extra):
        directional=[]
        if action=="ywy_taiji_fist":directional=[self.direction("down")]
        elif action in ("ywy_chase","ywy_launcher"):directional=[self.direction("up")]
        elif action=="ywy_zhenwu":directional=[self.direction("up",1),self.direction("down",1)]
        elif action in ("ywy_sword1","ywy_sword2","ywy_sword3"):directional=[self.direction("up",1)]
        elif action in ("jump_down","drop_down"):directional=[self.direction("down")]
        elif action in ("jump","jump2"):directional=[self.direction("down",1)]
        if action in ("dash","dash2"):
            directional.append(self.script("dash:"+("1" if action=="dash" else "2")))
        # Explicit ChangeSkillByActionName does not enforce PreSkillOrder. The
        # same read-only gate also guards native PlayerSkillChain row selection.
        if group:
            directional.append(self.script(f'move:"{action}", input:{key}, group:{group}'))
        return {"TimeCheck": {"StartType": 1, "Start": fixed(at), "End": fixed(9999), "NonTimeType": 1},
                "ConditionGroup": cond(self.input(key), *directional, *extra),
                "NewActionEx": {"UseExpression": 0, "ConstValue": action, "Expression": {"Source": ""}},
                "NewActionMode": 1, "SkillCheck": 15, "SkillGroup": group,
                "NewActionWithAutoFace": 1, "ScriptCall": {"Function": "", "Params": ""}}

    def fresh(self, name, clip, ticks=None, action_type=1):
        a = deepcopy(self.by_name["stand"])
        # Keep the serialized field layout and default values; erase all donor mechanics.
        for k, value in list(a.items()):
            if isinstance(value, list):
                a[k] = []
        ticks = ticks or self.contract["clips"]["ywy_" + clip]["ticks"]
        a.update(Enable=1, RoleName="ywy", Name=name, Animate="ywy_" + clip,
                 AnimateDuration=fixed(ticks / 60), TotalDuration=fixed(ticks / 60), ActionType=action_type,
                 NextAction="stand", DropAction="drop", OnGroundAction="", DeadAction="dead",
                 ProtectTime=fixed(0), ActionMaxHitCount=9999)
        a["StartSpeed"] = deepcopy(self.by_name["attackHold"]["StartSpeed"])
        a["InputDirControlsActorDir"] = 0
        a["BehitBoxs"] = [{"TimeRange": time_range(0, 9999), "ConditionGroup": cond(), "Index": 0,
            "Tag": "ywy_body", "BehitPreproc": {"Function": "YwyGuard", "Params": ""},
            "Box": {"Min": {"x": fixed(-0.3), "y": fixed(0)}, "Max": {"x": fixed(0.3), "y": fixed(1.8)}}}]
        return a

    def movement(self, a, x, y, at=0, duration=0.15):
        m = deepcopy(self.by_name["attackHold"]["AddMotions"][0])
        m["Time"] = fixed(at)
        m["ConditionGroup"] = cond()
        m["Motion"]["MotionType"] = 3
        m["Motion"]["DeltaX"] = expr(x)
        m["Motion"]["DeltaY"] = expr(y)
        m["Motion"]["DurationEx"] = expr(duration)
        m["Motion"]["CanInterrupt"] = 1
        a["AddMotions"].append(m)

    def inv(self, a, start, end, level=9):
        a["Invincibility"].append({"TimeRange": time_range(start, end), "ConditionGroup": cond(),
            "InvincipalLvlEx": {"UseExpression": 0, "ConstValue": level, "Expression": {"Source": ""}}})

    def hit(self, a, kind, start_tick, end_tick, bounds, ratio=1, fly=0, push=3, interval=-1, max_hits=1):
        h = deepcopy(self.by_name["attackHold"]["HitDataList"][0])
        h["TickRange"] = {"Start": fixed(start_tick / 60), "End": fixed(end_tick / 60), "HitInterval": fixed(interval)}
        h["HitBox"] = {"Min": {"x": fixed(bounds[0]), "y": fixed(bounds[1])},
                       "Max": {"x": fixed(bounds[2]), "y": fixed(bounds[3])}}
        h["Id"] = "ywy_" + kind + "_" + str(start_tick)
        h["ArmorBreak"] = 1
        h["InvincipalBreak"] = 0
        h["Victim"].update(Action="behit_up" if fly else "behit_middle", RandomActions=[],
            DamageMultiply=fixed(ratio), Speed={"x": fixed(push), "y": fixed(fly)},
            SpeedRand={"x": fixed(0), "y": fixed(0)}, BuffList=[], NoCombo=0)
        h["Victim"]["DistAdapt"]["Enable"] = 0
        for key in h["HitFreezeN"]:
            h["HitFreezeN"][key] = fixed(0.025 if "Attacker" in key else 0.07)
        h["PreventHitBySameBoxType"] = 0
        h["PreventHitBySameBoxIdDuration"] = fixed(0)
        h["PreventHitBySameBoxIdMaxTimes"] = max_hits
        h["PreventHitBySameBoxIdMaxTimesEx"] = {"UseExpression": 0, "ConstValue": max_hits, "Expression": {"Source": ""}}
        h["AttackerCalls"] = [{"ConditionGroup": cond(), "CalcStage": stage,
            "FuncCall": {"Function": name, "Params": 'kind:"' + kind + '"'}}
            for stage, name in ((1, "YwyDamage"), (3, "YwyHit"))]
        a["HitDataList"].append(h)

    def core(self):
        aliases = {
            "stand": "stand", "standby1": "standby", "standby2": "standby", "runStart": "run_start",
            "run": "run", "runBrake": "run_stop", "squat": "squat", "squat_loop": "squat_loop",
            "squat_to_stand": "squat_to_stand", "jump_down": "jump", "drop_down": "drop",
            "jump": "jump", "jump2": "jump2", "jump3": "jump2", "drop_start": "drop_start",
            "drop": "drop", "drop2": "drop", "dropend": "dropend", "dropend2": "dropend",
            "dropend3": "dropend", "dropend4": "dropend", "quickStand": "getup", "reactive": "getup",
            "behit_up": "behit", "behit_middle": "behit", "push_back": "behit_air", "push_back_2": "behit_air",
            "push_back_3": "behit_air", "push_back_4": "behit_air", "push_down": "behit_air",
            "push_down_2": "behit_air", "push_down_3": "behit_air", "push_down_4": "behit_air",
            "standUp": "getup", "standUp2": "getup", "standUp_Dead": "dead", "push_back_show": "behit_air",
            "bornshow_standup": "born_land", "bornshow_fall_end": "born_land", "bornshow_fall": "born_fall",
            "reborn": "born", "born": "born", "born_start": "born_fall", "born_start_2": "born_land",
            "burst": "burst", "burstD": "burst", "teacherskill": "burst", "teacherskillAir": "burst",
            "super_burst": "burst", "super_burstAir": "burst", "pvp_burst": "burst", "pvp_burstAir": "burst",
            "dead": "dead", "dead_backup": "dead", "transmit": "transmit", "addHP": "heal", "addHPAir": "heal",
            "summon": "summon", "winpose": "pose", "winpose2": "pose", "StagePass": "pose",
            "knockdown": "tumble", "knockdown_loop": "down", "knockdown_stand": "getup",
            "knockdown_todead": "dead", "pvp_born": "born", "drop_down_show": "drop",
            "dropend_show": "dropend", "paid_show": "pose",
        }
        out = []
        for name, clip in aliases.items():
            a = deepcopy(self.by_name[name])
            a.update(RoleName="ywy", Animate="ywy_" + clip, Enable=1,
                     AnimateDuration=fixed(self.contract["clips"]["ywy_"+clip]["ticks"]/60))
            # Stock physical movement and passive/death state handling stay native.
            # Stock offensive resources, voices, FX, scripts, triggers and branches do not.
            for k in ("ActionSwitchs", "HitDataList", "AddRoles", "AddBuff", "RemoveBuff", "Audios", "HitAudios",
                      "AddEffects", "RemoveEffect", "ScriptCalls", "GrabStart", "GrabTimeRange", "GrabControlFrames",
                      "GrabDamages", "ForceFields", "BehitNotify", "ActionTags", "ValueCurve"):
                a[k] = []
            a["JoystickVibrate"] = []; a["MobileVibrate"] = []
            clear_conditions(a)
            for k in ("NextAction", "DropAction", "DropEndAction", "DropEndHighAction", "OnGroundAction", "BeginFallAction", "DeadAction"):
                if a.get(k) and a[k] not in aliases:
                    a[k] = "dead" if k == "DeadAction" else "drop" if "Drop" in k else "stand"
            # Avoid copied trigger-gated cooldowns: explicit jump/air-dash reset contracts.
            a["CDList"] = []
            if name in ("stand", "runStart", "run", "dropend", "dropend2", "dropend3", "dropend4"):
                a["CDList"] = [{"Time": fixed(0), "ID": key, "Duration": fixed(0)}
                               for key in ("jump2", "dashAir", "ywy_air1", "ywy_air2")]
            if name in ("jump2", "jump3"):
                a["CDList"] = [{"Time": fixed(0), "ID": name, "Duration": fixed(9999)}] + [
                    {"Time": fixed(0), "ID": key, "Duration": fixed(0)} for key in ("ywy_air1", "ywy_air2")]
                a["ScriptCalls"].append(once(0,"SkillChainReset","chain:4, cd:0"))
            for box in a["BehitBoxs"]:
                box["ConditionGroup"] = cond()
                box["BehitPreproc"] = {"Function": "YwyGuard", "Params": ""}
            if name in ("born", "reborn", "pvp_born"):
                a["ScriptCalls"].append(once(0, "YwyBorn"))
                a["NextAction"] = "stand"
            if name in ("addHP", "addHPAir"):
                # Generic engine completion consumes/heals the real equipped flask.
                a["ScriptCalls"].append(once(1,"UseHealthFlaskSucc"))
            if name == "summon":
                # Preserve the equipped tactic; do not substitute a character skill.
                a["ScriptCalls"].append(once(0,"CreateBullet_summon"))
                a["ScriptCalls"].append(once(0,"YwyStart",'kind:"summon", input:5'))
            if name in ("jump_down", "drop_down", "jump", "jump2"):
                a["ScriptCalls"].append(once(0,"YwyStart",'kind:"jump", input:800'))
            if name == "jump":
                # Ground jump, like landing, opens one native second jump and air kit.
                a["CDList"] = [{"Time":fixed(0),"ID":key,"Duration":fixed(0)}
                               for key in ("jump2","dashAir","ywy_air1","ywy_air2")]
            if a["ActionType"] == 8:
                a["ScriptCalls"].append(once(0, "YwyReset"))
            if name in ("behit_up", "behit_middle", "push_back", "push_back_2", "push_down", "push_down_2", "knockdown", "knockdown_loop"):
                sw=self.switch("ywy_escape",5,0,55,self.script("escape:true"))
                # Independent seven-second escape uses its own native action gate,
                # not a possibly muted ground/air-dash skill chain. It spends no MP.
                sw["NewActionMode"]=0;sw["SkillCheck"]=0
                a["ActionSwitchs"].append(sw)
            if a["ActionType"] in (0, 2, 4, 9, 18):
                self.cancel(a, 0)
            out.append(a)
        return out

    def cancel(self, a, at):
        # Native MP/CD/ground checks still apply. Per-action time and input epoch
        # are checked by YwyGate even when a different skill chain has reset Cur.
        for name, group, key in (("dash", 5, 55), ("dash2",5,55), ("dashAir", 5, 55),
                                 ("jump_down",7,800),("drop_down",7,800),("jump", 7, 800), ("jump2", 7, 800),
                                 ("ywy_ultra", 3, 4), ("ywy_taiji_fist", 2, 3), ("ywy_chase", 2, 3),
                                 ("ywy_zhenwu", 2, 3), ("ywy_launcher", 1, 1), ("ywy_air1", 4, 1),
                                 ("ywy_sword1", 1, 1),("summon",11,5)):
            if name == a["Name"]:
                continue
            if a["Name"] in ("ywy_sword1","ywy_sword2") and name == "ywy_sword1":
                continue
            a["ActionSwitchs"].append(self.switch(name, group, .01 if group==5 else at, key))

    def charge_entry(self, a):
        sw = self.switch("ywy_charge", 8, .30, 1)
        sw["ConditionGroup"] = cond(self.input(1, 4, .30, 9999))
        sw["NewActionMode"] = 0; sw["SkillCheck"] = 0
        a["ActionSwitchs"].insert(0, sw)

    def kit(self):
        out = []
        params = {
            "sword1": ([(6, 10, (-0.4, 0.1, 2.6, 2.0), 1)], 0.45, 0),
            "sword2": ([(6, 9, (-0.3, 0.1, 2.8, 2.1), 0.5), (13, 17, (-0.5, 0.1, 3.1, 2.2), 0.5)], 0.65, 0),
            "sword3": ([(10, 19, (-1.2, -0.1, 3.8, 2.6), 1)], 1.0, 0),
            "launcher": ([(8, 15, (-0.3, 0.1, 2.8, 3.3), 1)], 0.75, 8),
            "air1": ([(6, 13, (-1.1, -0.7, 2.7, 1.8), 1)], 0.4, 1),
            "air2": ([(9, 18, (-1.8, -1.0, 3.2, 1.8), 1)], 0.6, 2),
            "chase": ([(11, 22, (-0.6, -0.5, 3.5, 2.6), 1)], 3.2, 4),
            "taiji_fist": ([(24, 31, (-1.5, -0.2, 4.0, 2.6), 1)], 0.9, 0),
            "circle_short": ([(12, 23, (-4.0, -0.5, 4.0, 3.1), 1)], 0, 0),
            "circle_full": ([(9, 13, (-4.8, -0.5, 4.8, 3.4), 1/3), (18, 22, (-4.8, -0.5, 4.8, 3.4), 1/3), (28, 34, (-5.2, -0.5, 5.2, 3.6), 1/3)], 0, 0),
            "ultra": ([(15, 21, (-5, -0.7, 5, 4), 0.25), (33, 42, (-6, -0.7, 6, 4.5), 0.25), (62, 74, (-7, -0.7, 7, 5), 0.5)], 1.5, 0),
        }
        kinds = {"taiji_fist": "fist", "circle_short": "short", "circle_full": "full"}
        for name, (hits, move, fly) in params.items():
            a = self.fresh("ywy_" + name, name, action_type=6 if name == "ultra" else 1)
            kind = kinds.get(name, name)
            a["ScriptCalls"].append(once(0, "YwyStart", f'kind:"{kind}"'))
            for start, end, box, ratio in hits:
                self.hit(a, kind, start, end, box, ratio, fly=fly, push=0.5 if "circle" in name else 3)
            if move:
                self.movement(a, move, 1.7 if name == "chase" else 0, 0.04, 0.2)
            if name in ("air1", "air2", "chase"):
                a["NextAction"] = "drop"; a["OnGroundAction"] = "" if name == "chase" else "dropend"
                a["OverridePhysics"] = [{"TimeRange": time_range(0, 0.22), "OverrideGravityValue": fixed(0),
                    "OverrideGroundFriction": fixed(-1), "OverrideAirDrag": {"x": fixed(0), "y": fixed(0)}, "OverrideAirFriction": fixed(-1)}]
                if name != "chase":
                    a["CDList"] = [{"Time":fixed(0), "ID":"ywy_"+name, "Duration":fixed(9999)}]
            if name == "taiji_fist":
                a["Armors"] = [{"TimeRange": time_range(0, 0.5), "Armor": 9}]
            if name in ("circle_short", "circle_full", "ultra"):
                a["ForceFields"] = [{"TimeRange": time_range(0.08, 0.45), "ConditionGroup": cond(),
                    "Area": {"Min": {"x": fixed(-5), "y": fixed(-0.4)}, "Max": {"x": fixed(5), "y": fixed(3.5)}},
                    "ForceType": 1, "Dir": 1, "FactionFilter": 2, "PushInvincipalLvl": 1,
                    "Strength": fixed(12), "StrengthY": fixed(0)}]
                a["ScriptCalls"].append(once(0.45, "YwyEmit", 'kind:"circle_follow"'))
                self.inv(a, 0, 0.15 if name != "ultra" else 1.2)
            if name == "ultra":
                a["ScriptCalls"].append(once(0.6, "YwyEmit", 'kind:"ultra"'))
            self.cancel(a, ATTACK_CANCEL[a["Name"]])
            next_attack = {"sword1": "ywy_sword2", "sword2": "ywy_sword3", "air1": "ywy_air2"}.get(name)
            if next_attack:
                a["ActionSwitchs"].insert(0, self.switch(next_attack, 4 if name == "air1" else 1, ATTACK_CANCEL[a["Name"]], 1))
            if name in ("sword1","sword2","sword3","air1","air2"):
                self.charge_entry(a)
            out.append(a)
        a = self.fresh("ywy_zhenwu", "zhenwu")
        a["ScriptCalls"] = [once(0, "YwyStart", 'kind:"zhenwu"'), once(9/60, "YwyEmit", 'kind:"zhenwu"')]
        self.cancel(a, ATTACK_CANCEL[a["Name"]]); out.append(a)
        for name, clip, kind, distance in (("dash", "dash", "dash", 3.2), ("dash2", "dash", "dash", 3.2),
                                             ("dashAir", "dash_air", "dash", 2.8), ("ywy_escape", "escape", "escape", 3.5)):
            a = self.fresh(name, clip, action_type=16 if name == "dashAir" else 0)
            a["NextAction"] = "drop" if name == "dashAir" else "stand"
            a["OnGroundAction"] = "dropend" if name == "dashAir" else ""
            a["ScriptCalls"].append(once(0, "YwyStart", f'kind:"{kind}"'))
            self.movement(a, distance, 0, 0, 0.28)
            self.inv(a, 0, 0.30)
            if name == "dashAir":
                a["CDList"] = [{"Time": fixed(0), "ID": "dashAir", "Duration": fixed(9999)}]
            self.cancel(a, 0.08)
            if name == "dash":
                a["ActionSwitchs"].insert(0, self.switch("dash2",5,0.16,55))
            out.append(a)
        # Input mode 4 is the native LongPressing condition. No HUD or wall-clock timer.
        # The first sword hit already happened; charge is free until native row activation.
        a = self.fresh("ywy_charge", "charge", action_type=1)
        a["TotalDuration"] = fixed(9999)
        a["NextAction"] = "stand"
        a["ScriptCalls"].append(once(0,"YwyStart",'kind:"charge"'))
        a["FreeMoves"] = [{"TimeRange":time_range(0,9999),"ConditionGroup":cond(),
            "Scale":{"x":fixed(.65),"y":fixed(0)},"AutoFace":1,"Invert":0,"MoveLimit":0,"UseFaceIfNoInput":0}]
        for name, at in (("ywy_circle_full",.5),("ywy_circle_short",0)):
            sw = self.switch(name,8,at,1)
            sw["ConditionGroup"] = cond(self.input(1,3,0,9999))
            a["ActionSwitchs"].append(sw)
        # If neither release row can pay, leave the charge immediately without spending.
        sw = self.switch("stand",0,0,1)
        sw["ConditionGroup"] = cond(self.input(1,3,0,9999));sw["NewActionMode"]=0;sw["SkillCheck"]=0
        a["ActionSwitchs"].append(sw)
        self.cancel(a,0)
        out.append(a)
        return out

    def bullet_tree(self, stock_bullet):
        tree = deepcopy(stock_bullet)
        tree.update(m_Name="ywybullet", AnimationJson="ywy", AnimationJsons=["ywy"])
        out = []
        ref_start = len(self.refs)
        spec = (("ywy_zhenwu_bolt", "zhenwu_wave", 90, 14, 0, 1),
                ("ywy_zhenwu_bolt_up", "zhenwu_wave", 90, 14, 2.8, 1),
                ("ywy_zhenwu_bolt_down", "zhenwu_wave", 90, 14, -2.8, 1),
                ("ywy_sword_echo", "sword_echo", 24, 9, 0, 1),
                ("ywy_attached", "sword_echo", 24, 0, 0, 3),
                ("ywy_taiji_counter", "taiji_counter", 30, 0, 0, 1),
                ("ywy_wuxiang", "wuxiang", 60, 0, 0, 3))
        for name, clip, ticks, vx, vy, hits in spec:
            a = self.fresh(name, clip, ticks)
            a["NextAction"] = "dead"; a["DropAction"] = ""; a["BehitBoxs"] = []
            a["StartSpeed"]["Speed"] = {"x": fixed(vx), "y": fixed(vy)}
            a["OverridePhysics"] = [{"TimeRange": time_range(0, ticks/60), "OverrideGravityValue": fixed(0),
                "OverrideGroundFriction": fixed(0), "OverrideAirDrag": {"x": fixed(0), "y": fixed(0)}, "OverrideAirFriction": fixed(0)}]
            bound = (-0.9, -0.7, 0.9, 0.9) if "bolt" in name or "attached" in name else (-3.5, -1.0, 3.5, 2.5)
            self.hit(a, name.removeprefix("ywy_"), 1, ticks-2, bound, 1,
                     interval=0.15 if hits > 1 else -1, max_hits=hits)
            for hit in a["HitDataList"]:
                hit["PreventHitBySameBoxType"] = 3  # native IdCasterAttackerAction, one budget per projectile
            a["ActionMaxHitCount"] = 9999
            a["ScriptCalls"].append(on_exit("YwyBulletDone"))
            if name == "ywy_attached":
                m = deepcopy(self.by_name["attackHold"]["AddMotions"][0]); mo = m["Motion"]
                m["Time"] = fixed(1/60); m["ConditionGroup"] = cond(); mo["MotionType"] = 11
                for key in ("DeltaX", "DeltaY", "TrackTargetOffsetX", "TrackTargetOffsetY", "TrackInitSpeedEx"):
                    mo[key] = expr(0)
                mo.update(DurationEx=expr(ticks/60), TrackTargetBindPos=3, MaxSpeedEx=expr(40),
                          TrackAccelerateEx=expr(200), TrackDurEx=expr(ticks/60),
                          NoTargetEndAction=1, EndMotionOnTrackArrived=0, TrackArriveDistanceEx=expr(0.1))
                a["AddMotions"] = [m]
            out.append(a)
        # These layers contain no HitData and have no SkillDamage rows. Native
        # motion follows the caster; a native action condition ends them on the
        # precise originating action instance, including cancel, hurt and death.
        for name,clip,ticks,bound in (("ywy_fx_charge","taiji_charge",60,"charge"),
                ("ywy_fx_circle","taiji_circle",48,"circle"),
                ("ywy_fx_ultra","ultra_field",90,"ultra"),
                ("ywy_fx_impact","qi_impact",24,"")):
            a = self.fresh(name,clip,ticks)
            a.update(NextAction=name if bound=="charge" else "dead",DropAction="",BehitBoxs=[])
            a["StartSpeed"]["Speed"] = {"x":fixed(0),"y":fixed(0)}
            a["OverridePhysics"] = [{"TimeRange":time_range(0,ticks/60),"OverrideGravityValue":fixed(0),
                "OverrideGroundFriction":fixed(0),"OverrideAirDrag":{"x":fixed(0),"y":fixed(0)},"OverrideAirFriction":fixed(0)}]
            # A charge loop keeps its original source-instance binding across
            # TimeEnd; only Interrupt releases it. Finite layers clean both.
            a["ScriptCalls"].append(on_exit("YwyBulletDone",4 if bound=="charge" else 6))
            if bound:
                args = f'bound:"{bound}"'
                a["ScriptCalls"].append(once(0,"YwyVisualBind",args))
                gate = self.ref("ActionLogicCondition_Script",{"Invert":1,"Call":{"Function":"YwyVisualAlive","Params":args}})
                sw = self.switch("dead",0,0,1)
                sw["ConditionGroup"]=cond(gate);sw["NewActionMode"]=0;sw["SkillCheck"]=0
                a["ActionSwitchs"].append(sw)
                m=deepcopy(self.by_name["attackHold"]["AddMotions"][0]);mo=m["Motion"]
                # CreateBulletByParams returns before TargetMgr.SetTarget. Match
                # the attached-hit setup: initialize follow on the next native tick.
                m["Time"]=fixed(1/60);m["ConditionGroup"]=cond();mo["MotionType"]=17
                for key in ("TrackCasterOffsetX","TrackCasterOffsetY","TrackTargetOffsetX","TrackTargetOffsetY"):
                    mo[key]=expr(0)
                mo.update(DurationEx=expr(ticks/60),TrackTargetBindPos=0,TrackAxis=3)
                a["AddMotions"]=[m]
            out.append(a)
        dead = self.fresh("dead", "sword_echo", 1, 8)
        dead.update(NextAction="", DropAction="", BehitBoxs=[])
        out.append(dead)
        tree["_actions"] = out
        tree["references"] = {"version": 2, "RefIds": deepcopy(self.refs[ref_start:])}
        return business(tree)


def business(tree):
    return {k: deepcopy(v) for k, v in tree.items() if k not in ("m_GameObject", "m_Enabled", "m_Script")}


def copy(table, where, changes):
    return {"$copyRows": {"where": where, "set": changes}}


def new(**kw):
    return {"$new": True, **kw}


CARDS = [
    ("剑宗", "两仪连华", "第三段剑命中后，追加前方双剑气；剑气有独立寿命和命中预算。", 1),
    ("剑宗", "真武三清", "真武剑气同时发出上、中、下三道穿透剑气，侧刃为主刃75%伤害。", 2),
    ("剑宗", "梯云追月", "流云追身剑启动时重置二段跳与空中梯云纵，使追身后能继续空战。", 3),
    ("剑宗", "剑势不绝", "短蓄与满蓄剑圈主体后追加两道前冲剑气，并返还5点真气。", 4),
    ("化境", "以静制动", "流云太极拳化劲窗由0.35秒延长至0.45秒，失败仍正常打出掌劲。", 5),
    ("化境", "云相反照", "成功化劲额外打出独立范围反击；前0.20秒精准化劲使反击再增50%。", 6),
    ("化境", "拳剑相生", "剑拳交替的首次命中额外返还5点真气，并获得3%最大生命的短盾。", 7),
    ("化境", "轻身破阵", "梯云纵后1.2秒进攻提高25%；完美闪避额外积1势，并刷新进攻窗口。", 8),
    ("无极", "圆转不息", "剑圈最多只消耗2势，仍按出手前全部势强化伤害与短盾，便于连续终结。", 9),
    ("无极", "流云归一", "绝式启动时立即恢复一次独立脱身机会；普通梯云纵仍不耗气。", 10),
    ("无极", "百川归流", "剑拳交替首次命中额外返还8点真气和4点绝式资源，支持主动循环。", 11),
    ("无极", "四象无极", "满5势时剑拳交替命中触发原生范围剑阵，并进入3秒无极进攻；剑阵至少间隔2秒。", 12),
]


def skill_rows(stock):
    rows = []
    def row(group, order, action, input, *, air=False, both=False, cost=0, direction=None, previous=None, strict=None, **kwargs):
        strict = ATTACK_CANCEL.get(action,.15) if strict is None else strict
        mute = .08 if group==5 else strict
        input_key = {"Attack":1,"Skill":3,"Ultra":4,"Dash":55}.get(input,0)
        r = new(ActorId=ACTOR, Group=group, Order=order, Action=action,
            AllowActiveState=True, AllowGround=not air or both, AllowFlying=air or both,
            AutoTurn=1, ActionpointInputTag=group, ActionpointInputTag2=1,
            Preinputtime=INPUT_BUFFER, ActdurStrict=strict, Mutelist=f'"all":{mute},"5":0.01,"7":0.10',
            StartTrigger=[] if previous else [f"Start_{group}"], Timeout=.7,
            SatisfyInputkey=[group], PreScriptCall="YwyGate")
        gate_params = f'move:"{action}", input:{input_key}, group:{group}'
        icon = 209005 if action == "ywy_taiji_fist" else 209003 if action == "ywy_chase" else 209010 if group==3 else 209009 if group==8 else 209008 if group==5 else 209002
        r["Icon"] = [{"Atlas":"UI/Atlas/IconPotential200901/IconPotential200901", "Sprite":f"Potential_{icon}"} for _ in range(2)]
        if input:r["Input"] = input
        if cost:
            r["Mps"] = [{"Slot": 2, "Limit": str(cost), "MpChange": -float(cost)}]
        if direction is not None:
            r["InputDir"] = direction
        if previous:
            r["PreSkillOrder"] = previous
        r.update(kwargs)
        if r["PreScriptCall"] != "YwyGate":
            raise ValueError("own input rows must retain the shared native action eligibility gate")
        r["PreScriptCallParams"] = gate_params + (", " + kwargs["PreScriptCallParams"] if kwargs.get("PreScriptCallParams") else "")
        rows.append(r)
    row(1, 1, "ywy_launcher", "Attack", direction=1, Timeout=0, ExitTrigger=["End_1"])
    row(1, 2, "ywy_sword1", "Attack", Timeout=.48)
    row(1, 3, "ywy_sword2", "Attack", previous=[2], Timeout=.52)
    row(1, 4, "ywy_sword3", "Attack", previous=[3], Timeout=0, ExitTrigger=["End_1"])
    row(4, 1, "ywy_air1", "Attack", air=True, Timeout=.6, PrecheckActionCd=1)
    row(4, 2, "ywy_air2", "Attack", air=True, previous=[1], Timeout=0, ExitTrigger=["End_4"], PrecheckActionCd=1)
    row(2, 1, "ywy_taiji_fist", "Skill", both=True, direction=2, cost=20, Timeout=0, ExitTrigger=["End_2"])
    row(2, 2, "ywy_chase", "Skill", both=True, direction=1, cost=25, Timeout=0, ExitTrigger=["End_2"])
    row(2, 3, "ywy_zhenwu", "Skill", both=True, cost=20, Timeout=0, ExitTrigger=["End_2"])
    row(8, 1, "ywy_circle_full", None, both=True, cost=40, Timeout=0, ExitTrigger=["End_8"])
    row(8, 2, "ywy_circle_short", None, both=True, cost=30, Timeout=0, ExitTrigger=["End_8"])
    # Qualified UI row and actual native Ultra activation are deliberately separate.
    rows.append(new(ActorId=ACTOR, Group=3, Order=1, Mps=[{"Slot": 3, "Limit": "100"}], ActionpointInputTag=3,
        Icon=[{"Atlas":"UI/Atlas/IconPotential200901/IconPotential200901","Sprite":"Potential_209010"} for _ in range(2)]))
    row(3, 2, "ywy_ultra", "Ultra", both=True,
        Mps=[{"Slot": 3, "Limit": "100", "MpChange": -100.0}], UiSkip=1, UiSkipMobile=1, Timeout=0, ExitTrigger=["End_3"])
    row(5, 1, "ywy_escape", "Dash", both=True, strict=.15, AllowActiveState=False, AllowPassiveState=True,
        PreScriptCall="YwyGate", PreScriptCallParams="escape:true")
    row(5, 2, "dash", "Dash", TurnToDrag=True, strict=.15, Timeout=.85,
        PreScriptCall="YwyGate",PreScriptCallParams="dash:1")
    row(5, 3, "dash2", "Dash", previous=[2], TurnToDrag=True, strict=.15, Timeout=0,
        ExitTrigger=["End_5"],PreScriptCallParams="dash:2")
    row(5, 4, "dashAir", "Dash", air=True, TurnToDrag=True, strict=.15, PrecheckActionCd=1)
    # Jump and equipment summon retain only generic stock rows, removing Ragna potentials.
    for src in stock:
        if src.get("ActorId") == 100101 and ((src["Group"] == 7 and src["Order"] in (1,2,3,4)) or (src["Group"] == 11 and src["Order"] == 3)):
            r = deepcopy(src); r.update(ActorId=ACTOR, **{"$new": True}); r.pop("ReqTriggerId", None)
            if r["Group"] == 7:
                # Stock jump2 has no Input because its donor tree explicitly enters
                # that mid-chain row. Own independent starts support native selection
                # and landing buffers without depending on a stale donor chain Cur.
                r.update(Input="Jump",Preinputtime=INPUT_BUFFER,StartTrigger=["Start_7"],
                    ExitTrigger=["End_7"],Timeout=0,SatisfyInputkey=[7],PreScriptCall="YwyGate",
                    PreScriptCallParams=f'move:"{r["Action"]}", input:800, group:7')
                if r["Action"] == "jump2": r["PrecheckActionCd"] = 1
            rows.append(r)
    return rows


def generate():
    build = (ROOT / "inspect/game_build.txt").read_text().strip()
    if build != "25627491":
        raise ValueError("Yuwen Yi native layout is bound to build 25627491")
    contract = read(HERE / "character-contract.json")
    input_policy = {"schema":1,"buffer":INPUT_BUFFER,"recovery":ATTACK_CANCEL,
                    "dash_cancel":.01,"jump_cancel":.10,"dash_follow":.15,"dash_attack":.08}
    write(HERE / "gen/input-policy.json",input_policy)
    stock = read(ROOT / "decoded/assets/actor_logicdata_rg.ab__rg.json")
    stock_bullet = read(ROOT / "decoded/assets/actor_logicdata_nobullet.ab__nobullet.json")
    L = Logic(stock, contract)
    actions = L.core() + L.kit()
    tree = business(stock)
    tree.update(m_Name="ywy", AnimationJson="ywy", AnimationJsons=["ywy"], _actions=actions,
                references={"version": 2, "RefIds": deepcopy(L.refs)})
    bullet = L.bullet_tree(stock_bullet)
    write(HERE / "gen/ywy_tree.json", tree)
    write(HERE / "gen/ywybullet_tree.json", bullet)
    table = {
        "HeroConfig": [copy("HeroConfig", {"Id": 100101}, {"Id": ACTOR, "LogicRes": "ywy", "Skin": ["02"],
            "MoveSpeed": 7.5, "Describe": "ywy", "MinMp": 0.0, "MaxMp": 100.0,
            "MpRecover": [0, 0, 3, 0, 0, 0, 0, 0, 0, 6.6666665, 6.6666665, 50],
            "Boxwidth": .6, "Boxheight": 1.8, "Colwidth": .72, "Colheight": 1.8})],
        "BaseActorConf": [copy("BaseActorConf", {"ActorId": 100101}, {"ActorId": ACTOR, "PotentialPoolId": ACTOR,
            "Unlocked": 1, "SortNum": 107, "PvpUnlocked": 0, "InheritSkill": [], "Name": "宇文逸", "Talents": [{"Id": 209080, "Quality": 1}]})],
        "BaseActorAttrConf": [copy("BaseActorAttrConf", {"ActorId": 100101}, {"ActorId": ACTOR,
            "Attr": [{"Type": 1, "Value": 1250.0}, {"Type": 6, "Value": 210.0}, {"Type": 18, "Value": 100.0},
                     {"Type": 92, "Value": 1.0}, {"Type": 98, "Value": 99.0}, {"Type": 115, "Value": .3}]})],
        "FesActorAttrInheritConf": [copy("FesActorAttrInheritConf", {"ActorId": 100101}, {"ActorId": ACTOR})],
        "PvpBaseActorAttrConf": [copy("PvpBaseActorAttrConf", {"ActorId": 100101}, {"ActorId": ACTOR})],
        "ActorConfig": [copy("ActorConfig", {"Id": 100101}, {"Id": ACTOR, "Paid": None, "MinPaidActorCount": 0})],
        "ClientSkinConf": [copy("ClientSkinConf", {"Id": 100101020}, {"Id": 200901020, "HeroId": ACTOR,
            "Color": "#447d9d", "SkinName": "02", "SkinNameDisplay": "武当", "VfxTintColor": "#AADDF0"})],
        "SkinUnlockConf": [copy("SkinUnlockConf", {"Id": 100101020}, {"Id": 200901020})],
        "BulletConfig": [copy("BulletConfig", {"Id": 10030101}, {"Id": BULLET, "LogicRes": "ywybullet"})],
        "SkillActivate": skill_rows(read(ROOT / "decoded/tables/SkillActivate.json.orig")),
        "SkillDamage": [], "BaseActorPotentialConf": [], "ActorActionConf": [],
        "PlayerBattleTriggerDetail": [], "BaseActorTalentQualityConf": [], "TalentEffectConf": [],
    }
    damage = {"sword1":(1,1.7), "sword2":(1,2.2), "sword3":(1,3.4), "launcher":(1,2.6),
        "air1":(4,2.1), "air2":(4,2.8), "zhenwu":(2,1), "chase":(2,4), "taiji_fist":(2,3.6),
        "circle_short":(8,5.0), "circle_full":(8,8.0), "ultra":(3,22),
        "zhenwu_bolt":(2,4.4), "zhenwu_bolt_up":(2,4.4), "zhenwu_bolt_down":(2,4.4),
        "sword_echo":(1,1.8), "attached":(8,0.65), "taiji_counter":(2,4.2), "wuxiang":(3,1.6)}
    for name, (group, value) in damage.items():
        table["SkillDamage"].append(new(ActorId=ACTOR, Action="ywy_" + name, HitTimes=1.0,
            SkillGroupId=group, FluctMin=1.0, FluctMax=1.0, DamageRatio=[value], DamageRatioPvp=[value], VibrateName="3_mid_short"))
    chs = {f"BaseActor_chs_{ACTOR}": "宇文逸", f"ActorSkill_{ACTOR}": "流云太极",
        f"ActorSkillDesc_{ACTOR}": "剑主拳辅，攻守流转。三段剑与空连回气，方向技能追身、化劲；蓄攻剑圈消耗太极势，出生自带绝式。", "ActorName_ywy": "宇文逸"}
    chs.update({f"ActorUltra_{ACTOR}":"流云太极绝式",f"ActorUltraDesc_{ACTOR}":"出生自带。消耗100点绝式资源，拳劲、剑圈、终斩三段原生范围判定；不强制扣真气。"})
    for branch, name, description, n in CARDS:
        pid = 209000 + n; action_id = 909000 + n
        table["BaseActorPotentialConf"].append(new(Id=pid, Rank=n, Label=[pid], Score=40,
            TriggerInfo={"Id": pid*10+1, "Level": 1}, OrderId=[1 if branch=="剑宗" else 2 if branch=="化境" else 3],
            ActorId=ACTOR, RelationId=[action_id], IconId=pid, New=True))
        table["ActorActionConf"].append(new(Id=action_id, ActorId=ACTOR, Type=1))
        for level in (1, 5):
            table["PlayerBattleTriggerDetail"].append(new(Idx=pid*10+1, Lvl=level, Name="宇文逸·"+name,
                Value=[0], Pvpvalue=[0], UiShowType="HideCD"))
        for key, text in (("PotentialName", name), ("PotentialDesc", description), ("ActorActionName", name),
                          ("ActorActionNameRuby", branch), ("ActorActionDesc", description)):
            chs[f"{key}_{pid if key.startswith('Potential') else action_id}"] = text
        chs[f"TriggerName_{pid*10+1}"] = name
        chs[f"TriggerDesc_{pid*10+1}"] = description
        chs[f"ActorActionInput_{action_id}"] = ""
        chs[f"ActorActionAffectedObject_{action_id}"] = branch
    moves = [
        ("武当三段剑","<action=Attack> 连按三次","快速三段剑，命中各回6、6、10点真气；第三段积1势。",0),
        ("挑空剑","↑+<action=Attack>","上挑后可接空连，免浮首领仍受到完整剑击伤害。",0),
        ("空中剑式","[空中] <action=Attack> 连按两次","出生具备两段空连；落地、二段跳重置空连次数。",0),
        ("真武剑气","<action=Skill>","消耗20真气，前方穿透剑气；固定寿命1.5秒。",20),
        ("流云追身剑","↑+<action=Skill>","消耗25真气，向前上方推进并挥斩；无目标也正常出招。",25),
        ("流云太极拳","↓+<action=Skill>","消耗20真气；前0.35秒化劲，随后主动掌劲，失败仍出招并短时减伤。",20),
        ("流云太极剑","按住<action=Attack>后释放","首剑即时出手；0.30秒转蓄，0.80秒满蓄。短蓄耗30、满蓄耗40真气；势强化剑圈并获上限15%短盾。",30),
        ("梯云纵","<action=Dash>","免费地面两次连续位移、空中一次；前0.30秒无敌，可取消攻击后摇。",0),
        ("流云太极绝式","<action=Ultra>","出生自带，消耗100绝式资源；拳劲、剑圈、终斩均有原生判定。",100),
        ("流云脱身","[普通受击] <action=Dash>","出生自带独立脱身，每7秒一次；不解死亡、剧情锁和不可解抓取。",0),
    ]
    for n,(name, inp, desc, cost) in enumerate(moves,909021):
        table["ActorActionConf"].append(new(Id=n,ActorId=ACTOR,Type=1,SkillCostOrigin=cost))
        chs.update({f"ActorActionName_{n}":name,f"ActorActionNameRuby_{n}":name,
                    f"ActorActionInput_{n}":inp,f"ActorActionDesc_{n}":desc})
    from potential_content import apply_potential_content
    write(HERE / "gen/potential-ui-contract.json",apply_potential_content(table,chs,actor_id=ACTOR,cards=CARDS))
    # Native talent is real resource recovery, with inheritance-safe level-specific rows.
    for quality in range(1, 6):
        effect = 2090800 + quality
        table["BaseActorTalentQualityConf"].append(new(TalentId=209080, Quality=quality, Score=30, TalentEffectId=effect))
        table["TalentEffectConf"].append(new(EffectId=effect, EffectType=1, Trigger=[{"TriggerId":2090801,"TriggerLevel":quality}]))
        table["PlayerBattleTriggerDetail"].append(new(Idx=2090801, Lvl=quality, Name="流云内息", Value=[quality],
            Pvpvalue=[quality], TrigType="StartStage", OPFunc="trYwyTalent", UiShowType="HideCD"))
    chs.update({"TriggerName_2090801":"流云内息", "TriggerDesc_2090801":"每秒额外恢复1～5点真气。传承给其他意识体时仍按其普通技能槽生效。"})
    for idx, kind, function, cd in ((2090901,"StartStage","trYwyStage",None),(2090902,"SuccessDodge","trYwyDodge","0.5")):
        r = new(Idx=idx, Lvl=1, Name="宇文逸原生事件·"+kind, Value=[0], Pvpvalue=[0], TrigType=kind, OPFunc=function, UiShowType="HideCD")
        if cd:r["Cd"] = cd
        table["PlayerBattleTriggerDetail"].append(r)
    content = {"tables": table, "locale": {"chs": chs, "enu": chs},
        "bundleClones": [{"from":"actor/logicdata/rg","to":"actor/logicdata/ywy",
            "rename":[["LogicData/rg.asset","LogicData/ywy.asset"]]},
            {"from":"actor/logicdata/nobullet","to":"actor/logicdata/ywybullet",
            "refTypesFrom":["actor/logicdata/rg"],
            "rename":[["LogicData/nobullet.asset","LogicData/ywybullet.asset"]]}],
        "assets": [{"bundle":"actor/touch/actorvirtualbuttonconfig.ab","asset":"ActorVirtualButtonConfig",
            "copyItems":[{"list":"actorEntries","key":"actorId","from":100101,"to":ACTOR,"set":[
                {"path":"styleEntries","value":[{"style":0,"virtualButtonEntries":[{
                    "commands":[4],"preferredSkillGroups":[3],"potentialEntries":[{
                        "actorId":ACTOR,"criteria":{"direction":0,"posture":0},
                        "icon":{"m_FileID":0,"m_PathID":0},"_1":0,"_2":0,"_3":0,"_4":0,"_5":0}]}]}]}]}]},
            {"bundle":"actor/logicdata/ywy.ab","asset":"rg","treeFile":"gen/ywy_tree.json"},
            {"bundle":"actor/logicdata/ywybullet.ab","asset":"nobullet","treeFile":"gen/ywybullet_tree.json"},
            {"bundle":"actor/buff/buff.ab","asset":"Buff","copyItems":[
                {"list":"BuffList","key":"Idx","from":"10501","to":"ywy_shield","set":[
                    {"path":"Name","value":"宇文逸·太极短盾"},{"path":"MaxStack","value":1},
                    {"path":"AddReplaceType","value":3},{"path":"AddEffects","value":[]},
                    {"path":"LogicArray","value":[{"Type":73,"ValueConstFp":fixed(1),"ValueAddForStackFp":fixed(0),
                        "OverTimeUpdateIntervalFp":fixed(0),"OnlyUpdateWhenBattleRun":0,"ScriptCall":"",
                        "ParamSet":{"ParamList":[],"ParamHintTypeInEditor":""}}]}]},
                {"list":"BuffList","key":"Idx","from":"24401_cd","to":"ywy_breath","set":[
                    {"path":"Name","value":"宇文逸·流云内息"},{"path":"MaxStack","value":1},
                    {"path":"AddReplaceType","value":3},{"path":"AddEffects","value":[]},
                    {"path":"AudioCue","value":[]},
                    {"path":"LogicArray","value":[{"Type":141,"ValueConstFp":fixed(1),"ValueAddForStackFp":fixed(0),
                        "OverTimeUpdateIntervalFp":fixed(1),"OnlyUpdateWhenBattleRun":1,"ScriptCall":"",
                        "ParamSet":{"ParamList":[{"Key":"Slot","Value":"2"}],"ParamHintTypeInEditor":"BuffLogic_MPChangeOT"}}]}]}]}],
        "js": [{"file":"data/js/gameplay/battleactor/ActorFuncs","append":
                "globalThis.BB_YWY_INPUT_POLICY="+json.dumps(input_policy,separators=(",",":"))+";"},
            {"file":"data/js/gameplay/battleactor/ActorFuncs","appendFile":"js/actor.js"},
            {"file":"data/js/gameplay/playertrigger/PlayerTriggerFuncs","appendFile":"js/triggers.js"},
            {"file":"data/js/window/battle/BattleUI","appendFile":"js/hud.js"},
            {"file":"data/js/gameplay/battle/BattleJs","appendFile":"js/lifecycle.js"},
            {"file":"data/js/core/ActorUtil","append":f"globalThis.BB_ACTOR_DONOR=globalThis.BB_ACTOR_DONOR||{{}};globalThis.BB_ACTOR_DONOR[{ACTOR}]=100101;globalThis.BB_SELF_TRIGGERS=globalThis.BB_SELF_TRIGGERS||{{}};globalThis.BB_SELF_TRIGGERS[{ACTOR}]=[2090901,2090902];"}],
        "importers": [{"script":"import_yuwen.py","args":["all"]}],
        "spriteAliases": {}, "textureAliases": {}}
    # Asset module owns only input preparation and resources; missing spec is a hard gap.
    import portraits
    art = portraits.spec()
    content["spriteAliases"].update(art.get("spriteAliases", {}))
    content["textureAliases"].update(art.get("textureAliases", {}))
    content["tables"]["HeroPortraitOffsetConfigUI"] = art["HeroPortraitOffsetConfigUI"]
    atlas = art["potentialAtlas"]
    donor, renames = atlas["donor"], atlas["rename"]
    if (not isinstance(donor,str) or not donor.startswith("ui/atlas/iconpotential") or
            donor.endswith(".ab") or ".." in donor or "\\" in donor or donor==atlas["path"]):
        raise ValueError("prepared potential atlas must provide its verified stock donor logical path")
    if (not isinstance(renames,list) or not renames or any(
            not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(v,str) or not v for v in pair)
            for pair in renames)):
        raise ValueError("prepared potential atlas must provide explicit native donor rename pairs")
    expected_icons = {f"Potential_{209000+i}" for i in range(1,13)} | {"Talent_209080","Ywy_Qi","Ywy_Taiji","Ywy_Guard"}
    if len(atlas["items"])!=16 or {item[0] for item in atlas["items"]}!=expected_icons:
        raise ValueError("prepared potential atlas must preserve all 16 owned icons")
    content["bundleClones"].append({"from":donor,
        "to":atlas["path"], "rename":renames,
        "atlasSprites":atlas["items"]})
    content["js"].append({"file":"data/js/window/battle/BattleUI","append":
        "globalThis.BB_HUD_SPRITES=globalThis.BB_HUD_SPRITES||{};" + "".join(
            f'globalThis.BB_HUD_SPRITES["{name}"]="UI/Atlas/IconPotential200901/IconPotential200901";'
            for name in [f"Potential_{209000+i}" for i in range(1,13)]+["Talent_209080","Ywy_Qi","Ywy_Taiji","Ywy_Guard"])})
    if art.get("content"):
        for k, value in art["content"].items():
            if isinstance(value, list): content.setdefault(k, []).extend(value)
            elif isinstance(value, dict): content.setdefault(k, {}).update(value)
            else: raise ValueError("unknown portrait content field: " + k)
    mod = {"id":"char-yuwen-yi","name":"宇文逸 · 流云太极","author":"local user mod","version":"0.1.0-dev",
        "description":"《逸剑风云决》宇文逸的横版动作改编；剑拳联动、梯云纵与出生完整流云太极绝式。",
        "gameBuilds":["25627491"],"dependencies":["bbee-sdk","bbee-actors"],
        "prepare":["mods/char-yuwen-yi/build_yuwen.py"],"content":content}
    from native_table_contract import audit
    write(HERE / "gen/native-table-contract.json", audit(ROOT, content, tree, bullet))
    write(HERE / "mod.json", mod)
    write(HERE / "gen/gameplay-inputs.json", {"schema":1,"actor_id":ACTOR,"build":build,
        "contract_sha256":hashlib.sha256((HERE/"character-contract.json").read_bytes()).hexdigest(),
        "native_actions":len(actions),"projectile_actions":len(bullet["_actions"]),
        "managed_conditions":len(L.refs),"source_grade":"D - BBEE adaptation; not runtime acceptance",
        "source_files":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (ROOT/"decoded/assets/actor_logicdata_rg.ab__rg.json",ROOT/"decoded/assets/actor_logicdata_nobullet.ab__nobullet.json",
             ROOT/"decoded/tables/SkillActivate.json.orig")}})
    print(json.dumps({"status":"prepared","actor_id":ACTOR,"actions":len(actions),"cards":len(CARDS)}, ensure_ascii=False))


if __name__ == "__main__":
    generate()
