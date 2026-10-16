"""Dependency-free, deterministic semantics for table and exact-text JS edits.

A supplied composer key may identify several rows in a list table; edits then
need an explicit ``$match`` selector. Native indexed-table identities/defaults
and final uniqueness belong to the caller. Row ownership follows actual rows,
including after insertion and replacement.
"""
from copy import deepcopy


class ComposeError(ValueError):
    pass


def depends_on(mods, mid, target, seen=None):
    seen = set() if seen is None else seen
    if mid in seen:
        return False
    seen.add(mid)
    return any(d == target or depends_on(mods, d, target, seen)
               for d in mods.get(mid, {}).get("dependencies", []))


def rowkey(row, keys, key_defaults=None):
    defaults = key_defaults or {}
    return tuple(row.get(k, defaults.get(k, 1 if k == "Lvl" else 0)) for k in keys)


def compose_table(name, baseline, keys, edits, mods, report, key_defaults=None):
    """Return a new row list; fail on missing/ambiguous targets.

    ``$append`` deliberately permits duplicate keys, preserving multi-row table
    descriptors. ``$new`` requires a free key, and ``$copyRows`` requires one
    unless its existing ``allowDuplicateKeys`` option is explicitly true.
    Independent writes that disagree are reported and are not applied. Optional
    typed defaults normalize omitted protobuf keys in identities and selectors;
    without them the existing generic caller behavior is retained.
    """
    rows = deepcopy(baseline)
    owners = {}                         # id(row) -> field -> author
    deleted = {}                        # key -> deleting author(s)
    table_index = {}

    def identity(row):
        return rowkey(row, keys, key_defaults)

    def field_value(row, field):
        if key_defaults is not None and field in key_defaults:
            return row.get(field, key_defaults[field])
        return row.get(field)

    def matches(row, selector):
        return all(field_value(row, field) == value for field, value in selector.items())

    for row in rows:
        table_index.setdefault(identity(row), []).append(row)

    def index():
        return table_index

    def unindex(row, key):
        remaining = [candidate for candidate in table_index[key] if candidate is not row]
        if remaining:
            table_index[key] = remaining
        else:
            del table_index[key]

    def conflict(mid, row, fields, label):
        writes = owners.get(id(row), {})
        previous = {author for field, author in writes.items()
                    if field == "*" or fields is None or field in fields}
        forbidden = sorted(p for p in previous if p != mid and not depends_on(mods, mid, p))
        for previous_mid in forbidden:
            report.append(f"CONFLICT table {name} row {identity(row)} {label}: "
                          f"{previous_mid} vs {mid} (declare {previous_mid} as a dependency to override it)")
        return bool(forbidden)

    def insert(mid, value, operation, allow_duplicate=False):
        key = identity(value)
        if keys and not allow_duplicate and key in index():
            raise ComposeError(f"{mid}: {name} {operation} would duplicate key {key}")
        forbidden = [author for author in deleted.get(key, ())
                     if author != mid and not depends_on(mods, mid, author)]
        if forbidden:
            for author in sorted(forbidden):
                report.append(f"CONFLICT table {name} row {key}: {mid} recreates a row deleted by {author} "
                              f"(declare {author} as a dependency to override it)")
            return
        rows.append(value)
        table_index.setdefault(key, []).append(value)
        owners[id(value)] = {"*": mid}

    for mid, changes in edits:
        for edit in changes:
            operations = [x for x in ("$copyRows", "$append", "$new", "$delete", "$replace") if edit.get(x)]
            if len(operations) > 1:
                raise ComposeError(f"{mid}: {name} mutually exclusive operations {operations}")
            if "$copyRows" in edit:
                spec = edit["$copyRows"]
                where = spec.get("where")
                if not isinstance(where, dict) or not where:
                    raise ComposeError(f"{mid}: {name} $copyRows requires a nonempty where selector")
                source = [deepcopy(r) for r in rows if matches(r, where)]
                if not source:
                    raise ComposeError(f"{mid}: {name} $copyRows found no rows where {where}")
                for value in source:
                    value.update(deepcopy(spec.get("set", {})))
                    for rule in spec.get("setWhere", []):
                        if matches(value, rule["match"]):
                            value.update(deepcopy(rule["set"]))
                    if spec.get("idOffset") and keys and keys[0] in value:
                        value[keys[0]] += spec["idOffset"]
                    insert(mid, value, "$copyRows", bool(spec.get("allowDuplicateKeys")))
                continue
            value = {f: deepcopy(v) for f, v in edit.items() if not f.startswith("$")}
            if edit.get("$new") or edit.get("$append"):
                insert(mid, value, "$append" if edit.get("$append") else "$new", bool(edit.get("$append")))
                continue
            selector = edit.get("$match", {})
            if not isinstance(selector, dict):
                raise ComposeError(f"{mid}: {name} $match must be an object")
            if not keys and not selector:
                raise ComposeError(f"{mid}: {name} has no primary key; provide a unique $match selector")
            key = identity(edit)
            # A selector may provide the whole identity, allowing a replacement
            # to change key fields without confusing lookup with replacement.
            provided_keys = [k for k in keys if k in edit]
            if selector:
                candidates = [r for r in rows if matches(r, selector)
                              and all(field_value(r, k) == edit[k] for k in provided_keys if k not in selector)]
            else:
                candidates = index().get(key, [])
            if not candidates:
                raise ComposeError(f"{mid}: {name} row {key} selector {selector} not found (use $new to insert)")
            if len(candidates) != 1:
                raise ComposeError(f"{mid}: {name} row {key} is ambiguous ({len(candidates)} rows); "
                                   "provide a unique $match selector for this list-table row")
            row = candidates[0]
            old_key = identity(row)
            if edit.get("$delete"):
                if conflict(mid, row, None, "delete"):
                    continue
                rows[:] = [candidate for candidate in rows if candidate is not row]
                unindex(row, old_key)
                deleted.setdefault(old_key, set()).add(mid)
                continue
            if edit.get("$replace"):
                if row == value:
                    continue
                if conflict(mid, row, None, "replace"):
                    continue
                new_key = identity(value)
                if keys and new_key != old_key and index().get(new_key):
                    raise ComposeError(f"{mid}: {name} replacement would duplicate key {new_key}")
                if new_key != old_key:
                    deleted.setdefault(old_key, set()).add(mid)
                    unindex(row, old_key)
                    table_index.setdefault(new_key, []).append(row)
                row.clear()
                row.update(value)
                owners[id(row)] = {"*": mid}
                continue
            for field, new in value.items():
                if field in keys or (field in row and row[field] == new):
                    continue
                if conflict(mid, row, {field}, f"field {field}"):
                    continue
                row[field] = new
                owners.setdefault(id(row), {})[field] = mid
    return rows


def apply_js_replacements(source, replacements, mid, logical, report, anchors, mods, root, options=None):
    """Apply exact anchors. Missing anchors always fail; repeated ones opt in.

    Legacy [old,new] entries default to exactly one match. Use
    {old,new,expectedCount:N}, [old,new,{expectedCount:N}], or a script-level
    expectedCount/allowMultiple option for a deliberate multi-match edit.
    """
    options = options or {}
    for replacement in replacements:
        rules = dict(options)
        if isinstance(replacement, dict):
            old, new = replacement.get("old"), replacement.get("new")
            rules.update(replacement)
        elif isinstance(replacement, (list, tuple)) and len(replacement) in (2, 3):
            old, new = replacement[:2]
            if len(replacement) == 3:
                rules.update(replacement[2] if isinstance(replacement[2], dict) else {"expectedCount": replacement[2]})
        else:
            raise ComposeError(f"{mid}: {logical} invalid JS replacement entry")
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise ComposeError(f"{mid}: {logical} JS anchors must be nonempty strings and replacement must be text")
        expected = rules.get("expectedCount")
        if isinstance(expected, dict):
            expected = expected.get(old)
        if expected is not None and (type(expected) is not int or expected < 1):
            raise ComposeError(f"{mid}: {logical} expectedCount must be a positive integer")
        actual = source.count(old)
        expected = None if expected is None and rules.get("allowMultiple") is True else (expected if expected is not None else 1)
        if actual == 0 or (expected is not None and actual != expected):
            report.append(f"ERROR js {logical} ({mid}): anchor matched {actual}, expected "
                          f"{expected if expected is not None else 'at least 1'}: {old[:80]!r}")
            continue
        previous = anchors.get(old)
        if previous and previous != mid and not depends_on(mods, mid, previous):
            report.append(f"CONFLICT js {logical}: anchor patched by {previous} and {mid}: {old[:60]!r}")
            continue
        new = new.replace("@ROOT@", root.replace("\\", "/"))
        if old != new:
            source = source.replace(old, new)
            anchors[old] = mid
    return source
