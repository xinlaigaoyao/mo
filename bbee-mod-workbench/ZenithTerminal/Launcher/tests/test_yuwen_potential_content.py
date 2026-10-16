"""Player-facing native potential contracts, run with the complete frozen batch."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROLE = Path(__file__).resolve().parents[1] / "mods" / "char-yuwen-yi"
SPEC = importlib.util.spec_from_file_location("yuwen_potential_content", ROLE / "potential_content.py")
UI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UI)


def fixture():
    # Match the public pre-integration table contract without running a role
    # generator, reading game data or constructing any install/save state.
    table = {"ActorActionConf":[], "BaseActorPotentialConf":[],
             "PlayerBattleTriggerDetail":[], "SkillActivate":[]}
    for n in range(1,13):
        pid, action = 209000+n, 909000+n
        table["ActorActionConf"].append({"$new":True,"Id":action,"ActorId":200901,"Type":1})
        table["BaseActorPotentialConf"].append({"$new":True,"Id":pid,"ActorId":200901,
            "RelationId":[action],"TriggerInfo":{"Id":pid*10+1,"Level":1}})
        for level in (1,5):
            table["PlayerBattleTriggerDetail"].append({"Idx":pid*10+1,"Lvl":level})
    for action in range(909021,909031):
        table["ActorActionConf"].append({"$new":True,"Id":action,"ActorId":200901,"Type":1})
    table["SkillActivate"] = [
        {"ActorId":200901,"Action":"ywy_sword1","Input":"Attack","Group":1,"Order":2},
        {"ActorId":200901,"Action":"ywy_ultra","Input":"Ultra","Group":3,"Order":2,
         "Mps":[{"Slot":3,"Limit":"100","MpChange":-100.0}]}]
    chs = {}
    UI.apply_potential_content(table, chs)
    return table, chs


class YuwenPotentialContentTests(unittest.TestCase):
    def test_native_tree_renders_controls_for_all_twelve_additions_without_locking_birth_kit(self):
        table, chs = fixture()
        by_id = {row["Id"]:row for row in table["ActorActionConf"]}
        roots = {row["Id"] for row in by_id.values() if not row.get("Inherit")}
        self.assertEqual(roots, set(UI.MOVES)-set(UI.BIRTH_PARENTS))
        self.assertEqual(len(table["BaseActorPotentialConf"]),12)
        for p in table["BaseActorPotentialConf"]:
            a = by_id[p["RelationId"][0]]
            self.assertEqual(a["Type"],2)
            self.assertIn(a["Inherit"][0],roots)
            # Native WidgetActionsDesc only emits Input directly for Type 1.
            # The Type 2 Label must therefore carry its controls as well.
            inputs = chs["ActorActionInput_"+str(a["Id"])]
            self.assertTrue(inputs)
            self.assertIn(inputs,"".join(chs[key] for key in a["Label"]))
        self.assertTrue(all(not by_id[r].get("FromPotential") for r in roots))
        self.assertTrue(all(not by_id[r].get("FromPotential") for r in UI.BIRTH_PARENTS))
        self.assertEqual(UI.audit_potential_content(table,chs)["extra_combat_unlocks"],0)

    def test_broken_relation_missing_parent_and_cycle_are_rejected(self):
        table, chs = fixture()
        for bad in ("relation","parent","cycle"):
            with self.subTest(bad=bad):
                changed = deepcopy(table)
                rows = {row["Id"]:row for row in changed["ActorActionConf"]}
                if bad == "relation":
                    changed["BaseActorPotentialConf"][0]["RelationId"] = [999999]
                elif bad == "parent":
                    rows[909001]["Inherit"] = [999999]
                else:
                    rows[909021]["Inherit"] = [909021]
                with self.assertRaises(ValueError):
                    UI.audit_potential_content(changed,chs)

    def test_associated_effects_require_exact_real_card_pairs_and_never_add_callbacks(self):
        table, chs = fixture()
        pairs = {row["Id"]:row["Potentials"] for row in table["PotentialComboConf"]}
        self.assertEqual(pairs,{209101:[209005,209006],209102:[209007,209011],
                                209103:[209008,209012],209104:[209004,209009]})
        changed = deepcopy(table)
        changed["PotentialComboConf"][0]["Potentials"] = [209005]
        with self.assertRaises(ValueError):
            UI.audit_potential_content(changed,chs)
        changed = deepcopy(table)
        changed["PlayerBattleTriggerDetail"][0]["OPFunc"] = "awardSecondCopy"
        with self.assertRaises(ValueError):
            UI.audit_potential_content(changed,chs)

    def test_ultra_uses_dynamic_glyph_and_real_slot3_deduction_without_fake_unlock(self):
        table, chs = fixture()
        self.assertEqual(chs["ActorActionInput_909029"],"<action=Dynamic>")
        self.assertTrue(next(r for r in table["ActorActionConf"] if r["Id"]==909029)["IsUltraSkill"])
        for bad in ("glyph","cost_slot","fake_unlock"):
            with self.subTest(bad=bad):
                changed, text = deepcopy(table), dict(chs)
                if bad == "glyph":text["ActorActionInput_909029"] = "<action=Ultra>"
                elif bad == "cost_slot":changed["SkillActivate"][1]["Mps"][0]["Slot"] = 2
                else:changed["SkillActivate"][0]["ReqTriggerId"] = 2090011
                with self.assertRaises(ValueError):
                    UI.audit_potential_content(changed,text)


if __name__ == "__main__":
    unittest.main()
