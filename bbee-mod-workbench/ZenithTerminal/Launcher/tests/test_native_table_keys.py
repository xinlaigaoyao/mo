"""Native key regressions use synthetic rows, without importing bbmod or Unity."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from composer_core import ComposeError, compose_table, rowkey
from native_table_keys import KEY_OVERRIDES, NATIVE_KEY_DEFAULTS, validate_native_keys


class NativeTableKeyTests(unittest.TestCase):
    def compose(self, name, baseline, changes):
        report = []
        rows = compose_table(name, baseline, KEY_OVERRIDES[name], [("role", changes)],
                             {"role": {}}, report, key_defaults=NATIVE_KEY_DEFAULTS.get(name))
        self.assertFalse(report)
        validate_native_keys(name, rows)
        return rows

    def test_distinct_native_actions_and_layout_keys_can_be_inserted(self):
        cases = [
            ("SkillDamage", {"ActorId": 200901, "HitTimes": 1, "Action": "sword"},
             {"ActorId": 200901, "HitTimes": 1, "Action": "fist"}),
            ("HeroPortraitOffsetConfigUI", {"Id": 200901, "Key": "FesL"},
             {"Id": 200901, "Key": "FesR"}),
            ("BlessScreenGridConf", {"Series": 1, "Col": 2, "Row": 1, "BlessId": 4},
             {"Series": 1, "Col": 3, "Row": 1, "BlessId": 4}),
            ("BaseActorTalentQualityConf", {"TalentId": 209080, "Quality": 1},
             {"TalentId": 209080, "Quality": 2}),
        ]
        for name, first, second in cases:
            with self.subTest(table=name):
                result = self.compose(name, [first], [{"$new": True, **second}])
                self.assertEqual(result, [first, second])

    def test_true_native_duplicates_are_rejected_including_append(self):
        cases = [
            ("SkillDamage", {"ActorId": 200901, "Action": "sword", "HitTimes": 1}, {"HitTimes": 2}),
            ("HeroConfig", {"Id": 200901, "Quality": 1}, {"Quality": 2}),
            ("BlessScreenGridConf", {"Series": 1, "Col": 2, "Row": 1, "BlessId": 4}, {"BlessId": 5}),
            ("BaseActorConf", {"ActorId": 200901}, {"Name": "changed"}),
            ("BaseActorTalentQualityConf", {"TalentId": 209080, "Quality": 1}, {"Score": 40}),
            ("TalentEffectConf", {"EffectId": 2090801}, {"EffectType": 2}),
        ]
        for name, original, other_fields in cases:
            duplicate = {**original, **other_fields}
            with self.subTest(table=name, operation="new"):
                with self.assertRaisesRegex(ComposeError, "duplicate key"):
                    self.compose(name, [original], [{"$new": True, **duplicate}])
            with self.subTest(table=name, operation="append"):
                with self.assertRaisesRegex(ValueError, "duplicate native key"):
                    self.compose(name, [original], [{"$append": True, **duplicate}])

    def test_omitted_string_key_and_explicit_empty_string_conflict(self):
        for name, prefix, string_key in [
            ("BulletConfig", {"Id": 20090101}, "StartAction"),
            ("HeroPortraitOffsetConfigUI", {"Id": 200901}, "Key"),
            ("SkillDamage", {"ActorId": 200901}, "Action"),
        ]:
            with self.subTest(table=name):
                with self.assertRaisesRegex(ComposeError, "duplicate key"):
                    self.compose(name, [prefix], [{"$new": True, **prefix, string_key: ""}])
                # Explicit defaults must match even through a $match selector.
                result = self.compose(name, [{**prefix, "Value": 1}],
                                      [{**prefix, string_key: "", "$match": prefix, "Value": 2}])
                self.assertEqual(result[0]["Value"], 2)

    def test_trigger_omitted_level_equals_zero_but_generic_contract_is_unchanged(self):
        with self.assertRaisesRegex(ComposeError, "duplicate key"):
            self.compose("PlayerBattleTriggerDetail", [{"Idx": 2090901}],
                         [{"$new": True, "Idx": 2090901, "Lvl": 0}])
        result = self.compose("PlayerBattleTriggerDetail", [{"Idx": 2090901, "Name": "old"}],
                              [{"Idx": 2090901, "Lvl": 0, "Name": "new"}])
        self.assertEqual(result[0]["Name"], "new")
        self.assertEqual(rowkey({"Idx": 1}, ("Idx", "Lvl")), (1, 1))

    def test_native_list_tables_keep_duplicate_groups_and_explicit_match(self):
        for name, identity, selector in [
            ("SkillActivate", {"ActorId": 1, "Group": 2, "Order": 1}, "Action"),
            ("SkillAttr", {"ActorId": 1, "Order": 1}, "Level"),
            ("SkillFromTeacher", {"TeacherSkillId": 11}, "Order"),
        ]:
            values = ("first", "second") if selector == "Action" else (1, 2)
            baseline = [{**identity, selector: value, "Value": 10} for value in values]
            with self.subTest(table=name):
                result = self.compose(name, baseline,
                                      [{**identity, "$match": {selector: values[1]}, "Value": 20}])
                self.assertEqual([r["Value"] for r in result], [10, 20])
                with self.assertRaisesRegex(ComposeError, "ambiguous"):
                    self.compose(name, baseline, [{**identity, "Value": 20}])


if __name__ == "__main__":
    unittest.main()
