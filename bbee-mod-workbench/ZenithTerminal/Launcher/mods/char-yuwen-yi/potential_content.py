"""Native potential presentation for Yuwen Yi, bound to build 25627491.

This module edits presentation tables only. It never unlocks combat actions or
adds a trigger callback. All twelve cards enhance the kit available at birth.
The four combination rows describe effects already produced by actor.js when
both cards are owned; they do not award a second copy of those effects.

Shipped sources (relative to Launcher, all .orig):
* Core/PotentialUtil: Type 1 roots, Type 2 additions, Inherit action trees.
* Window/Potential/WidgetActionsDesc: Label/Input/Desc and selection state.
* Window/Potential/DataActorAction: RelationId and combo-potentials ownership.
* Window/Potential/PotentialCombosBase: required-card/associated-effect panel.
* ActorActionConf 10101 (additional), 380583 (multiple inherited parents).

Ultra is InputCmd 4, not a Rewired action name. ProcessInput (native RVA
0x1C527C0) parses Rewired action names; Dynamic 61 uses DynamicCmdReplace.
UpdateDynamicCmdBinding (RVA 0x1C55DB0) defaults to Summon 5 and then uses
ActorVirtualButtonConfig's eligible single-command entry. The generator owns
Yuwen Yi's unconditional Dynamic -> Ultra entry; Summon remains the tactic.
The UI therefore uses <action=Dynamic>, never the nonexistent <action=Ultra>.
These are static code/data contracts, not runtime acceptance.
"""
from __future__ import annotations

from copy import deepcopy
import re

ACTOR = 200901
WEAVE_ACTION = 909031
ULTRA_INPUT = "<action=Dynamic>"
HI = "<color=#3AFDFFFF>"


def named(text):
    return HI + text + "</color>"


# id: name, real base-action parent, native input notation, complete effect.
# The input is also included in a localized Label because Type 2 additions
# intentionally do not render ActorActionInput on their own in the native UI.
POTENTIALS = {
    1: ("两仪连华", 909021, "【地面】<action=Attack> · <action=Attack> · <action=Attack>",
        "第三段剑首次命中敌人时，追加前方两道剑气，第二道伤害为第一道的70%。"
        "每次第三段剑只触发一次，命中多个敌人不会重复生成。剑气持续0.40秒，对同一敌人各命中至多一次。"),
    2: ("真武三清", 909024, "<action=Skill>",
        "真武剑气由一道增至上、中、下三道穿透剑气；上下侧刃伤害各为中刃的75%。"
        "每次施放只生成一组，空放也正常出招；每道持续1.50秒，对同一敌人命中至多一次，不额外消耗真气。"),
    3: ("梯云追月", 909025, "<action=MoveY+>+<action=Skill>",
        "流云追身剑启动时，立即恢复二段跳和空中梯云纵的使用次数，无需命中。"
        "可接二段跳、空中位移或空连；此效果本身不重置已用过的两段空连，二段跳仍按原有规则重置空连。"),
    4: ("剑势不绝", 909027, "长按<action=Attack>后释放",
        "短蓄或满蓄剑圈启动时立即返还5点真气；剑圈动作持续至0.45秒时，向前追加两道等伤剑气。"
        "追击不额外耗气，每道持续0.40秒、对同一敌人命中至多一次；在追击发出前取消动作不会补发。"),
    5: ("以静制动", 909026, "<action=MoveY->+<action=Skill>",
        "流云太极拳的化劲窗口由前0.35秒延长至前0.45秒。窗口内受击免除该次伤害和受击动作，"
        "成功化劲仍按原规则回气、积势；前0.20秒的精准化劲窗口不变。未化劲成功时仍正常打出主动掌劲。"),
    6: ("云相反照", 909026, "<action=MoveY->+<action=Skill> · 化劲成功",
        "化劲成功时追加一次独立范围反击；在招式前0.20秒内精准化劲，反击伤害额外提高50%。"
        "每次太极拳最多获得一次反击，且反击奖励至少间隔1秒；反击持续0.50秒，对同一敌人命中至多一次。"),
    7: ("拳剑相生", WEAVE_ACTION, "剑式 · <action=MoveY->+<action=Skill> · 剑式",
        "剑式与流云太极拳的主动掌劲交替首次命中敌人时，额外恢复5点真气，并获得相当于最大生命3%的护盾，持续3秒。"
        "只按本人动作首次命中结算，剑气或反击不会代替主动掌劲触发；相邻交替结算须间隔超过0.10秒。"),
    8: ("轻身破阵", 909028, "<action=Dash> · 进攻",
        "梯云纵启动后1.20秒内，本人直接攻击伤害提高25%，独立剑气不享受这项加成。"
        "完美闪避在原有回气奖励之外额外积1势，并刷新这1.20秒窗口；太极势上限仍为5。"),
    9: ("圆转不息", 909027, "长按<action=Attack>后释放",
        "短蓄和满蓄剑圈最多只消耗2层太极势，仍按出手前的全部势计算剑圈伤害和短盾。"
        "每层势使剑圈伤害提高10%、给予最大生命3%的盾，盾持续3秒、上限15%；5势出手可保留3势。"
        "绝式仍消耗全部势。"),
    10: ("流云归一", 909029, ULTRA_INPUT,
        "流云太极绝式启动时，立即刷新独立流云脱身的7秒冷却。"
        "随后在普通可解受击中按<action=Dash>即可脱身；不解除死亡、剧情控制或不可解抓取。"
        "绝式和普通梯云纵均出生自带，此潜能只刷新脱身机会。"),
    11: ("百川归流", WEAVE_ACTION, "剑式 · <action=MoveY->+<action=Skill> · 剑式",
        "剑式与流云太极拳主动掌劲交替首次命中敌人时，额外恢复8点真气和4点绝式资源。"
        "与拳剑相生的奖励可以叠加；只按本人动作首次命中结算，独立剑气不触发，"
        "相邻交替结算须间隔超过0.10秒，资源不超过各自100点上限。"),
    12: ("四象无极", WEAVE_ACTION, "5势 · 剑式与<action=MoveY->+<action=Skill>交替命中",
        "合法剑拳交替命中结算后达到5势时，触发范围剑阵，并进入3秒无极状态，期间本人和自有剑气伤害提高40%。"
        "剑阵至少间隔2秒、持续1秒，对同一敌人最多命中3次。只达到5势而未发生交替命中不会触发；"
        "触发本身不消耗太极势。"),
}

# The existing ten action IDs are kept. These are the native tree roots, not
# SkillActivate actions; presentation metadata cannot gate combat availability.
MOVES = {
    909021: ("武当三段剑", "【地面】<action=Attack> · <action=Attack> · <action=Attack>",
        "出生自带三段剑。各段首次命中敌人分别恢复6、6、10点真气，第三段另积1势。"
        "每段对多个敌人的命中只结算一次资源；独立剑气不重复提供这项奖励。", 0),
    909022: ("挑空剑", "【地面】<action=MoveY+>+<action=Attack>",
        "出生自带上挑剑，可衔接跳跃与空连。本人首次命中恢复6点真气；不能被挑飞的目标仍可受到剑击伤害。", 0),
    909023: ("空中剑式", "【空中】<action=Attack> · <action=Attack>",
        "出生自带两段空连，各段首次命中恢复6、10点真气，第二段另积1势。"
        "落地或使用二段跳可重置两段空连的次数。", 0),
    909024: ("真武剑气", "<action=Skill>",
        "出生自带，消耗20点真气发出前方穿透剑气，持续1.50秒。"
        "无需命中或锁定目标即可施放；按住上、下方向会分别使用追身剑、太极拳。", 20),
    909025: ("流云追身剑", "<action=MoveY+>+<action=Skill>",
        "出生自带，消耗25点真气向前上方推进并挥斩；地面、空中均可施放，无目标时也正常出招。", 25),
    909026: ("流云太极拳", "<action=MoveY->+<action=Skill>",
        "出生自带，消耗20点真气，前0.35秒可化劲，随后打出主动掌劲。化劲成功免除当次伤害及受击动作，"
        "恢复20真气、8绝式资源并积1势；前0.20秒精准化劲改为恢复25真气、12绝式资源。"
        "每次动作奖励最多一次，奖励至少间隔1秒；窗口后至动作0.50秒仍减伤70%。", 20),
    909027: ("流云太极剑", "长按<action=Attack>后释放",
        "出生自带。首剑即时出手，按住0.30秒进入蓄势，0.80秒达到满蓄；释放后短蓄消耗30真气，满蓄消耗40真气。"
        "默认消耗全部太极势，每层使剑圈伤害提高10%，并给予最大生命3%的3秒护盾，上限15%。"
        "每个命中的敌人额外附着一把有限寿命的剑气；不足30真气时释放直接结束蓄势。", 30),
    909028: ("梯云纵", "<action=Dash>",
        "出生自带，不耗真气。地面可连续位移两次，停用0.45秒后恢复；空中可用一次，落地恢复。"
        "每次前0.30秒无敌，可取消攻击后摇。完美闪避本身恢复10真气、5绝式资源，奖励至少间隔0.50秒。", 0),
    909029: ("流云太极绝式", ULTRA_INPUT,
        "出生自带，通过动态技能键施放，消耗100点绝式资源，不消耗真气。拳劲、剑圈、终斩连续攻击周围目标。"
        "消耗全部太极势，每层使本体绝式伤害提高10%，启动获得最大生命15%的3秒护盾。"
        "召唤战术仍使用<action=Summon>。", 100),
    909030: ("流云脱身", "【普通受击】<action=Dash>",
        "出生自带独立脱身，不耗真气，每7秒可用一次。只在普通可解受击中可发动，"
        "不解除死亡、剧情控制或不可解抓取；与普通梯云纵的次数分开计算。", 0),
    WEAVE_ACTION: ("拳剑流转", "剑式 · <action=MoveY->+<action=Skill> · 剑式",
        "出生机制。三段剑、挑空剑、空连、追身剑及剑圈视为剑式；与太极拳主动掌劲交替首次命中敌人时积1势。"
        "相邻交替结算须间隔超过0.10秒，剑气、反击不代替本人主动命中。太极势上限5，进入新房间会清空势、短盾和临时增伤窗口。", 0),
}

# PageActorPotential.initUI assumes every visible root has a related potential
# and dereferences GetTotalPotential(root)[0] without a null check. Birth-only
# branches therefore belong below a related root, while remaining obtained
# unconditionally (they are absent from all potential/combo RelationId lists).
BIRTH_PARENTS = {909022: 909021, 909023: 909021, 909030: 909028}

# Id -> required cards, native action ID, parent, name, exact existing synergy.
COMBINATIONS = {
    209101: ((209005, 209006), 909101, 909026, "静中反照",
        "同时获得以静制动、云相反照：可在前0.45秒内成功化劲并触发范围反击；"
        "只有前0.20秒内的精准化劲使反击伤害额外提高50%。窗口延长不会延长精准判定。"),
    209102: ((209007, 209011), 909102, WEAVE_ACTION, "百川相生",
        "同时获得拳剑相生、百川归流：每次合法剑拳交替首次命中，合计额外恢复13真气、4绝式资源，"
        "并获得最大生命3%的3秒护盾；不额外结算第二次交替或第二层势，资源受100点上限限制。"),
    209103: ((209008, 209012), 909103, WEAVE_ACTION, "轻身入无极",
        "同时获得轻身破阵、四象无极：梯云纵或完美闪避后的1.20秒窗口与3秒无极状态重叠时，"
        "本人直接攻击的两项倍率相乘，达到原伤害的175%；独立剑气只获得无极的140%。"
        "仍须5势时合法剑拳交替命中触发无极，剑阵至少间隔2秒。"),
    209104: ((209004, 209009), 909104, 909027, "圆转续剑",
        "同时获得剑势不绝、圆转不息：剑圈启动返还5真气，最多消耗2势，"
        "按出手前全部势强化伤害与盾；持续至0.45秒仍追加双剑气。"
        "5势出手保留3势，短蓄实际净耗25真气、满蓄35真气；施放前仍须具备30或40真气。"),
}

NATIVE_EVIDENCE = {
    "build_id": "25627491",
    "potential_combo_pk": {"source": "dump/dump.cs", "pk_line": 178162, "get_line": 178198, "keys": ["Id"]},
    "ultra_command": 4, "rewired_token": "Dynamic", "default_dynamic_command": 5,
    "binding_bundle": "actor/touch/actorvirtualbuttonconfig.ab",
    "binding_baseline_sha256": "1cce437b3870b0e2ee5426f6c4123af5393731dee65915e3c000b4d4a5749924",
    "binding_baseline_path_id": -5315585975808096748,
    "process_input_rva": "0x1C527C0", "update_dynamic_binding_rva": "0x1C55DB0",
}


def _index(rows, label):
    result = {}
    for row in rows:
        if "Id" not in row or row["Id"] in result:
            raise ValueError(label + " requires distinct explicit Id values")
        result[row["Id"]] = row
    return result


def _locale(chs, action_id, name, inputs, description, *, label=None):
    chs.update({f"ActorActionName_{action_id}": name,
                f"ActorActionNameRuby_{action_id}": name,
                f"ActorActionInput_{action_id}": inputs,
                f"ActorActionDesc_{action_id}": description,
                f"ActorActionAffectedObject_{action_id}": name})
    if label is not None:
        chs[f"YwyPotentialLabel_{action_id}"] = label


def apply_potential_content(table, chs, *, actor_id=ACTOR, cards=None):
    """Complete the generator-owned UI data after its ten birth move rows exist."""
    if actor_id != ACTOR:
        raise ValueError("potential presentation is bound to ActorId 200901")
    if cards is not None:
        expected = {n: POTENTIALS[n][0] for n in POTENTIALS}
        actual = {n: name for branch, name, description, n in cards}
        if len(cards) != 12 or actual != expected:
            raise ValueError("card identities changed; audit their actual gameplay before updating UI")
    actions = _index(table["ActorActionConf"], "ActorActionConf")
    potentials = _index(table["BaseActorPotentialConf"], "BaseActorPotentialConf")
    if set(potentials) != {209000 + n for n in POTENTIALS}:
        raise ValueError("expected exactly the twelve owned potential IDs")
    required = {909000 + n for n in POTENTIALS} | (set(MOVES) - {WEAVE_ACTION})
    if not required <= set(actions) or WEAVE_ACTION in actions or table.get("PotentialComboConf"):
        raise ValueError("UI generator inputs are missing, duplicated or already expanded")
    # Validate all inputs before mutating presentation data.
    if any(row.get("ActorId") != ACTOR for row in actions.values()):
        raise ValueError("UI row escaped the owned actor")
    for n in POTENTIALS:
        pid = 209000 + n
        if potentials[pid].get("RelationId") != [909000+n] or potentials[pid].get("TriggerInfo") != {"Id":pid*10+1,"Level":1}:
            raise ValueError("potential gameplay identity changed")
    table["ActorActionConf"].append({"$new": True, "Id": WEAVE_ACTION, "ActorId": ACTOR, "Type": 1})
    actions[WEAVE_ACTION] = table["ActorActionConf"][-1]
    for action_id, (name, inputs, description, cost) in MOVES.items():
        row = actions[action_id]
        row.update(Type=1, SortOrder=action_id-909020, SkillCostOrigin=cost)
        if action_id in BIRTH_PARENTS:
            row["Inherit"] = [BIRTH_PARENTS[action_id]]
        else:
            row.pop("Inherit", None)
        if action_id == 909029:
            row["IsUltraSkill"] = True
        _locale(chs, action_id, name, inputs, description)
    chs["ActorActionConfCostDesc_909027"] = "真气：短蓄30／满蓄40"
    chs["ActorActionConfCostDesc_909029"] = "绝式资源：100"
    for n, (name, parent, inputs, description) in POTENTIALS.items():
        pid, action_id = 209000+n, 909000+n
        row = actions[action_id]
        row.update(Type=2, Inherit=[parent], FromPotential=pid, SortOrder=n,
                   Label=[f"YwyPotentialLabel_{action_id}"])
        for key in ("SkillCostOrigin", "SkillCostChange", "IsUltraSkill"):
            row.pop(key, None)
        _locale(chs, action_id, name, inputs, description, label=named(name)+" · "+inputs)
        chs.update({f"PotentialName_{pid}":name, f"PotentialNameRuby_{pid}":name,
                    f"PotentialDesc_{pid}":description, f"TriggerName_{pid*10+1}":name,
                    f"TriggerDesc_{pid*10+1}":description})
    combos = []
    for combo_id, (required_cards, action_id, parent, name, description) in COMBINATIONS.items():
        table["ActorActionConf"].append({"$new":True, "Id":action_id, "ActorId":ACTOR,
            "Type":2, "Inherit":[parent], "FromPotentialCombo":combo_id, "SortOrder":100+combo_id-209100,
            "Label":[f"YwyPotentialLabel_{action_id}"]})
        combos.append({"$new":True, "Id":combo_id, "ActorId":ACTOR,
                       "Potentials":list(required_cards), "RelationId":[action_id]})
        _locale(chs, action_id, name, chs[f"ActorActionInput_{parent}"], description,
                label=named("关联效果 · "+name))
    table["PotentialComboConf"] = combos
    chs[f"ActorSkillDesc_{ACTOR}"] = "出生自带完整剑拳招式与绝式。按方向切换技能，剑拳交替积势，蓄攻释放剑圈。潜能强化既有招式；关联效果面板显示真实双卡叠加条件。"
    return audit_potential_content(table, chs, actor_id=actor_id)


def audit_potential_content(table, chs, *, actor_id=ACTOR):
    """Fail closed on the native UI graph, controls, card conditions and costs.

    Called during the one complete prepare/acceptance batch. Does not read files
    or execute gameplay; the input-asset generator separately checks its binding.
    """
    if actor_id != ACTOR:
        raise ValueError("unexpected potential UI actor")
    actions = _index(table["ActorActionConf"], "ActorActionConf")
    potentials = _index(table["BaseActorPotentialConf"], "BaseActorPotentialConf")
    combos = _index(table["PotentialComboConf"], "PotentialComboConf")
    expected_potentials = {209000+n for n in POTENTIALS}
    if set(potentials) != expected_potentials or set(combos) != set(COMBINATIONS):
        raise ValueError("potential/combo identity set changed")
    expected_actions = set(MOVES) | {909000+n for n in POTENTIALS} | {v[1] for v in COMBINATIONS.values()}
    if set(actions) != expected_actions:
        raise ValueError("potential UI action graph is incomplete or has undeclared nodes")
    visiting, visited = set(), set()
    def visit(action_id):
        if action_id in visiting:
            raise ValueError("cycle in potential Inherit graph")
        if action_id in visited:
            return
        visiting.add(action_id)
        row = actions[action_id]
        if row.get("ActorId") != ACTOR or row.get("Close"):
            raise ValueError("potential action is foreign or closed")
        for parent in row.get("Inherit", []):
            if parent not in actions or actions[parent].get("Type") != 1:
                raise ValueError("potential parent is missing or not a native Alone node")
            visit(parent)
        visiting.remove(action_id); visited.add(action_id)
    for action_id in actions:
        visit(action_id)
        for prefix in ("ActorActionName_", "ActorActionNameRuby_", "ActorActionInput_", "ActorActionDesc_"):
            text = chs.get(prefix+str(action_id))
            if not isinstance(text, str) or not text.strip() or "<action=Ultra>" in text:
                raise ValueError("missing native potential text or unsupported Ultra glyph")
            if any(token not in {"Attack","Skill","Dash","Jump","Summon","Dynamic","MoveY+","MoveY-"}
                   for token in re.findall(r"<action=([^>]+)>", text)):
                raise ValueError("unsupported potential input glyph")
        for label in actions[action_id].get("Label", []):
            if not chs.get(label):
                raise ValueError("potential label is unresolved")
    for action_id, (_, inputs, _, cost) in MOVES.items():
        row = actions[action_id]
        parents = [BIRTH_PARENTS[action_id]] if action_id in BIRTH_PARENTS else []
        if row.get("Type") != 1 or row.get("Inherit",[]) != parents or row.get("FromPotential") or row.get("FromPotentialCombo"):
            raise ValueError("birth move was incorrectly locked behind a potential")
        if row.get("SkillCostOrigin", 0) != cost or chs[f"ActorActionInput_{action_id}"] != inputs:
            raise ValueError("birth move input or cost differs from its actual kit")
    triggers = {(r["Idx"],r["Lvl"]):r for r in table["PlayerBattleTriggerDetail"]}
    for n, (name, parent, inputs, description) in POTENTIALS.items():
        pid, action_id = 209000+n, 909000+n
        row, potential = actions[action_id], potentials[pid]
        if row.get("Type") != 2 or row.get("Inherit") != [parent] or row.get("FromPotential") != pid:
            raise ValueError("potential must be an Additional child of its real birth action")
        if potential.get("RelationId") != [action_id] or potential.get("TriggerInfo") != {"Id":pid*10+1,"Level":1}:
            raise ValueError("potential RelationId/trigger closure changed")
        if chs[f"ActorActionNameRuby_{action_id}"] != name or chs[f"ActorActionInput_{action_id}"] != inputs:
            raise ValueError("potential name or input was replaced by a category/placeholder")
        if chs[f"ActorActionDesc_{action_id}"] != description or chs.get(f"PotentialDesc_{pid}") != description:
            raise ValueError("potential description drifted from the audited actual effect")
        for level in (1,5):
            if (pid*10+1,level) not in triggers or triggers[pid*10+1,level].get("OPFunc"):
                raise ValueError("potential ownership marker must not grant a duplicate effect callback")
    for combo_id, (required_cards, action_id, parent, _, description) in COMBINATIONS.items():
        row, combo = actions[action_id], combos[combo_id]
        if combo.get("ActorId") != ACTOR or combo.get("Potentials") != list(required_cards) or combo.get("RelationId") != [action_id]:
            raise ValueError("associated effect conditions or RelationId changed")
        if not set(required_cards) <= expected_potentials or row.get("Type") != 2 or row.get("Inherit") != [parent] or row.get("FromPotentialCombo") != combo_id:
            raise ValueError("associated effect native graph is unresolved")
        if chs[f"ActorActionDesc_{action_id}"] != description:
            raise ValueError("associated effect description drifted")
    roots = [i for i,row in actions.items() if not row.get("Inherit")]
    def root_for(action_id):
        parents = actions[action_id].get("Inherit",[])
        return root_for(parents[0]) if parents else action_id
    covered_roots = {root_for(action_id) for p in potentials.values() for action_id in p["RelationId"]}
    if set(roots) != covered_roots:
        raise ValueError("visible native root has no potential/icon; PageActorPotential would dereference an absent row")
    ultra_rows = [r for r in table["SkillActivate"] if r.get("ActorId")==ACTOR and r.get("Action")=="ywy_ultra"]
    if len(ultra_rows) != 1 or ultra_rows[0].get("Input") != "Ultra":
        raise ValueError("native Ultra command row is unresolved")
    if ultra_rows[0].get("Mps") != [{"Slot":3,"Limit":"100","MpChange":-100.0}]:
        raise ValueError("Ultra UI cost must match the real 100-point Slot3 deduction")
    if not actions[909029].get("IsUltraSkill") or chs["ActorActionInput_909029"] != ULTRA_INPUT:
        raise ValueError("Ultra must display its real Dynamic input and SP cost")
    # Current kit is available without a potential; UI rows must not introduce
    # a false unlock requirement through SkillActivate while adding tree nodes.
    if any(r.get("ReqTriggerId") for r in table["SkillActivate"] if r.get("ActorId")==ACTOR):
        raise ValueError("birth kit unexpectedly requires a potential trigger")
    return {"schema":1, "actor_id":ACTOR, "status":"passed",
        "scope":"native UI data closure only; actual controls, display and gameplay require runtime acceptance",
        "potentials":len(potentials), "action_nodes":len(actions), "birth_actions":len(MOVES), "visible_roots":len(roots),
        "large_icon_textures":[f"ui/texture/iconpotential/potential_{i}.ab" for i in sorted(potentials)],
        "combinations":[{"id":i,"potentials":list(v[0]),"action_id":v[1]} for i,v in COMBINATIONS.items()],
        "native_evidence":deepcopy(NATIVE_EVIDENCE),
        "extra_combat_unlocks":0, "extra_effect_callbacks":0}
