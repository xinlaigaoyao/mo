"""Build 25627491 table identities audited against native and shipped JS loaders.

Dictionary-backed tables require unique final protobuf keys. Three list loaders
have no native primary key; their published composer grouping selectors and
multirow $match contract remain unchanged. No per-build dump parsing is needed.
"""

BUILD_ID = "25627491"
NATIVE_TABLE_KEYS = {
    "ActorActionConf": ("Id",),
    "ActorConfig": ("Id",),
    "BaseActorAttrConf": ("ActorId",),
    "BaseActorConf": ("ActorId",),
    "BaseActorPotentialConf": ("Id",),
    "BaseActorTalentQualityConf": ("TalentId", "Quality"),
    "BlessScreenGridConf": ("Series", "Col", "Row"),
    "BulletConfig": ("Id", "StartAction"),
    "ClientSkinConf": ("Id",),
    "FesActorAttrInheritConf": ("ActorId",),
    "HeroConfig": ("Id",),
    "HeroPortraitOffsetConfigUI": ("Id", "Key"),
    "PlayerBattleTriggerDetail": ("Idx", "Lvl"),
    "PotentialComboConf": ("Id",),
    "PvpBaseActorAttrConf": ("ActorId",),
    "SkillDamage": ("ActorId", "Action"),
    "SkillSlotBanActions": ("ActorId", "SkillSlot"),
    "SkinUnlockConf": ("Id",),
    "TalentEffectConf": ("EffectId",),
}

# These are composer grouping selectors, deliberately not native primary keys.
LIST_TABLE_KEYS = {
    "SkillActivate": ("ActorId", "Group", "Order"),
    "SkillAttr": ("ActorId", "Order"),
    "SkillFromTeacher": ("TeacherSkillId",),
}
KEY_OVERRIDES = {name: list(keys) for name, keys in {**NATIVE_TABLE_KEYS, **LIST_TABLE_KEYS}.items()}
STRING_KEYS = {("BulletConfig", "StartAction"), ("HeroPortraitOffsetConfigUI", "Key"),
               ("SkillDamage", "Action")}
NATIVE_KEY_DEFAULTS = {
    name: {key: "" if (name, key) in STRING_KEYS else 0 for key in keys}
    for name, keys in NATIVE_TABLE_KEYS.items()
}

# Paths are relative to Launcher. Pk/Get line pairs refer to dump/dump.cs.
# get_Item(int index) is an ordinal accessor, never evidence of a primary key.
KEY_EVIDENCE = {
    "ActorActionConf": {"pk_line": 170417, "get_line": 170453},
    "ActorConfig": {"loader": "decoded/data/js/gen/Xlsx.js.orig", "line": 1, "js_keys": ["id"]},
    "BaseActorAttrConf": {"pk_line": 170819, "get_line": 170855},
    "BaseActorConf": {"pk_line": 170871, "get_line": 170907},
    "BaseActorPotentialConf": {"pk_line": 170968, "get_line": 171004},
    "BaseActorTalentQualityConf": {"pk_line": 171072, "get_line": 171108},
    "BlessScreenGridConf": {"pk_line": 171429, "get_line": 171465},
    "BulletConfig": {"pk_line": 173158, "get_line": 173194},
    "ClientSkinConf": {"pk_line": 173515, "get_line": 173551},
    "FesActorAttrInheritConf": {"pk_line": 175549, "get_line": 175585},
    "HeroConfig": {"pk_line": 176554, "get_line": 176590},
    "HeroPortraitOffsetConfigUI": {"pk_line": 176606, "get_line": 176642},
    "PlayerBattleTriggerDetail": {"pk_line": 177812, "get_line": 177848},
    "PotentialComboConf": {"pk_line": 178162, "get_line": 178198},
    "PvpBaseActorAttrConf": {"pk_line": 178266, "get_line": 178302},
    "SkillDamage": {"pk_line": 179025, "get_line": 179061},
    "SkillSlotBanActions": {"pk_line": 179122, "get_line": 179158},
    "SkinUnlockConf": {"pk_line": 179174, "get_line": 179210},
    "TalentEffectConf": {"pk_line": 179413, "get_line": 179449},
    "SkillActivate": {"list_loader_line": 178930, "ordinal_get_item_line": 178953, "native_keys": []},
    "SkillAttr": {"list_loader_line": 178975, "ordinal_get_item_line": 178998, "native_keys": []},
    "SkillFromTeacher": {"list_loader_line": 179072, "ordinal_get_item_line": 179095, "native_keys": []},
}
DEFAULT_EVIDENCE = {
    "loader": "decoded/data/js/gen/pbdef.js.orig", "line": 1,
    "examples": ["BulletConfig.prototype.startAction=\"\"", "PlayerBattleTriggerDetail.prototype.lvl=0"],
    "contract": "Protobuf scalar key defaults: string empty, numeric/enum zero.",
}


def native_identity(name, row):
    """Return the protobuf-normalized identity of a known indexed table."""
    if name not in NATIVE_TABLE_KEYS:
        raise ValueError(f"{name}: no audited native dictionary key")
    defaults = NATIVE_KEY_DEFAULTS[name]
    return tuple(row.get(key, defaults[key]) for key in NATIVE_TABLE_KEYS[name])


def validate_native_keys(name, rows):
    """Reject final native duplicates even if edits used $append.

    Unknown tables and native lists retain their existing contracts. Missing
    scalar keys use protobuf defaults, including Lvl=0 and empty strings.
    """
    if name not in NATIVE_TABLE_KEYS:
        return
    seen = {}
    for index, row in enumerate(rows):
        identity = native_identity(name, row)
        try:
            previous = seen.get(identity)
        except TypeError as exc:
            raise ValueError(f"{name}: native key fields must be scalar") from exc
        if previous is not None:
            raise ValueError(f"{name}: duplicate native key {identity} at rows {previous} and {index}; "
                             "$append cannot bypass a dictionary-backed loader")
        seen[identity] = index
