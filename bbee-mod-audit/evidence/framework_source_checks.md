# 非角色框架核对：原始源码片段

读取方式：仅从 ZIP 解压文本到内存，未导入或执行 ZIP 内模块。下面行号为原文件行号。

## ZenithTerminal/Launcher/make_patch.py

SHA-256: `01889193e0d9ffefc6334aac737141ec3c967ec9e2ddc35f9e35e4db2a104d94`

```text
189: def verify_table(name, raw):
190: 
191:     n = 0; i = 0
192:     while i + 4 <= len(raw):
193:         ln = struct.unpack_from("<I", raw, i)[0]; i += 4 + ln; n += 1
194:     print(f"  {name}: {n} rows, {len(raw)} bytes")
```

```text
271: MERGE = os.path.join(AB, "merge.json"); MERGE_BAK = MERGE + ".orig"; MODFILE = "m_mod.m"
272: def install_steam():
273:     require_usable_backup(MERGE_BAK, "install")
274:     if not os.path.exists(MERGE_BAK): make_backup(MERGE, MERGE_BAK)
275:     entries = json.load(open(MERGE_BAK, encoding="utf-8"))
276:     idx = {e["r"]: e for e in entries}
277:     blob = bytearray(); n = 0
278:     for dp, dn, fn in os.walk(OUT):
279:         for f in fn:
280:             if f.startswith("_"): continue
281:             p = os.path.join(dp, f); logical = os.path.relpath(p, OUT).replace("\\", "/")
282:             if logical not in idx:
283:                 e = {"r": logical, "m": MODFILE, "s": 0}; entries.append(e); idx[logical] = e; print("NEW bundle entry:", logical)
284:             data = open(p, "rb").read()
285:             e = idx[logical]; e["m"] = MODFILE; e["s"] = type(e["s"])(len(blob)) if not isinstance(e["s"], str) else str(len(blob))
286:             blob += data; n += 1; print(f"  {logical} -> {MODFILE}@{len(blob)-len(data)} ({len(data)} bytes)")
287: 
288: 
289:     tmp_m, tmp_j = os.path.join(AB, MODFILE + ".new"), MERGE + ".new"
290:     with open(tmp_m, "wb") as f: f.write(blob)
291:     with open(tmp_j, "w", encoding="utf-8") as f: json.dump(entries, f, separators=(",", ":"), ensure_ascii=False)
292:     os.replace(tmp_m, os.path.join(AB, MODFILE)); os.replace(tmp_j, MERGE)
293:     print(f"installed {n} bundles into {os.path.join(AB, MODFILE)}; merge.json updated (backup: merge.json.orig)")
294: def uninstall_steam():
295:     require_usable_backup(MERGE_BAK, "uninstall")
296:     if os.path.exists(MERGE_BAK): shutil.copy2(MERGE_BAK, MERGE); print("merge.json restored")
297:     p = os.path.join(AB, MODFILE)
298:     if os.path.exists(p): os.remove(p); print("removed", p)
```

## ZenithTerminal/Launcher/pipeline.py

SHA-256: `a91e417d0bc15050ab85766991b09df3d12b83f8ccaae94ff8ba37caad4d16ce`

```text
39: count = 0
40: for e in merge:
41:     if not e["r"].startswith("data/"): continue
42:     try: env = UnityPy.load(slice_bundle(e))
43:     except Exception: continue
44:     for obj in env.objects:
45:         if obj.type.name != "TextAsset": continue
46:         d = obj.read(); s = d.m_Script
47:         raw = s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s)
48:         rel = e["r"][:-3] if e["r"].endswith(".ab") else e["r"]
49:         outdir = os.path.join(RAW, *rel.split("/")[:-1]); os.makedirs(outdir, exist_ok=True)
50:         open(os.path.join(outdir, d.m_Name + ".bin"), "wb").write(raw); count += 1
51: print("raw text assets:", count)
```

```text
58: js_ok = js_bad = 0; keys = {}
59: for dp, dn, fn in os.walk(RAW):
60:     for f in fn:
61:         p = os.path.join(dp, f); b = open(p, "rb").read()
62:         rel = os.path.relpath(p, RAW); base = os.path.join(DEC, rel[:-4]); os.makedirs(os.path.dirname(base), exist_ok=True)
63:         if b[:4] != b"NOAH":
64:             ext = ".json" if b[:1] in b"{[" else ".bin"
65:             open(base + ext, "wb").write(b); continue
66:         key = int.from_bytes(bytes(b[4+i] ^ b'"use'[i] for i in range(4)), "little")
67:         dec = noah_xor(b[4:], key)
68:         if dec[:12] == b'"use strict"':
69:             open(base + ".js", "wb").write(dec); keys[rel.replace("\\", "/")[:-4]] = key; js_ok += 1
70:         else:
71:             open(base + ".noah", "wb").write(b); js_bad += 1
72: json.dump({k: f"0x{v:08x}" for k, v in keys.items()}, open(os.path.join(INS, "js_keys.json"), "w"), indent=1)
73: print(f"JS decoded: {js_ok}, unresolved: {js_bad}  (keys saved to inspect\\js_keys.json)")
```

```text
176:         else: raise ValueError(f"wire {wt}")
177:         if kind.startswith("rep_"): out.setdefault(fname, []).append(val)
178:         else: out[fname] = val
179:     return out
180: 
181: TB = os.path.join(DEC, "data", "xlsx"); ok = bad = 0
182: for f in sorted(os.listdir(TB)):
183:     if not f.endswith(".bin"): continue
184:     name = f[:-4]; cls = name if name in schema else None
185:     b = open(os.path.join(TB, f), "rb").read(); rows = []; i = 0
186:     try:
187:         while i + 4 <= len(b):
188:             ln = struct.unpack_from("<I", b, i)[0]; i += 4; rows.append(dmsg(b[i:i+ln], cls or "?")); i += ln
189:         ok += 1
190:     except Exception as ex: bad += 1
191:     json.dump(rows, open(os.path.join(TOUT, name + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
192: print(f"tables decoded: {ok}, failed: {bad}")
193: 
```

## ZenithTerminal/Launcher/entry_point.py

SHA-256: `046e8ae4eb92ef7eea64a5fc6bf335fc61848d4ea951d0639a34288fd59ef1a6`

```text
97: def setup(args):
98:     say("== The Zenith Terminal: setup ==")
99:     if sys.version_info < (3, 10): fail("Python 3.10 or newer is needed (you have %s)." % sys.version.split()[0])
100:     say("Python %s  ok" % sys.version.split()[0])
101:     missing = []
102:     for mod, pkg in PKGS:
103:         try: __import__(mod)
104:         except ImportError: missing.append(pkg)
105:     if missing:
106:         say("Installing Python packages: " + ", ".join(missing))
107:         r = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade"] + missing)
108:         if r.returncode != 0: fail("pip could not install %s. Try: py -m pip install %s" % (" ".join(missing), " ".join(missing)))
109:     say("Python packages  ok")
110:     if shutil.which("node") is None:
111:         say("Node.js not found  (optional: only used to double-check scripts; you can skip it)")
```

```text
129:     need_closed()
130:     say(""); say("Reading the game data (takes a few minutes, only needed once and after each game update)...")
131:     r = subprocess.run([sys.executable, os.path.join(ROOT, "pipeline.py")], cwd=ROOT)
132:     if r.returncode != 0: fail("Reading the game data failed (see the messages above).")
133:     if installed_build():
134:         open(BUILD_MARK, "w", encoding="utf-8").write(installed_build())
135:     say(""); say("Setup done. Next: close the game (if open) and run 2_INSTALL.bat  (or: python entry_point.py install)")
```

```text
170: SAVE_ROOT = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\91Act\BlazblueEntropyEffect")
171: 
172: 
173: def backup_save(tag):
174:     """copy the whole save area (every account, its Save, Backup and ColdBackup) into save_backups/<time>_<tag>"""
175:     import shutil
176:     if not os.path.isdir(SAVE_ROOT): say("No save folder found yet (%s); nothing to back up." % SAVE_ROOT); return None
177:     dst = os.path.join(ROOT, "save_backups", time.strftime("%Y%m%d_%H%M%S") + "_" + tag)
178:     for sub in ("Steam", "XBoxPc", "Global"):
179:         src = os.path.join(SAVE_ROOT, sub)
180:         if os.path.isdir(src): shutil.copytree(src, os.path.join(dst, sub))
181:     say("Save backed up to: " + dst)
182:     return dst
183: 
184: 
185: def save_files():
186:     """the files the game loads your progress from: <account>/Save/<slot> and Save/Backup/<slot>"""
187:     out = []
188:     for acc in glob.glob(os.path.join(SAVE_ROOT, "Steam", "*", "Save")) + glob.glob(os.path.join(SAVE_ROOT, "XBoxPc", "*", "Save")):
189:         for f in glob.glob(os.path.join(acc, "*")) + glob.glob(os.path.join(acc, "Backup", "*")):
190:             if os.path.isfile(f) and os.path.basename(f).isdigit(): out.append(f)
```

```text
270: def install(args):
271:     if not os.path.exists(os.path.join(GAME, EXE)): fail("Setup hasn't been run yet (no game folder link). Run 1_SETUP.bat first.")
272:     if not os.path.isdir(os.path.join(ROOT, "decoded", "tables")): fail("The game data hasn't been read yet. Run 1_SETUP.bat first.")
273:     need_closed()
274:     now = installed_build(); read = open(BUILD_MARK, encoding="utf-8").read().strip() if os.path.exists(BUILD_MARK) else None
275:     if now and read != now:
276:         fail("The game data in this folder was read from %s, and the game is now build %s.\n"
277:              "Run 1_SETUP.bat again, then 2_INSTALL.bat." % ("game build " + read if read else "an earlier setup", now))
278:     retire_stale_backups()
279:     backup_save("before_install")
280:     drop_missing_characters()
281:     cf = find_bbcf()
282:     if cf:
283:         os.environ["BBCF_DIR"] = cf
284:         say("BlazBlue Centralfiction found: " + cf + "  (used for her Centralfiction animations if this Steam account owns it)")
285:     else:
286:         say("BlazBlue Centralfiction not found: her moves use her Entropy Effect animations (nothing is missing).")
287:     say("== building and installing (1-5 minutes) ==")
288:     t0 = time.time(); done = os.path.join(ROOT, "mods", "installed.json")
289:     if bbmod("install") != 0: fail("The install stopped with an error (see above).")
290:     if not os.path.exists(done) or os.path.getmtime(done) < t0 - 2:
291:         fail("The install did not finish (see the messages above; a line starting with REFUSING or BUILD ABORTED says why).")
292:     say(""); say("Installed. Start the game normally from Steam. Yhe new characters are at the end of the Prototype list.")
293: 
294: 
295: def uninstall(args):
296:     """SAFE uninstall. The normal game can't load a save that still has Modded Characters in it (their Evotypes, records,
297:     a run with them), so the save is backed up and cleaned FIRST, then the mods are removed."""
298:     need_closed()
299:     say("== safe uninstall ==")
300:     say("The Evotypes and records will be removed from your save (the normal game can't load them).")
301:     say("Everything else stays. A full copy of your save goes to the save_backups folder first.")
302:     repair_save(args)
303:     if os.path.exists(os.path.join(GAME, EXE)): retire_stale_backups()
304:     if bbmod("uninstall") != 0: fail("Removing the mod stopped with an error (see above). Your save was already repaired.")
305:     say(""); say("All mods removed and your save is ready for the normal game.")
306:     say("If anything still looks modded, use Steam > Verify integrity of game files.")
307: 
```

## ZenithTerminal/Launcher/bbmod.py

SHA-256: `89cde5d98d5cbb69b058b2125f767583c66d18c7a421cf612976d8dffe49eb77`

```text
227: 
228: 
229: 
230: 
231: _gen = None
232: class _CachedTypeTrees:
233:     """UnityPy typetree generator with a per-game-build cache (tools/typetrees/<build>/). With dump/DummyDll present
234:     (Il2CppDumper output) nodes are generated and the cache refreshed; without it -- an end user's machine -- the cached
235:     nodes are used, so installing never needs Il2CppDumper. Type layouts are metadata, not game content."""
236:     def __init__(self):
237:         self.real = False; self.dir = os.path.join(ROOT, "tools", "typetrees", str(game_build()))
238:     def _real(self):
239:         if self.real is False:
240:             dll = os.path.join(ROOT, "dump", "DummyDll"); self.real = None
241:             if os.path.isdir(dll):
242:                 from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
243:                 self.real = TypeTreeGenerator("2022.3.62f3"); self.real.load_local_dll_folder(dll)
244:         return self.real
245:     def get_nodes_up(self, assembly, fullname):
246:         f = os.path.join(self.dir, "%s__%s.json" % (assembly.replace(".dll", ""), fullname))
247:         g = self._real()
248:         if g is not None:
249:             node = g.get_nodes_up(assembly, fullname)
250:             os.makedirs(self.dir, exist_ok=True); json.dump(node.to_dict_list(), open(f, "w", encoding="utf-8"))
251:             return node
252:         if os.path.exists(f):
253:             from UnityPy.helpers.TypeTreeNode import TypeTreeNode
254:             return TypeTreeNode.from_list(json.load(open(f, encoding="utf-8")))
255:         raise SystemExit("no dump/DummyDll and no cached type tree for %s (build %s). See docs/boons-plus/README.md." % (fullname, game_build()))
256: def typetree_gen():
257:     global _gen
258:     if _gen is None: _gen = _CachedTypeTrees()
259:     return _gen
```

```text
483: def install():
484:     if STAGING: print("refusing: BBMOD_PROFILE/BBMOD_OUT set (staging build); unset them to install"); return
485:     blocked = gameslot_block()
486:     if blocked: print("REFUSING to install: " + blocked); return
487:     if game_running(): print("REFUSING to install: the game is running. Close it completely, then run install again."); return
488:     if not build(): return
489:     if game_running():
490:         print("REFUSING to install: the game was started during the build. Nothing in the game folder was changed. "
491:               "Close the game completely, then run install again."); return
492:     if os.path.exists(os.path.join(OUT, "_build.json")): os.remove(os.path.join(OUT, "_build.json"))
493:     _mp["install_steam"]()
494:     madd = os.path.join(OUT, "_manifest_add.json")
495:     import bbchar
496:     if os.path.exists(madd): bbchar.apply_manifest_additions(json.load(open(madd)))
497:     else: bbchar.restore_manifest()
498:     prof = load_profile(); json.dump({"gameBuild": game_build(), "enabled": prof["enabled"], "installed": time.strftime("%Y-%m-%d %H:%M:%S")}, open(INSTALLED, "w"), indent=1)
499:     print("installed; run the game and check", os.path.join(ROOT, "modlog.txt"))
500: def uninstall():
501:     if STAGING: print("refusing: BBMOD_PROFILE/BBMOD_OUT set (staging build)"); return
502:     blocked = gameslot_block()
503:     if blocked: print("REFUSING to uninstall: " + blocked); return
504:     _mp["uninstall_steam"]()
505:     import bbchar; bbchar.restore_manifest()
506:     if os.path.exists(INSTALLED): os.remove(INSTALLED)
```

## ZenithTerminal/Launcher/bbchar.py

SHA-256: `b3ecf8a995ddc4b6d886fa2fb485d0688e4d14a3156a8906c0573882c946a6bc`

```text
18: def read_manifest():
19:     global _MAN
20:     if _MAN is None: _MAN = _read_manifest()
21:     return [list(_MAN[0]), [[i, list(d)] for i, d in _MAN[1]], [[i, list(g)] for i, g in _MAN[2]]]
22: def _read_manifest():
23:     use_bak = bbmod._mp["backup_state"](MANIFEST_BAK)
24:     if use_bak is False: bbmod._mp["pristine_merge_path"]()
25:     raw = lz4.frame.decompress(open(MANIFEST_BAK if use_bak else MANIFEST, "rb").read()).decode("utf-8")
26:     L = raw.split("\r\n"); assert L[0] == "FastManifest V3"
27:     n1 = int(L[1][2:]); names = L[2:2 + n1]; i = 2 + n1; n2 = int(L[i][2:]); i += 1; entries = []
28:     while i < len(L) and not L[i].startswith("N:"):
29:         if L[i].startswith(" "): entries[-1][1].append(L[i].strip())
30:         else: entries.append([L[i], []])
31:         i += 1
32:     n3 = int(L[i][2:]); i += 1; guids = []
33:     while i < len(L) and L[i] != "----":
34:         if L[i].startswith(" "): guids[-1][1].append(L[i].strip())
35:         else: guids.append([L[i], []])
36:         i += 1
37:     return names, entries, guids
38: def write_manifest(names, entries, guids):
39:     global _MAN; _MAN = None
40:     bbmod._mp["require_usable_backup"](MANIFEST_BAK, "write the manifest")
41:     if not os.path.exists(MANIFEST_BAK): bbmod._mp["make_backup"](MANIFEST, MANIFEST_BAK)
42:     out = ["FastManifest V3", f"N:{len(names)}"] + names + [f"N:{len(entries)}"]
43:     for idx, deps in entries: out += [idx] + [" " + d for d in deps]
44:     out += [f"N:{len(guids)}"]
45:     for idx, gs in guids: out += [idx] + [" " + g for g in gs]
46:     out += ["----", ""]
47:     open(MANIFEST, "wb").write(lz4.frame.compress("\r\n".join(out).encode("utf-8")))
48: def restore_manifest():
49:     global _MAN; _MAN = None
50:     bbmod._mp["require_usable_backup"](MANIFEST_BAK, "restore the manifest")
51:     if os.path.exists(MANIFEST_BAK): import shutil; shutil.copy2(MANIFEST_BAK, MANIFEST)
```
