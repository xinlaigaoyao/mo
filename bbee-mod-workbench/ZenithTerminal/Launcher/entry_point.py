r"""Verified commands for the independent mod workbench.

  setup          validate dependencies, decode the physical game copy, verify baseline
  install        build first; verified save backup + plan; one install transaction
  uninstall      verified save backup + plan; one uninstall transaction
  repair-save    verified save backup; one save-repair transaction
  backup-save    explicitly bound saves -> local private verified backup
  status         installed state
  feedback       diagnostics ZIP (private save backups are never included)

The game must be closed. BBEE_SAVE_ROOT explicitly binds save-affecting commands.
This fork does not discover accounts, install packages or create game junctions.
"""
import glob
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(ROOT, "game")
AB = os.path.join(GAME, "BlazblueEntropyEffect_Data", "StreamingAssets", "ab")
BUILD_MARK = os.path.join(ROOT, "inspect", "game_build.txt")
EXE = "BlazblueEntropyEffect.exe"
PKGS = [("UnityPy", "UnityPy"), ("lz4", "lz4"), ("PIL", "Pillow"), ("numpy", "numpy")]


def say(*args):
    print(*args)
    sys.stdout.flush()


def fail(message):
    say("PROBLEM: " + message)
    raise SystemExit(1)


def need_closed():
    from safe_install import require_closed
    require_closed()


def _workbench():
    return Path(ROOT).resolve().parents[1]


def _private():
    return _workbench() / "private"


def _physical_game():
    from install_transaction import checked_path
    game = checked_path(GAME)
    if not game.is_dir() or not (game / EXE).is_file():
        fail("Prepare the independent physical Launcher/game copy before setup or install.")
    return game


def _build_id():
    build = os.environ.get("BBMOD_BUILD_ID", "").strip()
    if not re.fullmatch(r"\d+", build):
        fail("BBMOD_BUILD_ID must explicitly bind this workbench to the verified game build.")
    return build


def installed_build():
    """Compatibility accessor; explicit binding replaces Steam discovery."""
    return os.environ.get("BBMOD_BUILD_ID") or None


def setup(args):
    say("== verified workbench setup ==")
    if sys.version_info < (3, 11):
        fail("Python 3.11 or newer is required by the pinned workbench runtime.")
    missing = []
    for module, package in PKGS:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        repair = _workbench() / "requirements.lock.txt"
        fail("Missing dependencies: " + ", ".join(missing) + ". Use the bundled runtime, or explicitly repair with: "
             + f'"{sys.executable}" -m pip install -r "{repair}"')
    if shutil.which("node") is None:
        fail("Node.js is required for script syntax verification. Select the pinned workbench runtime.")
    game = _physical_game()
    if args and Path(args[0]).absolute() != game:
        fail("This fork reads only its physical Launcher/game copy; it does not create game junctions.")
    need_closed()
    build = _build_id()
    result = subprocess.run([sys.executable, "-E", "-s", "-u", os.path.join(ROOT, "pipeline.py"), ROOT,
                             "--fresh", "--strict", "--build-id", build], cwd=ROOT)
    if result.returncode:
        fail("Strict extraction failed. Setup is incomplete; inspect the decode report.")
    from validation_tables import validate_baseline
    validate_baseline(Path(ROOT), build)
    if not Path(BUILD_MARK).is_file() or Path(BUILD_MARK).read_text(encoding="utf-8").strip() != build:
        fail("Setup baseline build mark is missing or inconsistent.")
    say("Setup passed: fresh baseline hashes and decode status verified.")


def bbmod(command):
    return subprocess.run([sys.executable, "-E", "-s", "-u", os.path.join(ROOT, "bbmod.py"), command], cwd=ROOT).returncode


def prepare_mods():
    return subprocess.run([sys.executable, "-E", "-s", "-u", os.path.join(ROOT, "prepare_mods.py")], cwd=ROOT).returncode


def _bound_save_root():
    from install_transaction import checked_path
    value = os.environ.get("BBEE_SAVE_ROOT", "").strip()
    if not value:
        fail("BBEE_SAVE_ROOT must explicitly bind the save directory. Account directories are never discovered automatically.")
    root = checked_path(value)
    if not root.is_dir() or root == Path(root.anchor):
        fail("BBEE_SAVE_ROOT must name an existing, explicitly selected save directory.")
    return root


def _empty_test_root_allowed(root):
    if os.environ.get("BBEE_ALLOW_EMPTY_SAVE") != "1" or not root.is_relative_to(_workbench()):
        return False
    _physical_game()
    return True


def backup_save(tag="manual"):
    from save_safety import backup_saves, verify_backup
    root = _bound_save_root()
    try:
        result = backup_saves(root, _private() / "save-backups")
        if result["status"] == "no_saves":
            if not _empty_test_root_allowed(root):
                fail("The bound save root is empty. No backup was created; this operation stopped.")
            say("Explicit fresh workbench test save: empty; no backup was created.")
        elif result["status"] == "backed_up":
            checked = verify_backup(result["backup_dir"])
            if checked["file_count"] != result["file_count"] or checked["manifest_sha256"] != result["manifest_sha256"]:
                fail("Save backup read-back evidence changed; this operation stopped.")
            say("Verified private save backup: %d files." % result["file_count"])
        else:
            fail("The save backup did not produce a verified result; this operation stopped.")
    except SystemExit:
        raise
    except Exception as exc:
        raise RuntimeError("Save backup failed; no save or game files were changed.") from exc
    return root, result


def _recover_bound_group(root, *, repair=False):
    from install_transaction import recover_transactions
    if repair:
        from save_safety import _pending_targets
        state = _private() / "repair-transactions"
        allowed = set(save_files(root)) | _pending_targets(root, state)
        if any(not path.name.isdigit() for path in allowed):
            fail("Pending save repair contains a target outside the numeric save-slot scope.")
        if allowed:
            recover_transactions(allowed_targets=allowed, state_dir=state)
    else:
        from safe_install import paths
        _, state, _, allowed = paths(Path(ROOT))
        recover_transactions(allowed_targets=[*allowed, *save_files(root)], state_dir=state)


def save_files(root=None):
    """Numeric slots, including Backup/ColdBackup, under one explicit root."""
    from install_transaction import checked_path
    from save_safety import _scan
    root = _bound_save_root() if root is None else checked_path(root)
    files = []
    for item in _scan(root):
        path = checked_path(root / item["path"])
        if path.name.isdigit():
            files.append(path)
    return sorted(files)


def _save_codec():
    """Isolate per-plan actor ids from every other codec/imported module."""
    path = Path(ROOT) / "tools" / "savefile.py"
    spec = importlib.util.spec_from_file_location("bbee_private_save_codec_" + uuid.uuid4().hex, path)
    codec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codec)
    return codec


def enabled_actor_ids():
    """Read the actual resolved mod set of the successful staged build."""
    output = Path(os.environ.get("BBMOD_OUT", str(Path(ROOT) / "patch_out")))
    record = json.loads((output / "_build.json").read_text(encoding="utf-8"))
    identifiers = set(record["mods"])
    folders = [Path(ROOT) / "shared", Path(ROOT) / "mods"]
    folders.extend(Path(value) for value in os.environ.get("BBMOD_MODS_EXTRA", "").split(os.pathsep) if value)
    ids = set()
    for mid in identifiers:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", mid):
            raise ValueError("Invalid mod identifier in staged build record")
        existing = [folder / mid / "mod.json" for folder in folders if (folder / mid / "mod.json").is_file()]
        if len(existing) != 1:
            raise ValueError("Resolved mod source missing or ambiguous during save planning")
        content = existing[0].read_bytes()
        if record.get("descriptors", {}).get(mid) != hashlib.sha256(content).hexdigest():
            raise ValueError("Mod descriptor changed after the successful build; save planning refused")
        text = content.decode("utf-8")
        ids.update(int(value) for value in re.findall(r'"ActorId"\s*:\s*(\d{6})', text) if int(value) >= 190000)
    return ids


def clean_missing(codec, data, gone):
    """Byte-only transformation on an isolated codec; no writes or report output."""
    codec.MOD_ACTORS = set(gone)
    structural = codec.scan_custom(data)
    if not (structural or codec.pattern_hits(data)):
        return None, []
    try:
        new, report = codec.clean(data)
    except RuntimeError:
        if structural:
            raise
        return None, []  # a raw byte-pattern coincidence alone is not an actor
    return (new, report) if report else (None, [])


def plan_save_changes(root, *, remove_all=False):
    """Compute writes only; recheck original bytes under the transaction lock."""
    import lz4.frame
    from install_transaction import FileChange
    codec = _save_codec()
    gone = set(codec.MOD_ACTORS) if remove_all else set(codec.MOD_ACTORS) - enabled_actor_ids()
    if not gone:
        return []
    changes = []
    try:
        for path in save_files(root):
            original = path.read_bytes()
            decoded = lz4.frame.decompress(original)
            cleaned, report = clean_missing(codec, decoded, gone)
            if cleaned is None:
                continue
            blob = codec.compress(cleaned)
            if lz4.frame.decompress(blob) != cleaned or codec.scan_custom(cleaned) or codec.pattern_hits(cleaned):
                raise ValueError("Save transformation failed read-back/reference verification")
            changes.append(FileChange(path, data=blob, expected_sha256=hashlib.sha256(blob).hexdigest(),
                                      expected_before_sha256=hashlib.sha256(original).hexdigest(), expected_before_exists=True))
    except Exception as exc:
        raise RuntimeError("Save planning failed; the verified private backup is retained and no target was changed.") from exc
    return changes


def install(args):
    _physical_game()
    need_closed()
    from validation_tables import validate_baseline
    validate_baseline(Path(ROOT), _build_id())
    say("== prepare, build and verify before save planning ==")
    if prepare_mods():
        fail("Mod preparation failed. Build, save planning and installation were not started.")
    if bbmod("build"):
        fail("Build failed. Save planning and installation were not started.")
    _recover_bound_group(_bound_save_root())
    root, backup = backup_save("before_install")
    changes = plan_save_changes(root)
    from safe_install import install as install_group
    result = install_group(ROOT, extra_changes=changes, extra_allowed=save_files(root))
    say("Install committed with %d save changes in the same transaction." % len(changes))
    return result


def uninstall(args):
    _physical_game()
    need_closed()
    _build_id()
    _recover_bound_group(_bound_save_root())
    root, backup = backup_save("before_uninstall")
    changes = plan_save_changes(root, remove_all=True)
    from safe_install import uninstall as uninstall_group
    result = uninstall_group(ROOT, extra_changes=changes, extra_allowed=save_files(root))
    if changes and result.get("status") == "already_uninstalled":
        fail("No installed game group exists. Use repair-save for standalone save repair; no target was changed.")
    say("Uninstall completed with %d save changes in the same transaction." % len(changes))
    return result


def repair_save(args, backup=True):
    if not backup:
        fail("Skipping verified backups is disabled in this workbench.")
    need_closed()
    _recover_bound_group(_bound_save_root(), repair=True)
    root, saved = backup_save("before_repair")
    changes = plan_save_changes(root, remove_all=True)
    if not changes:
        say("Save planning found no required changes.")
        return {"status": "unchanged", "file_count": 0}
    from install_transaction import apply_transaction
    result = apply_transaction(changes, allowed_targets=[change.target for change in changes],
                               state_dir=_private() / "repair-transactions")
    say("Save repair committed: %d files; verified pre-repair backup retained privately." % len(changes))
    return result


def backup_only(args):
    need_closed()
    return backup_save("manual")


def status(args):
    return bbmod("status")


def feedback(args):
    from install_transaction import checked_path
    say("== collecting diagnostic feedback ==")
    if bbmod("report"):
        fail("Diagnostic report generation failed.")
    os.makedirs(os.path.join(ROOT, "feedback"), exist_ok=True)
    out = os.path.join(ROOT, "feedback", "TheZenithTerminal%s.zip" % time.strftime("%Y%m%d_%H%M%S"))
    diag = sorted(glob.glob(os.path.join(ROOT, "diag", "report_*")), key=os.path.getmtime)[-20:]
    reports = sorted(glob.glob(os.path.join(ROOT, "reports", "*.md")), key=os.path.getmtime)[-1:]
    extra = [path for path in (os.path.join(ROOT, "mods", "installed.json"), os.path.join(ROOT, "modlog.txt")) if os.path.isfile(path)]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in diag + reports + extra:
            checked_path(path)
            archive.write(path, os.path.relpath(path, ROOT))
    say("Diagnostics ZIP: " + out)


CMDS = {"setup": setup, "install": install, "uninstall": uninstall, "status": status, "feedback": feedback,
        "repair-save": repair_save, "backup-save": backup_only}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        say(__doc__)
        raise SystemExit(2)
    try:
        CMDS[sys.argv[1]](sys.argv[2:])
    except Exception as error:
        fail(str(error))
