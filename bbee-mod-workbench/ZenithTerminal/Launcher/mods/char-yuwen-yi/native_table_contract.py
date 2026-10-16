"""Role-owned native table and hit/damage closure checks during complete prepare.

This is a hard guard, not a replacement for the shared composer/table verifier.
SkillDamage's native key is ActorId+Action. HitTimes remains an ordinary damage
field; it must never be altered to evade an incorrect composition key.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re


KEYS = {
    "HeroConfig": ("Id",), "BaseActorConf": ("ActorId",),
    "BaseActorAttrConf": ("ActorId",), "FesActorAttrInheritConf": ("ActorId",),
    "PvpBaseActorAttrConf": ("ActorId",), "ActorConfig": ("Id",),
    "ClientSkinConf": ("Id",), "SkinUnlockConf": ("Id",),
    "BulletConfig": ("Id", "StartAction"),
    "SkillActivate": ("ActorId", "Group", "Order"),
    "SkillDamage": ("ActorId", "Action"),
    "BaseActorPotentialConf": ("Id",), "ActorActionConf": ("Id",),
    "PlayerBattleTriggerDetail": ("Idx", "Lvl"),
    "BaseActorTalentQualityConf": ("TalentId", "Quality"),
    "TalentEffectConf": ("EffectId",), "HeroPortraitOffsetConfigUI": ("Id", "Key"),
    "PotentialComboConf": ("Id",),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(name, row, fields):
    from native_table_keys import NATIVE_TABLE_KEYS, LIST_TABLE_KEYS, native_identity
    if name in NATIVE_TABLE_KEYS:
        return native_identity(name, row)
    if tuple(LIST_TABLE_KEYS.get(name, ())) != fields:
        raise ValueError("role list identity differs from the shared table contract: " + name)
    # SkillActivate's synthetic list identity contains only numeric protobuf fields.
    return tuple(row.get(field, 0) for field in fields)


def loader_evidence(text, name, fields, schema, xlsx_source):
    """Read the current dump's typed Get signature; refuse incompatible changes."""
    if name == "ActorConfig":
        registration = 'c(ActorConfig,$pb.act91.ace.ActorConfig,["id"])'
        if fields != ("Id",) or registration not in xlsx_source:
            raise ValueError("ActorConfig JS registration is absent or its real key changed")
        return {"kind": "javascript_registration", "keys": list(fields),
                "source": "decoded/data/js/gen/Xlsx.js.orig", "asserted_registration": registration,
                "note": "native protocol loader is registered in JS with keys=[id]"}
    pattern = r"public class Xlsx\.XlsxLoader_" + re.escape(name) + r"\b(?!\.)"
    match = re.search(pattern, text)
    if not match:
        raise ValueError("native loader declaration missing: " + name)
    end = text.find("\n// Namespace:", match.start())
    body = text[match.start():end]
    if name == "SkillActivate":
        if "Dictionary<" in body:
            raise ValueError("SkillActivate loader changed from native list to dictionary")
        return {"kind": "native_list_operational_identity", "keys": list(fields),
                "note": "native loader has no dictionary; role-owned Group/Order identities must be unique"}
    signature = re.search(r"public " + re.escape(name) + r" Get\(([^)]*)\)", body)
    if not signature:
        raise ValueError("native typed Get signature missing: " + name)
    known = {re.sub("_", "", value[0]).lower(): value[0] for value in schema[name].values()}
    native = []
    for param in signature.group(1).split(","):
        words = param.strip().split()
        if words[0] == "ErrType":
            continue
        key = re.sub("_", "", words[1]).lower()
        if key not in known:
            raise ValueError("native key parameter is not in current schema: " + name + "." + words[1])
        native.append(known[key])
    if tuple(native) != fields:
        raise ValueError(f"native key contract changed: {name}: {native} != {fields}")
    return {"kind": "native_dictionary", "keys": native, "get_signature": signature.group(0)}


def audit(root, content, actor_tree, bullet_tree):
    """Inspect every complete role table before publishing its generated descriptor."""
    # Imported only when root runs the entire frozen preparation batch.
    from validation_tables import normalize_message, encode_message
    from native_table_keys import NATIVE_TABLE_KEYS, LIST_TABLE_KEYS, NATIVE_KEY_DEFAULTS

    root = Path(root)
    schema_path = root / "inspect/proto_schema.json"
    schema = json.loads(schema_path.read_text("utf-8"))
    dump_path = root / "dump/dump.cs"
    dump = dump_path.read_text("utf-8")
    xlsx_path = root / "decoded/data/js/gen/Xlsx.js.orig"
    xlsx_source = xlsx_path.read_text("utf-8")
    materialized = {}
    report = {"schema": 1, "scope": "all owned native table identities, protobuf fields and action damage closure",
              "source_files": {"inspect/proto_schema.json": digest(schema_path), "dump/dump.cs": digest(dump_path),
                               "decoded/data/js/gen/Xlsx.js.orig": digest(xlsx_path),
                               "native_table_keys.py": digest(root / "native_table_keys.py")},
              "tables": [], "damage_contract": [], "status": "passed"}
    if set(content["tables"]) != set(KEYS):
        raise ValueError("every new role table must declare a native identity contract")
    for name, edits in content["tables"].items():
        source = root / "decoded/tables" / (name + ".json.orig")
        baseline = json.loads(source.read_text("utf-8"))
        fields = KEYS[name]
        shared_fields = NATIVE_TABLE_KEYS.get(name, LIST_TABLE_KEYS.get(name))
        if tuple(shared_fields or ()) != fields:
            raise ValueError("role native identity differs from the shared contract: " + name)
        evidence = loader_evidence(dump, name, fields, schema, xlsx_source)
        stock_keys = {identity(name, normalize_message(row,name,schema), fields) for row in baseline}
        rows = []
        for i, edit in enumerate(edits):
            if "$copyRows" in edit:
                copy = edit["$copyRows"]
                found = [row for row in baseline if all(row.get(k) == v for k, v in copy["where"].items())]
                if len(found) != 1:
                    raise ValueError(f"{name}[{i}]: role copy source must be exactly one native row")
                row = deepcopy(found[0]); row.update(copy.get("set", {}))
            elif edit.get("$new") or edit.get("$append"):
                row = {k: deepcopy(v) for k, v in edit.items() if not k.startswith("$")}
            else:
                raise ValueError(f"{name}[{i}]: unsupported role-owned mutation operation")
            known = {value[0] for value in schema[name].values()}
            unknown = set(row) - known - {"$opaque_proto"}
            if unknown:
                raise ValueError(f"{name}[{i}]: fields are absent from this build schema: {sorted(unknown)}")
            normalized = normalize_message(row, name, schema, path=f"{name}[{i}]")
            missing = [field for field in fields if field not in normalized and field != "StartAction"]
            if missing:
                raise ValueError(f"{name}[{i}]: newly owned rows must state native identity fields explicitly: {missing}")
            # Encode every nested value under the actual schema; do not infer a field from a similar table.
            encode_message(normalized, name, schema)
            key = identity(name, normalized, fields)
            if None in key:
                raise ValueError(f"{name}[{i}]: missing required native identity {fields}")
            if key in stock_keys or any(identity(name, old, fields) == key for old in rows):
                raise ValueError(f"{name}[{i}]: duplicate true native identity {key}")
            rows.append(normalized)
        materialized[name] = rows
        report["source_files"][str(source.relative_to(root))] = digest(source)
        report["tables"].append({"table": name, "rows": len(rows), "identity": evidence,
                                 "key_defaults": NATIVE_KEY_DEFAULTS.get(name, {field:0 for field in fields}),
                                 "native_keys": [list(identity(name, row, fields)) for row in rows]})

    actor = materialized["HeroConfig"][0]["Id"]
    all_actions = {action["Name"]: action for tree in (actor_tree, bullet_tree) for action in tree["_actions"]}
    bullet_clones=[clone for clone in content["bundleClones"] if clone.get("to")=="actor/logicdata/ywybullet"]
    if (len(bullet_clones)!=1 or bullet_clones[0].get("from")!="actor/logicdata/nobullet" or
            bullet_clones[0].get("refTypesFrom")!=["actor/logicdata/rg"]):
        raise ValueError("native bullet managed types must explicitly include the verified rg Script-condition donor")
    required_types={(ref["type"]["class"],ref["type"]["ns"],ref["type"]["asm"])
                    for ref in bullet_tree["references"]["RefIds"] if ref["type"]["class"]}
    available_types=set()
    for donor in ("rg","nobullet"):
        source=root/"decoded/assets"/f"actor_logicdata_{donor}.ab__{donor}.json"
        data=json.loads(source.read_text("utf-8-sig"))
        available_types.update((ref["type"]["class"],ref["type"]["ns"],ref["type"]["asm"])
                               for ref in data["references"]["RefIds"] if ref["type"]["class"])
        report["source_files"][str(source.relative_to(root))]=digest(source)
    if not required_types <= available_types:
        raise ValueError("native bullet managed-reference types escape the declared verified donors")
    report["managed_reference_closure"]={"bundle":"actor/logicdata/ywybullet","from":"actor/logicdata/nobullet",
        "refTypesFrom":["actor/logicdata/rg"],"required_types":[list(t) for t in sorted(required_types)],
        "scope":"stock serialized type metadata only; actor attacks/body are not imported",
        "note":"declaration/source closure; full build must serialize and re-read native ref_types"}
    main_actions = {action["Name"] for action in actor_tree["_actions"]}
    damages = {row["Action"]: row for row in materialized["SkillDamage"]}
    native_damage_keys = {(row["ActorId"], row["Action"]) for row in materialized["SkillDamage"]}
    if len(native_damage_keys) != len(damages):
        raise ValueError("SkillDamage native ActorId/Action identity is ambiguous")
    for row in materialized["SkillActivate"]:
        if row.get("Action") and row["Action"] not in main_actions:
            raise ValueError("SkillActivate action is absent from the actor logic: " + row["Action"])
        if row["ActorId"] != actor:
            raise ValueError("SkillActivate escaped the owned actor")
    # One policy is emitted before ActorFuncs and consumed by both native entry
    # paths. Guard the actual hit/cancel boundary, not merely a chain's Cur state.
    policy_prefix = "globalThis.BB_YWY_INPUT_POLICY="
    policies = [op["append"] for op in content["js"] if op.get("append", "").startswith(policy_prefix)]
    if len(policies) != 1:
        raise ValueError("owned native input policy must be emitted exactly once")
    policy = json.loads(policies[0][len(policy_prefix):].rstrip(";"))
    if policy.get("schema") != 1 or policy.get("buffer",0) < .35:
        raise ValueError("native input buffering policy is absent or truncates the finisher buffer")
    skills = {row["Action"]:row for row in materialized["SkillActivate"] if row.get("Action")}
    for name,row in skills.items():
        if row.get("PreScriptCall")=="YwyGate":
            params=row.get("PreScriptCallParams","")
            if f'move:"{name}"' not in params or "input:" not in params or f'group:{row["Group"]}' not in params:
                raise ValueError("native input row lost its common eligibility parameters: " + name)
    for name, recovery in policy["recovery"].items():
        action, row = all_actions[name], skills[name]
        ends = [hit["TickRange"]["End"]["value"]/(1<<32) for hit in action["HitDataList"]]
        if ends and recovery <= max(ends):
            raise ValueError("ordinary cancel truncates a real hit window: " + name)
        if row.get("PreScriptCall") != "YwyGate" or f'move:"{name}"' not in row.get("PreScriptCallParams",""):
            raise ValueError("native automatic skill entry escaped the current-action/input gate: " + name)
        mute = json.loads("{"+row["Mutelist"]+"}")
        if (row["ActdurStrict"] < recovery or mute["all"] < recovery or
                row.get("Preinputtime",0) < policy["buffer"] or row.get("SatisfyInputkey") != [row["Group"]]):
            raise ValueError("native skill timing/edge-consumption contract is inconsistent: " + name)
    role_dir=Path(__file__).resolve().parent
    clip_contract_path=role_dir/"character-contract.json"
    production_path=role_dir/"assets/prepared/production-manifest.json"
    clip_contract=json.loads(clip_contract_path.read_text("utf-8-sig"))
    production=json.loads(production_path.read_text("utf-8-sig"))
    phase_contract=[]
    for name in ("ywy_sword1","ywy_sword2","ywy_sword3","ywy_air1","ywy_air2","ywy_zhenwu"):
        definition=clip_contract["clips"][name]
        ticks=definition["source_keyframe_ticks"]; chain=definition["chain_after_ticks"]
        if (sum(ticks)!=definition["ticks"] or chain < sum(ticks[:-1])+2 or
                policy["recovery"][name] != chain/60):
            raise ValueError("attack cancel fails to expose the complete strike and release poses: " + name)
        prepared=production["clip_frames"][name]
        if [frame.get("exact_ticks") for frame in prepared] != ticks or any("source_weight" not in frame for frame in prepared):
            raise ValueError("prepared native animation dropped the explicit adaptation timing/provenance: " + name)
        phase_contract.append({"action":name,"source_indices":definition["source_keyframe_indices"],
            "exact_ticks":ticks,"chain_after_ticks":chain,"last_pose_visible_before_chain_ticks":chain-sum(ticks[:-1])})
    report["source_files"][str(clip_contract_path.relative_to(root))]=digest(clip_contract_path)
    report["source_files"][str(production_path.relative_to(root))]=digest(production_path)
    for name in ("ywy_sword2","ywy_sword3","ywy_air2"):
        if skills[name].get("StartTrigger") or not skills[name].get("PreSkillOrder"):
            raise ValueError("combo continuation incorrectly restarts a native chain: " + name)
    for name, group in (("ywy_sword3",1),("ywy_air2",4),("ywy_zhenwu",2),("ywy_chase",2),("ywy_taiji_fist",2)):
        if skills[name].get("ExitTrigger") != [f"End_{group}"]:
            raise ValueError("native independent skill/finisher never exits its chain: " + name)
    for name in ("jump_down","drop_down","jump","jump2"):
        if skills[name].get("Input") != "Jump" or skills[name].get("PreScriptCall") != "YwyGate":
            raise ValueError("native Jump input is not independently reachable: " + name)
    if skills["jump2"].get("PrecheckActionCd") != 1:
        raise ValueError("second jump must retain its real native action cooldown")
    if skills["dash2"].get("TimeoutAddcd",0):
        raise ValueError("ground dash recharge must not put independent air dash/escape on shared chain CD")
    button_specs = [s for s in content["assets"] if s.get("bundle")=="actor/touch/actorvirtualbuttonconfig.ab"]
    if len(button_specs)!=1 or button_specs[0].get("asset")!="ActorVirtualButtonConfig":
        raise ValueError("native Dynamic input mapping is absent")
    copies=button_specs[0].get("copyItems",[])
    if len(copies)!=1 or (copies[0].get("list"),copies[0].get("key"),copies[0].get("from"),copies[0].get("to")) != ("actorEntries","actorId",100101,actor):
        raise ValueError("native Dynamic input mapping escaped the owned actor")
    styles=copies[0]["set"][0]["value"]
    buttons=styles[0]["virtualButtonEntries"]
    entry=buttons[0]["potentialEntries"][0]
    if (len(styles)!=1 or styles[0]["style"]!=0 or len(buttons)!=1 or buttons[0]["commands"]!=[4] or
            buttons[0]["preferredSkillGroups"]!=[3] or entry["actorId"]!=actor or
            any(entry[f"_{n}"] for n in range(1,6))):
        raise ValueError("birth Ultra must have an unconditional real native Dynamic command")
    report["native_input_contract"]={"policy":policy,"skill_actions":sorted(policy["recovery"]),
        "input_api":"IInput.GetCmdStatus/GetTimeEllaps/SetPressInputSatisfied; ActionMgr.Time",
        "dynamic_command":4,"summon_command":5,
        "virtual_button_source_bundle_sha256":"1cce437b3870b0e2ee5426f6c4123af5393731dee65915e3c000b4d4a5749924",
        "animation_phase_contract":phase_contract,
        "note":"static source contract only; actual input/animation/desktop acceptance remains required"}
    hit_actions = set()
    for name, action in all_actions.items():
        hits = action["HitDataList"]
        if not hits:
            continue
        hit_actions.add(name)
        if name not in damages:
            raise ValueError("native hitting action has no own SkillDamage row: " + name)
        damage = damages[name]
        if damage["ActorId"] != actor or not math.isfinite(damage["HitTimes"]) or damage["HitTimes"] <= 0:
            raise ValueError("invalid real damage metadata: " + name)
        ratios = damage.get("DamageRatio", [])
        if not ratios or any(not math.isfinite(value) or value <= 0 for value in ratios):
            raise ValueError("native hitting action must have positive own DamageRatio: " + name)
        multipliers = []
        for hit in hits:
            start = hit["TickRange"]["Start"]["value"]
            end = hit["TickRange"]["End"]["value"]
            if not 0 <= start < end <= action["TotalDuration"]["value"]:
                raise ValueError("hit window lies outside native action duration: " + name)
            multiplier = hit["Victim"]["DamageMultiply"]["value"] / (1 << 32)
            if not math.isfinite(multiplier) or multiplier <= 0:
                raise ValueError("native hit multiplier is not positive: " + name)
            if hit["PreventHitBySameBoxIdMaxTimes"] < 1:
                raise ValueError("native hit must declare its finite per-box budget: " + name)
            multipliers.append(multiplier)
        report["damage_contract"].append({"action": name, "native_key": [actor, name],
            "skill_group": damage["SkillGroupId"], "HitTimes": damage["HitTimes"],
            "DamageRatio": ratios, "window_multipliers": multipliers,
            "note": "HitTimes is damage metadata; each hit window uses its explicit Victim.DamageMultiply"})
    if set(damages) - hit_actions != {"ywy_zhenwu"}:
        raise ValueError("unexpected damage-only actions; only the projectile source skill ywy_zhenwu may be book-only")
    visual_actions = ("ywy_fx_charge","ywy_fx_circle","ywy_fx_ultra","ywy_fx_impact")
    for name in visual_actions:
        action=all_actions[name]
        if action["HitDataList"] or action["BehitBoxs"] or name in damages:
            raise ValueError("visual-only layer acquired a combat hitbox/damage row: " + name)
        if not any(c["Call"]["Function"]=="YwyBulletDone" and c["TimeConfig"]["StartType"]==3 and
                   c["TimeConfig"]["NonTimeType"]==(4 if name=="ywy_fx_charge" else 6) for c in action["ScriptCalls"]):
            raise ValueError("visual-only layer has no native end/interrupt cleanup: " + name)
    report["visual_only_actions"]=list(visual_actions)
    triggers = {(row["Idx"], row["Lvl"]) for row in materialized["PlayerBattleTriggerDetail"]}
    for row in materialized["BaseActorPotentialConf"]:
        if (row["TriggerInfo"]["Id"], row["TriggerInfo"]["Level"]) not in triggers:
            raise ValueError("potential trigger identity is unresolved")
    from potential_content import audit_potential_content
    report["potential_ui_contract"] = audit_potential_content(content["tables"],content["locale"]["chs"],actor_id=actor)
    effects = {row["EffectId"]: row for row in materialized["TalentEffectConf"]}
    for row in materialized["BaseActorTalentQualityConf"]:
        if row["TalentEffectId"] not in effects:
            raise ValueError("talent quality effect is unresolved")
        for trigger in effects[row["TalentEffectId"]]["Trigger"]:
            if (trigger["TriggerId"], trigger["TriggerLevel"]) not in triggers:
                raise ValueError("talent trigger identity is unresolved")
    report["table_count"] = len(report["tables"])
    report["hitting_actions"] = len(hit_actions)
    report["book_only_damage_actions"] = ["ywy_zhenwu"]
    return report
