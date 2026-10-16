"""What the screens talk to: one object that reads the loader's folders and runs the loader's own commands.

The loader is KittySkin's (`Launcher\\entry_point.py` and the files beside it) and is used as it is: this module
starts `entry_point.py setup | install | uninstall | backup-save | repair-save | feedback` as child processes and
reads what they print. It changes two things itself, both of which the loader's own `bbmod.py enable / disable`
would change the same way: the list of enabled mods (`mods\\profile.json`) and, when a mod is added or deleted, the
`mods` folder.

A mod may bring `terminal.json` with its name, version and `prepare` declarations. Before installing, the window
runs the loader's guarded prepare_mods.py entry once for the effective profile. That entry resolves dependencies,
restores verified generator inputs and owns the generation cache under the build lock. An unbuilt mod can be
listed from terminal.json before its generator creates mod.json.

What a person reads about a mod is prepared here too: `known_mods.json` holds the words, pictures and placement for
the mods the Terminal knows, and any other mod's own description is shown with its developer details and
requirement sentences left out (`player_text`).
"""
import json
import os
import re
import shutil
import sys
import threading
import time
import zipfile

from PySide6.QtCore import Property, QFile, QObject, QProcess, QProcessEnvironment, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage

VERSION = "0.3.0"
HERE = os.path.dirname(os.path.abspath(__file__))
APPID = "2273430"
EXE = "BlazblueEntropyEffect.exe"
ART_DETAIL = ("art/terminal.png", "art/portrait_full.png", "art/portrait_mb.png", "art/portrait.png", "portrait.png",
              "art/card.png", "card.png")
SETTINGS = {"motion": ("full", "calm"), "startPage": ("home", "library"), "showCore": (False, True)}

INSTALL_STEPS = ["Find the game", "Read the game's data", "Back up your save", "Build your mods", "Install"]
# what the loader prints -> the step that line belongs to (the first match wins, steps only move forward)
INSTALL_MARKS = [("Game folder link", 0), ("Reading the game data", 1), ("tables decoded", 1), ("Save backed up", 2),
                 ("Removed from", 2), ("game build ", 3), ("tables:", 3), ("js:", 3), ("NEW bundle entry", 4),
                 ("installed ", 4)]
REBUILD_STEPS = ["Back up your save", "Build your mods", "Install"]
REBUILD_MARKS = [("Save backed up", 0), ("Removed from", 0), ("game build ", 1), ("tables:", 1), ("js:", 1),
                 ("NEW bundle entry", 2), ("installed ", 2)]
TAKE_OUT_STEPS = ["Back up your save", "Take it out of your save", "Rebuild your game without it"]
TAKE_OUT_MARKS = [("Save backed up", 0), ("Removed from", 1), ("game build ", 2), ("tables:", 2), ("js:", 2),
                  ("NEW bundle entry", 2), ("installed ", 2)]
REMOVE_STEPS = ["Back up and clean your save", "Remove the mods"]
REMOVE_MARKS = [("Save backed up", 0), ("Save repaired", 0), ("merge.json restored", 1), ("uninstalled", 1)]
SETUP_STEPS = ["Find the game", "Read the game's data"]
SETUP_MARKS = [("Game folder link", 0), ("Reading the game data", 1), ("tables decoded", 1)]
BACKUP_STEPS = ["Copy your save"]
BACKUP_MARKS = [("Save backed up", 0)]
REPAIR_STEPS = ["Back up your save", "Clean your save"]
REPAIR_MARKS = [("Save backed up", 0), ("Cleaned ", 1), ("Save repaired", 1), ("nothing to change", 1)]
REPORT_STEPS = ["Collect the files"]
REPORT_MARKS = [("F9 reports included", 0)]
PROBLEM = ("PROBLEM:", "REFUSING", "BUILD ABORTED")
PREPARE_STEP = "Prepare your mods"       # mods with a `prepare` list in terminal.json: made here before the install
ADD_STEPS = ["Unpack the files"]

PLAY_TEXT = "Start the game from Steam. New characters are at the end of the Prototype list."
# sentences a mod's own description may hold that the window does not show: what another game or file it wants, and
# developer details. During the alpha no character's text says that it requires anything (the lead, 2026-10-09).
_REQUIRES = re.compile(r"\brequire[sd]?\b|\bneeds? (?:bbee-|the |a |an |your )?[\w .-]{0,40}(?:sdk|dlc|install|copy|game)"
                       r"|\byour own\b.{0,60}\binstall|\bbuilt on your machine\b|\bownership\b|\bmust (?:own|have|be installed)\b",
                       re.I)
_DEV = re.compile(r"\s*\((?:actor ?id)[^)]*\)", re.I)
# loader lines about owning or having another game: not shown in the window's short log (the full log keeps them)
_OTHER_GAME = re.compile(r"(centralfiction|cross tag|bbtag)", re.I)


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (OSError, ValueError):
        return default


def player_text(text):
    """A mod's own description as the window shows it: without developer details in brackets and without the
    sentences that state what else it requires."""
    text = _DEV.sub("", str(text or "")).strip()
    kept = [part for part in re.split(r"(?<=[.!?])\s+", text) if part and not _REQUIRES.search(part)]
    return " ".join(kept)


class Controller(QObject):
    changed = Signal()
    busyChanged = Signal()
    logChanged = Signal()
    settingsChanged = Signal()
    said = Signal(str)            # one line for the person, shown above the foot of the window
    _packed = Signal(bool, str)   # a pack was unpacked on its own thread: back on the window's thread

    def __init__(self, launcher, profile_root=None, demo=False, data_dir=None, parent=None):
        super().__init__(parent)
        self.launcher = os.path.abspath(launcher)
        self.profile_root = profile_root          # a stand-in for the user's profile folder (tests only)
        self.demo = demo                          # nothing is started: the screens are driven by hand
        self.data_dir = data_dir                  # where the window keeps its own settings and its last log
        self._known = _read_json(os.path.join(HERE, "known_mods.json"), {})
        self._links = _read_json(os.path.join(HERE, "links.json"), {})
        self._settings = {key: allowed[0] for key, allowed in SETTINGS.items()}
        saved = _read_json(self._data("settings.json"), {}) if data_dir else {}
        self._settings.update({k: v for k, v in saved.items() if k in SETTINGS and v in SETTINGS[k]})
        self._measured = {}
        self._demo_enabled = None
        self._demo_disk = None
        self._mods, self._state, self._build = [], "setup", ""
        self._installed, self._installed_at = set(), ""
        self._busy = self._running = False
        self._title, self._steps, self._step = "", [], -1
        self._log, self._result, self._result_text = [], "", ""
        self._queue, self._proc, self._marks, self._problem = [], None, [], []
        self._done_text, self._after = "", ""
        self._problem_open = False
        self._prep_step = 0
        self._packed.connect(self._pack_done)
        self.refresh()

    # ---- what the folders say -------------------------------------------------------------------------------
    def _p(self, *parts):
        return os.path.join(self.launcher, *parts)

    def _data(self, *parts):
        return os.path.join(self.data_dir or "", *parts)

    def _work(self, *parts):
        """a folder or file the loader makes while it works (the game link, the data it read, save backups): under
        `temp` when the loader keeps it there, else beside the loader"""
        inside = self._p("temp", *parts)
        return inside if os.path.exists(inside) else self._p(*parts)

    def _game_build(self):
        game = self._work("game")
        if not os.path.exists(os.path.join(game, EXE)): return ""
        fork = _read_json(os.path.join(self.launcher, "..", "WORKBENCH_FORK.json"), {})
        if fork.get("game_build"):
            return str(fork["game_build"])
        manifest = os.path.join(os.path.realpath(game), "..", "..", "appmanifest_%s.acf" % APPID)
        try:
            with open(manifest, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"buildid"' in line: return line.split('"')[3]
        except OSError:
            pass
        return "?"

    def _enabled(self):
        if self.demo and self._demo_enabled is not None: return list(self._demo_enabled)
        return list(_read_json(self._p("mods", "profile.json"), {}).get("enabled", []))

    def _write_enabled(self, enabled):
        if self.demo:                             # a recording switches mods on screen only: no file is written
            self._demo_enabled = list(enabled)
            return
        path = self._p("mods", "profile.json")
        profile = _read_json(path, {"enabled": []})
        profile["enabled"] = list(enabled)
        with open(path, "w", encoding="utf-8") as f: json.dump(profile, f, indent=1)

    def _read_mods(self, build):
        enabled = set(self._enabled())
        core_on = set(_read_json(self._p("shared", "profile.json"), {}).get("enabled", []))
        out, present = [], set()
        for folder, core in (("mods", False), ("shared", True)):
            base = self._p(folder)
            for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
                meta = _read_json(os.path.join(base, name, "mod.json"), None)
                card = None if core else _read_json(os.path.join(base, name, "terminal.json"), None)
                if not isinstance(card, dict): card = {}
                built = isinstance(meta, dict) and "id" in meta
                if not built:                     # made on this PC by its `prepare` scripts: listed from its card
                    if "id" not in card: continue
                    meta = card
                mod_id, known = str(meta["id"]), self._known.get(str(meta["id"]), {})
                full = str(meta.get("name") or mod_id)
                m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", full)
                title, note = (m.group(1), m.group(2)) if m else (full, "")
                builds = [str(b) for b in meta.get("gameBuilds") or ["*"]]
                arts = self._arts(os.path.join(base, name), known.get("art"))
                adds_character = mod_id.startswith("char-") or self._adds_character(os.path.join(base, name, "mod.json"))
                present.add(mod_id)
                out.append({
                    "id": mod_id, "title": str(known.get("title") or title), "note": str(known.get("note") or note),
                    "version": str(meta.get("version", "")), "author": str(meta.get("author", "")),
                    "about": str(known.get("about") or player_text(meta.get("description"))),
                    "credit": str(known.get("credit", "")), "accent": str(known.get("accent", "")),
                    "kind": "CORE" if core else "CHARACTER" if adds_character else "MOD", "locked": core,
                    "enabled": mod_id in (core_on if core else enabled), "installed": mod_id in self._installed,
                    "compatible": not build or build == "?" or "*" in builds or build in builds,
                    "checkedOn": builds[-1] if builds else "", "needs": [str(d) for d in meta.get("dependencies") or []],
                    "art": arts[0]["src"] if arts else "", "arts": arts, "folder": os.path.join(base, name),
                    "prepare": [str(p) for p in card.get("prepare") or []], "built": built,
                    "monogram": (str(known.get("title") or title).strip()[:1] or "?").upper(),
                })
        for mod in out: mod["missing"] = [d for d in mod["needs"] if d not in present]
        order = {"CHARACTER": 0, "MOD": 1, "CORE": 2}
        out.sort(key=lambda mod: (order[mod["kind"]], mod["title"].lower()))
        return out

    # ---- a mod's pictures -----------------------------------------------------------------------------------
    @staticmethod
    def _pictures(folder):
        """a mod's own pictures when it has no single portrait: up to three from art/ or pack/art/ whose names say
        artwork or portrait, in name order (the first is shown in front)"""
        found = []
        for sub in ("art", os.path.join("pack", "art")):
            d = os.path.join(folder, sub)
            for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                if n.lower().endswith(".png") and ("artwork" in n.lower() or "portrait" in n.lower()):
                    found.append(os.path.join(d, n))
        return found[:3]

    def _measure(self, path):
        """(width, height, left, top, right, bottom): the picture's size and the box its figure fills, as shares of
        the picture. Read once per file from a small copy of its transparency."""
        try: key = (path, os.path.getmtime(path))
        except OSError: return None
        if key not in self._measured:
            image = QImage(path)
            w, h, box = image.width(), image.height(), (0.0, 0.0, 1.0, 1.0)
            if w and h and image.hasAlphaChannel():
                small = image.scaled(96, 96).convertToFormat(QImage.Format.Format_Alpha8)
                line, bits = small.bytesPerLine(), bytes(small.constBits())
                rows = [y for y in range(96) if any(v > 8 for v in bits[y * line:y * line + 96])]
                cols = [x for x in range(96) if any(bits[y * line + x] > 8 for y in range(96))]
                if rows and cols:
                    box = (cols[0] / 96, rows[0] / 96, (cols[-1] + 1) / 96, (rows[-1] + 1) / 96)
            self._measured[key] = (w, h) + box if w and h else None
        return self._measured[key]

    def _arts(self, folder, listed):
        """The pictures the window shows for a mod, each with where it stands. `listed` is the mod's entry in
        known_mods.json when it has one: [{"file", "focus": [x, y], "tall", "dx", "dy", "z", "dim"}]; without one the
        mod's own portrait is found (or up to three artworks) and placed by rule.
          tall     the figure's height as a share of the window's
          fx, fy   where the face is, as shares of the picture (the small cards are cut around it)
          card     the figure's height on a small card, in pixels (500: head and shoulders)
          stand    false: one figure, its face (ax, ay) put dx, dy window heights from the stage's focus point;
                   true: one of a party, the foot of its box (ax, ay) put dx window heights beside the focus
                   point and dy window heights above the stage's ground line"""
        if listed:
            files = [(os.path.join(folder, *str(entry.get("file", "")).split("/")), entry) for entry in listed]
        else:
            one = next((os.path.join(folder, *rel.split("/")) for rel in ART_DETAIL
                        if os.path.isfile(os.path.join(folder, *rel.split("/")))), "")
            files = [(path, {}) for path in ([one] if one else self._pictures(folder))]
        files = [(path, entry, self._measure(path)) for path, entry in files if os.path.isfile(path)]
        files = [f for f in files if f[2]]
        party = len(files) > 1
        slots = [(0.0, 0.0, 0.60, 3, 1.0), (-0.27, 0.04, 0.50, 1, 0.9), (0.24, 0.012, 0.70, 2, 0.94)]
        out = []
        for i, (path, entry, (w, h, l, t, r, b)) in enumerate(files):
            shape = ((r - l) * w) / max(1.0, (b - t) * h)
            fx, fy = entry.get("focus") or ((l + r) / 2, t + 0.2 * (b - t))
            dx, dy, tall, z, dim = slots[min(i, 2)] if party else (0.0, 0.0, 1.34 if shape < 0.62 else 1.12 if shape < 0.9 else 1.0, 1, 1.0)
            ax, ay = ((l + r) / 2, b) if party else (fx, fy)
            out.append({"src": QUrl.fromLocalFile(path).toString(), "w": w, "h": h, "l": l, "t": t, "r": r, "b": b,
                        "fx": float(fx), "fy": float(fy), "ax": float(entry.get("ax", ax)), "ay": float(entry.get("ay", ay)),
                        "tall": float(entry.get("tall", tall)), "dx": float(entry.get("dx", dx)),
                        "dy": float(entry.get("dy", dy)), "z": int(entry.get("z", z)), "dim": float(entry.get("dim", dim)),
                        "stand": party, "card": float(entry.get("card", 500))})
        return out

    @staticmethod
    def _adds_character(mod_json):
        """a mod whose data names a new playable character (the ids added characters use start at 190000)"""
        try:
            with open(mod_json, encoding="utf-8") as f: text = f.read()
        except OSError:
            return False
        return any(int(n) >= 190000 for n in re.findall(r'"ActorId":\s*(\d{6})', text))

    @Slot()
    def refresh(self):
        build = self._game_build()
        mark = ""
        try:
            with open(self._work("inspect", "game_build.txt"), encoding="utf-8") as f: mark = f.read().strip()
        except OSError:
            pass
        done = _read_json(self._p("mods", "installed.json"), None)
        has_mod_file = os.path.exists(os.path.join(self._work("game"), "BlazblueEntropyEffect_Data", "StreamingAssets", "ab", "m_mod.m"))
        if self.demo:                             # a recording reads the folders once and keeps that picture
            if self._demo_disk is None: self._demo_disk = (build, mark, done, has_mod_file)
            build, mark, done, has_mod_file = self._demo_disk
        in_game = bool(done and has_mod_file and build)
        self._installed = set(done.get("enabled", list(done.get("mods", {})))) if in_game else set()
        self._installed_at = str(done.get("installed", "")) if in_game else ""
        if not build: state = "no-game"
        elif mark != build: state = "setup"
        elif not in_game: state = "ready"
        else:
            core = _read_json(self._p("shared", "profile.json"), {}).get("enabled", [])
            want = set(self._enabled()) | set(core)
            state = "installed" if self._installed == want else "changes"
        self._build, self._state, self._mods = build, state, self._read_mods(build)
        self.changed.emit()

    def _mod(self, mod_id):
        return next((mod for mod in self._mods if mod["id"] == mod_id), None)

    def _wanted(self):
        """the mods a person switched on (core files are not counted: they go in with any mod)"""
        return [mod for mod in self._mods if mod["enabled"] and not mod["locked"]]

    @Property("QVariantList", notify=changed)
    def mods(self): return self._mods

    @Property(str, notify=changed)
    def state(self): return self._state

    @Property(str, notify=changed)
    def gameBuild(self): return self._build

    @Property(str, notify=changed)
    def gamePath(self):
        game = self._p("game")
        return os.path.realpath(game) if os.path.exists(os.path.join(game, EXE)) else ""

    @Property(str, notify=changed)
    def installedAt(self): return self._installed_at

    @Property(int, notify=changed)
    def backups(self):
        folder = self._backup_directory()
        return len([n for n in os.listdir(folder) if os.path.isdir(os.path.join(folder, n))]) if os.path.isdir(folder) else 0

    def _backup_directory(self):
        if os.path.isfile(os.path.join(self.launcher, "..", "WORKBENCH_FORK.json")):
            return os.path.abspath(os.path.join(self.launcher, "..", "..", "private", "save-backups"))
        return self._p("save_backups")

    @Property(str, notify=changed)
    def stateText(self):
        on = len(self._wanted())
        mods = "%d mod%s" % (on, "" if on == 1 else "s")
        return {"no-game": "The game has not been found yet", "setup": "The game's data has to be read first",
                "ready": "%s ready to install" % mods if on else "Nothing switched on",
                "changes": "Changes not applied yet", "installed": "%s installed" % mods}[self._state]

    @Property(str, notify=changed)
    def actionLabel(self):
        return {"no-game": "SET UP AND INSTALL", "setup": "SET UP AND INSTALL", "ready": "INSTALL",
                "changes": "APPLY CHANGES", "installed": "PLAY"}[self._state]

    @Property(bool, notify=changed)
    def canAct(self):
        """the big button has something to do (with nothing switched on and nothing installed it has not)"""
        return self._state in ("changes", "installed") or bool(self._wanted())

    # ---- the window's own settings, links and facts -----------------------------------------------------------
    @Property("QVariantMap", notify=settingsChanged)
    def settings(self): return dict(self._settings)

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        if key not in SETTINGS or value not in SETTINGS[key] or self._settings.get(key) == value: return
        self._settings[key] = value
        if self.data_dir and not self.demo:
            try:
                os.makedirs(self.data_dir, exist_ok=True)
                with open(self._data("settings.json"), "w", encoding="utf-8") as f: json.dump(self._settings, f, indent=1)
            except OSError:
                pass
        self.settingsChanged.emit()

    @Property("QVariantList", constant=True)
    def supporters(self): return list(self._links.get("support", []))

    @Property(str, constant=True)
    def version(self): return VERSION

    @Slot(str)
    def openLink(self, url):
        """opens one of the Terminal's own links in the person's browser (no other address is ever opened)"""
        if url not in [str(entry.get("url")) for entry in self.supporters]: return
        if self.demo: self.said.emit("Preview: the link is not opened from a recording."); return
        QDesktopServices.openUrl(QUrl(url))

    @Slot(str)
    def copyLink(self, url):
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication) and not self.demo: app.clipboard().setText(url)
        self.said.emit("Link copied.")

    # ---- the running job ------------------------------------------------------------------------------------
    @Property(bool, notify=busyChanged)
    def busy(self): return self._busy

    @Property(bool, notify=busyChanged)
    def running(self): return self._running

    @Property(str, notify=busyChanged)
    def title(self): return self._title

    @Property("QVariantList", notify=busyChanged)
    def steps(self): return self._steps

    @Property(int, notify=busyChanged)
    def step(self): return self._step

    @Property(str, notify=busyChanged)
    def result(self): return self._result

    @Property(str, notify=busyChanged)
    def resultText(self): return self._result_text

    @Property(str, notify=busyChanged)
    def resultAction(self):
        """what the finished job offers next: "play", "folder" (open what it made) or nothing"""
        return self._after if self._result == "ok" else ""

    @Property("QVariantList", notify=logChanged)
    def logTail(self):
        return [line for line in self._log if not _OTHER_GAME.search(line)][-7:]

    def _begin(self, title, steps, marks, done="", after=""):
        self._busy = self._running = True
        self._title, self._steps, self._step, self._marks = title, list(steps), 0, marks
        self._log, self._result, self._result_text, self._problem = [], "", "", []
        self._done_text, self._after, self._problem_open = done, after, False
        self.busyChanged.emit(); self.logChanged.emit()

    def _line(self, text):
        text = text.rstrip()
        if not text:
            self._problem_open = False
            return
        self._log.append(text)
        del self._log[:-600]
        if text.startswith(PROBLEM) or self._problem_open:
            self._problem_open = True
            self._problem.append(text.replace("PROBLEM: ", ""))
        for mark, step in self._marks:
            if mark in text:
                if step > self._step: self._step = step; self.busyChanged.emit()
                break
        self.logChanged.emit()

    def _finish(self, ok, text=""):
        self._running, self._result = False, "ok" if ok else "error"
        if ok: self._step = len(self._steps)
        self._result_text = text
        if self.data_dir and not self.demo:
            try:
                os.makedirs(self.data_dir, exist_ok=True)
                with open(self._data("last_run.log"), "w", encoding="utf-8") as f:
                    f.write("%s  %s  %s\n\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), self._title, self._result))
                    f.write("\n".join(self._log) + "\n")
            except OSError:
                pass
        self.refresh(); self.busyChanged.emit()

    def _python(self):
        bundled = os.path.join(self.launcher, "..", "Interpreter", "pythoncore-3.14-64", "python.exe")
        if os.path.exists(bundled): return os.path.abspath(bundled)
        exe = sys.executable
        console = os.path.join(os.path.dirname(exe), "python.exe")
        return console if os.path.basename(exe).lower() == "pythonw.exe" and os.path.exists(console) else exe

    def _next(self):
        if not self._queue:
            self._finish(True, self._done_text)
            return
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        if os.path.isfile(os.path.join(self.launcher, "..", "WORKBENCH_FORK.json")):
            import importlib.util
            path = os.path.abspath(os.path.join(self.launcher, "..", "..", "scripts", "workbench.py"))
            spec = importlib.util.spec_from_file_location("zenith_workbench_environment", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            env = QProcessEnvironment()
            for key, value in module.environment().items():
                env.insert(key, value)
        env.insert("PYTHONIOENCODING", "utf-8"); env.insert("PYTHONUNBUFFERED", "1")
        if self.profile_root: env.insert("USERPROFILE", self.profile_root)
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(self.launcher)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: [self._line(l) for l in
                                                      bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").splitlines()])
        proc.finished.connect(self._ended)
        proc.errorOccurred.connect(lambda error: self._finish(False, "The loader could not be started (%s)." % error.name)
                                   if error == QProcess.ProcessError.FailedToStart else None)
        self._proc = proc
        item = self._queue.pop(0)
        if item[0] == "@prepare":                 # one guarded profile-wide preparation entry
            self._line("Preparing %s..." % item[1])
            if self._prep_step > self._step: self._step = self._prep_step; self.busyChanged.emit()
            proc.start(self._python(), ["-E", "-s", "-u", os.path.join(self.launcher, "prepare_mods.py")])
        else:
            proc.start(self._python(), ["-E", "-s", "-u", "entry_point.py"] + item)

    def _ended(self, code, _status):
        if not self._running: return
        if code != 0:
            self._queue = []
            said = "\n".join(self._problem) or "\n".join(self._log[-3:])
            self._finish(False, said)
        else:
            self._next()

    def _run(self, title, steps, marks, queue, done, after=""):
        if self._busy or self.demo: return
        self._begin(title, steps, marks, done, after)
        self._queue = list(queue)
        self._next()

    def _install_job(self, title, done, after="play", steps=REBUILD_STEPS, marks=REBUILD_MARKS):
        """build and install what is switched on; the game's data is read first when that has not been done for
        this build of the game"""
        first = self._state in ("no-game", "setup")
        steps, marks = (INSTALL_STEPS, INSTALL_MARKS) if first else (steps, marks)
        # Always let the CLI inspect the effective profile, including terminal
        # dependencies that are absent from the top-level visible mod list.
        # Its cache hit is read-only and the GUI never writes prepare states.
        prepare = [["@prepare", "your mods"]]
        at = 2 if first else 0
        steps = list(steps[:at]) + [PREPARE_STEP] + list(steps[at:])
        marks = [(mark, step + 1 if step >= at else step) for mark, step in marks]
        self._prep_step = at
        self._run(title, steps, marks, ([["setup"]] if first else []) + prepare + [["install"]], done, after)

    @Slot()
    def primary(self):
        """the one big button: set up if needed and install, apply what was switched, or start the game"""
        if self._busy: return
        if self._state == "installed": self.play(); return
        if self._state == "changes" and not self._wanted():        # everything was switched off: take it all out
            self.uninstall(); return
        if not self._wanted(): self.said.emit("Switch a mod on in the Library first."); return
        self._install_job("APPLYING CHANGES" if self._state == "changes" else "INSTALLING", PLAY_TEXT)

    @Slot()
    def uninstall(self):
        self._run("UNINSTALLING EVERY MOD", REMOVE_STEPS, REMOVE_MARKS, [["uninstall"]],
                  "Your game and your save are back to normal. Your mods stay in the Library.")

    @Slot(str)
    def uninstallMod(self, mod_id):
        """Take one mod out of the game. It is switched off, then the game is rebuilt with what is left (the loader
        backs the save up and takes the character out of it); with nothing left, everything is removed."""
        mod = self._mod(mod_id)
        if self._busy or self.demo or not mod or mod["locked"]: return
        self._write_enabled([i for i in self._enabled() if i != mod_id])
        self.refresh()
        title = "UNINSTALLING " + mod["title"].upper()
        if self._wanted():
            self._install_job(title, "%s is out of your game. Its files stay in the Library." % mod["title"], after="",
                              steps=TAKE_OUT_STEPS, marks=TAKE_OUT_MARKS)
        else:
            self._run(title, REMOVE_STEPS, REMOVE_MARKS, [["uninstall"]],
                      "%s is out of your game, and your save is ready for the normal game." % mod["title"])

    @Slot(str, result=str)
    def deleteMod(self, mod_id):
        """Move a mod's folder to the Recycle Bin. Only a mod that is not in the game: uninstall comes first."""
        mod = self._mod(mod_id)
        if self._busy or not mod or mod["locked"]: return ""
        if mod["installed"]: return "Uninstall %s first, then its files can go." % mod["title"]
        if self.demo: return "Preview: nothing is deleted."
        moved = QFile.moveToTrash(mod["folder"])
        if not (moved[0] if isinstance(moved, tuple) else moved):
            return "%s could not be moved to the Recycle Bin." % mod["title"]
        self._write_enabled([i for i in self._enabled() if i != mod_id])
        self.refresh()
        return "%s is in the Recycle Bin." % mod["title"]

    @Slot()
    def runSetup(self):
        self._run("READING THE GAME'S DATA", SETUP_STEPS, SETUP_MARKS, [["setup"]], "The game's data is read.")

    @Slot()
    def backupSave(self):
        self._run("BACKING UP YOUR SAVE", BACKUP_STEPS, BACKUP_MARKS, [["backup-save"]],
                  "Save check completed. Open Backups to view any backups created.", after="backups")

    @Slot()
    def repairSave(self):
        self._run("REPAIRING YOUR SAVE", REPAIR_STEPS, REPAIR_MARKS, [["repair-save"]],
                  "Your save is ready for the normal game. If Steam asks about a cloud save conflict, choose the local save.")

    @Slot()
    def makeReport(self):
        self._run("MAKING A REPORT", REPORT_STEPS, REPORT_MARKS, [["feedback"]],
                  "The report is a zip in the Terminal's feedback folder. Send it with your notes.", after="feedback")

    @Slot()
    def dismiss(self):
        if self._running: return
        self._busy = False
        self.busyChanged.emit()

    @Property(bool, constant=True)
    def preview(self):
        """the loader in use is a test copy with a stand-in profile folder: nothing real is installed or started"""
        return bool(self.profile_root) or self.demo

    @Slot()
    def play(self):
        # This engineering fork builds into a physical workbench copy. Steam's
        # app URL would launch a different installation and a different save.
        if os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "WORKBENCH_FORK.json")):
            self.said.emit("Workbench: runtime launch requires an explicitly bound test session; Steam launch is disabled here.")
            return
        if self.demo or self.profile_root:                   # a test never starts the real game
            self.said.emit("Preview: this installs into a test copy, so the game is not started from here.")
            return
        QDesktopServices.openUrl(QUrl("steam://rungameid/" + APPID))

    def _open(self, *parts):
        path = self._p(*parts)
        if self.demo: self.said.emit("Preview: folders are not opened from a recording."); return
        if not os.path.exists(path): self.said.emit("That folder does not exist yet."); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot()
    def openModsFolder(self): self._open("mods")

    @Slot()
    def openGameFolder(self): self._open(os.path.relpath(self._work("game"), self.launcher))

    @Slot()
    def openBackups(self): self._open(os.path.relpath(self._backup_directory(), self.launcher))

    @Slot()
    def openFeedback(self): self._open("feedback")

    @Slot()
    def openLog(self):
        path = self._data("last_run.log")
        if self.demo or not os.path.isfile(path): self.said.emit("There is no log yet."); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot()
    def openNotices(self):
        path = os.path.join(os.path.dirname(HERE), "NOTICES.md")
        if self.demo or not os.path.isfile(path): return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ---- the list of mods ------------------------------------------------------------------------------------
    @Slot(str, bool)
    def setEnabled(self, mod_id, on):
        self._write_enabled([i for i in self._enabled() if i != mod_id] + ([mod_id] if on else []))
        self.refresh()

    @Slot(str, result=str)
    def addMod(self, url):
        """A mod's folder, or a zip of one, chosen or dropped on the window -> copied into mods and switched on.
        The folder holds mod.json, or terminal.json when the mod is made on this PC before it is installed.
        Answers what happened, in words for the person (nothing when the progress panel has taken over)."""
        src = QUrl(url).toLocalFile() if url.startswith("file:") else url
        if self._busy: return "Wait for the current job to finish first."
        try:
            if os.path.isdir(src):
                root = self._find_mod_root(src)
                if not root: return "That folder has no mod in it."
                meta = _read_json(os.path.join(root, "terminal.json"), None) or _read_json(os.path.join(root, "mod.json"), {})
                return self._add(str(meta.get("id") or ""), str(meta.get("name") or meta.get("id") or ""), folder=root)
            if zipfile.is_zipfile(src):
                with zipfile.ZipFile(src) as z:
                    names = z.namelist()
                    hits = [n for n in names if n.rsplit("/", 1)[-1] in ("mod.json", "terminal.json") and n.count("/") <= 2]
                    roots = sorted({n[:len(n) - len(n.rsplit("/", 1)[-1])] for n in hits})
                    if len(roots) != 1: return "That zip does not hold exactly one mod."
                    card = roots[0] + ("terminal.json" if roots[0] + "terminal.json" in names else "mod.json")
                    meta = json.loads(z.read(card).decode("utf-8"))
                return self._add(str(meta.get("id") or ""), str(meta.get("name") or meta.get("id") or ""), zip_path=src, prefix=roots[0])
            return "Choose a mod's zip, or drop its folder here."
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            return "That mod could not be added (%s)." % error

    def _add(self, mod_id, name, folder="", zip_path="", prefix=""):
        """copy a mod into mods\\<id> on a thread of its own, behind the progress panel"""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,60}", mod_id): return "That mod does not say which mod it is."
        title = str(self._known.get(mod_id, {}).get("title") or re.sub(r"\s*\([^()]*\)\s*$", "", name) or mod_id)
        have = self._mod(mod_id)
        if have and have["locked"]: return "%s is one of the Terminal's own files." % title
        if have and have["installed"]: return "%s is in your game. Uninstall it first, then add the new copy." % title
        if self.demo: return "Preview: nothing is added."
        dest = self._p("mods", mod_id)
        self._begin("ADDING " + title.upper(), ADD_STEPS, [],
                    "%s is in your Library and switched on. Press Install to put it in your game." % title)

        def work():
            try:
                if os.path.exists(dest):                     # an older copy: to the Recycle Bin, never merged into
                    moved = QFile.moveToTrash(dest)
                    if not (moved[0] if isinstance(moved, tuple) else moved): shutil.rmtree(dest)
                count = 0
                if folder:
                    shutil.copytree(folder, dest, ignore=shutil.ignore_patterns("__pycache__"))
                    count = sum(len(files) for _, _, files in os.walk(dest))
                else:
                    with zipfile.ZipFile(zip_path) as z:
                        for info in z.infolist():
                            if info.is_dir() or not info.filename.startswith(prefix): continue
                            rel = os.path.normpath(info.filename[len(prefix):])
                            if rel.startswith("..") or os.path.isabs(rel) or ":" in rel: raise ValueError("a file path that is not allowed")
                            out = os.path.join(dest, rel)
                            os.makedirs(os.path.dirname(out), exist_ok=True)
                            with z.open(info) as fin, open(out, "wb") as fout: shutil.copyfileobj(fin, fout, 1 << 20)
                            count += 1
                self._packed.emit(True, "%s|%d" % (mod_id, count))
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                shutil.rmtree(dest, ignore_errors=True)      # never half a mod
                self._packed.emit(False, "That mod could not be added (%s)." % error)

        threading.Thread(target=work, daemon=True).start()
        return ""

    @Slot(bool, str)
    def _pack_done(self, ok, text):
        if ok:
            mod_id, count = text.split("|")
            self._line("%s files copied into mods\\%s" % (count, mod_id))
            self._write_enabled([i for i in self._enabled() if i != mod_id] + [mod_id])
            self._finish(True, self._done_text)
        else:
            self._finish(False, text)

    @staticmethod
    def _find_mod_root(folder):
        is_mod = lambda d: os.path.isfile(os.path.join(d, "mod.json")) or os.path.isfile(os.path.join(d, "terminal.json"))
        if is_mod(folder): return folder
        inner = [os.path.join(folder, n) for n in os.listdir(folder) if is_mod(os.path.join(folder, n))]
        return inner[0] if len(inner) == 1 else ""

    # ---- driving the screens by hand (a recording of the install screen without running an install) ----------
    @Slot(str)
    def demoBegin(self, title):
        self._begin(title, INSTALL_STEPS, INSTALL_MARKS, PLAY_TEXT, "play")

    @Slot(int, str)
    def demoStep(self, step, line):
        self._step = step
        if line: self._log.append(line)
        self.busyChanged.emit(); self.logChanged.emit()

    @Slot()
    def demoFinish(self):
        self._running, self._result, self._step = False, "ok", len(self._steps)
        self._result_text = self._done_text
        self._state = "installed"
        self._installed = {mod["id"] for mod in self._mods if mod["enabled"]}
        for mod in self._mods: mod["installed"] = mod["id"] in self._installed
        self.changed.emit(); self.busyChanged.emit()
