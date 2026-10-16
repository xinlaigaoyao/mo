# Zenith Terminal 0.3.0-alpha：源码证据摘录


日期：2026-10-15。全部摘录来自用户上传的压缩包，不是外部仓库的其他版本。行号按 UTF-8 文本逐行计数；下面的 SHA-256 对原文件字节计算。

压缩包 SHA-256：`b5b3c2548ab61259c6f757b0cbf450a1d3490345ae9172915a5d7a303c36e150`。

这些摘录用于解释源代码行为；不证明作者身份、发布包真实性、完整安全性或游戏内成功。


## E01｜包身份、版本与初次生成说明


来源：`PACKAGE_MANIFEST.txt`，第 1–20 行。

SHA-256：`86d7160d19858bcfb07c11d897d060638b59a3b5813a5f93c3fdc6b3555811b0`


```text

1: The Zenith Terminal 0.3.0 alpha
2: packaged 2026-10-10 18:34
3: 
4: The loader (Launcher\): KittySkin's, commit f6770a6 of 2026-10-09 16:13:36 -0500, as it is in his repository at that commit.
5: Added beside the loader's files, none of them replaced:
6:   Launcher\mods\dr-party: DELTARUNE: Party 0.6.4, from DeltaruneParty-0.6.4-alpha.zip
7:     (sha256 ab08a50f2e6f2fefaa109884ff0e4fd9b3364575ac9746a28ff52a488abd16c3), switched on in Launcher\mods\profile.json.
8:   Launcher\tools\cri_acb.py: from the same package; the party's sound importer loads it.
9:   Launcher\local_only\deltarune\audio\hca_cache: the party's 24 sounds, encoded (VGAudio), so that
10:     installing it needs no .NET SDK.
11:   Launcher\mods\char-ruby: Ruby Rose 0.9.0, from RubyRose-0.9.0-terminal.zip
12:     (sha256 3b19bc0d88c5e4ca3157cad2932852d08a2e713d43c55aa3a2411212ded50803), switched on. She has no mod.json yet:
13:     the first install makes her on the player's PC (terminal.json, prepare).
14: Mods that come switched on: Nine 0.9.0 (char-nine, from the loader's repository), DELTARUNE: Party 0.6.4,
15:   Ruby Rose 0.9.0.
16: The window (Gui\): 0.3.0.
17: package\: ID.txt, KEEP.txt and FILES.txt, read by the one-file release when it unpacks or updates.
18: Python (Interpreter\): 3.14.8, the python.org runtime (https://www.python.org/ftp/python/3.14.8/python-3.14.8-amd64.zip), without its manual, C headers and tests.
19: Python packages, as published on PyPI:
20:   archspec 0.2.6

```


## E02｜Ruby 的 terminal prepare 描述


来源：`Launcher/mods/char-ruby/terminal.json`，第 1–20 行。

SHA-256：`3259fd91209050aaf2294af60bf624bb17233a79f4457fbecf67b64589721363`


```text

1: {
2:  "id": "char-ruby",
3:  "name": "Ruby Rose (Cross Effect, alpha)",
4:  "version": "0.9.0",
5:  "description": "Ruby Rose as a playable character: Crescent Rose's scythe strings and Gun Blast, her rifle, her own voice, effects and Potentials. Her moves, art and sounds are made on your PC the first time you install her (a few minutes). Unofficial fan work: not made or endorsed by 91Act, Arc System Works or RWBY's owners.",
6:  "dependencies": [
7:   "bbee-sdk",
8:   "bbee-actors"
9:  ],
10:  "prepare": [
11:   "mods/char-ruby/build_ruby.py",
12:   "mods/char-ruby/terminal_art.py"
13:  ],
14:  "gameBuilds": [
15:   "25478197",
16:   "25598842",
17:   "25621352",
18:   "25627491"
19:  ]
20: }

```


## E03｜GUI 的 setup → prepare → install 顺序及变更检查


来源：`Gui/zenith_gui/controller.py`，第 497–522 行。

SHA-256：`f7b47930211abe475abf552a5e456260c33ad7e57ad379c53209f19657b998d5`


```text

497:     def _install_job(self, title, done, after="play", steps=REBUILD_STEPS, marks=REBUILD_MARKS):
498:         """build and install what is switched on; the game's data is read first when that has not been done for
499:         this build of the game"""
500:         first = self._state in ("no-game", "setup")
501:         steps, marks = (INSTALL_STEPS, INSTALL_MARKS) if first else (steps, marks)
502:         prepare = [["@prepare", mod["title"], script] for mod in self._wanted() if self._needs_prepare(mod, first)
503:                    for script in mod["prepare"]]
504:         if prepare:                               # its own step, after the game's data is read and before the save
505:             at = 2 if first else 0
506:             steps = list(steps[:at]) + [PREPARE_STEP] + list(steps[at:])
507:             marks = [(mark, step + 1 if step >= at else step) for mark, step in marks]
508:             self._prep_step = at
509:         self._run(title, steps, marks, ([["setup"]] if first else []) + prepare + [["install"]], done, after)
510: 
511:     def _needs_prepare(self, mod, first):
512:         """a mod with `prepare` scripts is made again when it was never made, when the game's data is about to be
513:         read again, or when one of its own files or that data is newer than what was made"""
514:         if not mod.get("prepare"): return False
515:         made = os.path.join(mod["folder"], "mod.json")
516:         if first or not os.path.isfile(made): return True
517:         stamp = os.path.getmtime(made)
518:         newer = [self._work("inspect", "game_build.txt")]
519:         for name in os.listdir(mod["folder"]):
520:             if name.endswith((".py", ".json")) and name != "mod.json": newer.append(os.path.join(mod["folder"], name))
521:         return any(os.path.isfile(p) and os.path.getmtime(p) > stamp for p in newer)
522: 

```


## E04｜逻辑包切片和原始基线读取


来源：`Launcher/pipeline.py`，第 11–36 行。

SHA-256：`a91e417d0bc15050ab85766991b09df3d12b83f8ccaae94ff8ba37caad4d16ce`


```text

11: 
12: man = lz4.frame.decompress(open(os.path.join(AB, "manifest"), "rb").read())
13: open(os.path.join(INS, "manifest_decoded.txt"), "wb").write(man)
14: 
15: 
16: _mlive = os.path.join(AB, "merge.json"); _morig = _mlive + ".orig"
17: _msrc = _mlive
18: if '"m_mod.m"' in open(_mlive, encoding="utf-8").read():
19:     _stamp = open(_morig + ".build").read().strip() if os.path.exists(_morig + ".build") else None
20:     _acf = os.path.realpath(os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(GAME))), "appmanifest_2273430.acf"))
21:     _now = re.search(r'"buildid"\s+"(\d+)"', open(_acf, encoding="utf-8", errors="replace").read()).group(1) if os.path.exists(_acf) else None
22:     if os.path.exists(_morig) and _stamp and _stamp == _now:
23:         _msrc = _morig; print("mods are installed: decoding the pristine backup merge.json.orig (build %s)" % _stamp)
24:     else:
25:         sys.exit("merge.json is modded and there is no pristine backup for this game build. Run `python bbmod.py uninstall` "
26:                  "(or Steam 'Verify integrity'), then pipeline.py again. See docs/BUILD_UPDATE.md.")
27: merge = json.load(open(_msrc, encoding="utf-8"))
28: open(os.path.join(INS, "logical_bundles.txt"), "w", encoding="utf-8").write("\n".join(sorted(e["r"] for e in merge)))
29: by_file = collections.defaultdict(list)
30: for e in merge: by_file[e["m"]].append(e)
31: for m in by_file: by_file[m].sort(key=lambda e: e["s"])
32: def slice_bundle(entry):
33:     lst = by_file[entry["m"]]; i = lst.index(entry)
34:     p = os.path.join(AB, entry["m"]); end = lst[i+1]["s"] if i+1 < len(lst) else os.path.getsize(p)
35:     with open(p, "rb") as f: f.seek(entry["s"]); return f.read(end - entry["s"])
36: print("logical bundles:", len(merge))

```


## E05｜表格匹配键及组合规则


来源：`Launcher/bbmod.py`，第 108–171 行。

SHA-256：`89cde5d98d5cbb69b058b2125f767583c66d18c7a421cf612976d8dffe49eb77`


```text

108: 
109: KEY_OVERRIDES = {"BlessScreenGridConf": ["BlessId"], "SkillActivate": ["ActorId", "Group", "Order"], "BaseActorAttrConf": ["ActorId"],
110:                  "PvpBaseActorAttrConf": ["ActorId"], "SkillDamage": ["ActorId", "HitTimes"], "SkillAttr": ["ActorId", "Order"], "FesActorAttrInheritConf": ["ActorId"],
111:                  "SkillSlotBanActions": ["ActorId", "SkillSlot"], "HeroPortraitOffsetConfigUI": ["Id"],
112:                  "SkillFromTeacher": ["TeacherSkillId"]}
113: def table_keys(name, rows):
114:     if name in KEY_OVERRIDES: return list(KEY_OVERRIDES[name])
115:     f = rows[0] if rows else {}
116:     ks = ["Idx"] if "Idx" in f else ["Id"] if "Id" in f else []
117:     for extra in ("Lvl", "Quality"):
118:         if extra in f and ks: ks.append(extra)
119:     return ks
120: def rowkey(r, ks): return tuple(r.get(k, 1 if k == "Lvl" else 0) for k in ks)
121: def depends_on(mods, mid, target, seen=None):
122:     """True if mod `mid` (transitively) declares `target` as a dependency -> it may override target's values."""
123:     seen = seen or set()
124:     for d in mods.get(mid, {}).get("dependencies", []):
125:         if d == target or (d not in seen and (seen.add(d) or depends_on(mods, d, target, seen))): return True
126:     return False
127: def ensure_orig(path):
128:     if not os.path.exists(path + ".orig"): shutil.copy2(path, path + ".orig")
129: def compose_tables(order, mods, report):
130:     touched = {}
131:     for mid in order:
132:         for tname, rows in mods[mid].get("content", {}).get("tables", {}).items():
133:             touched.setdefault(tname, []).append((mid, rows))
134:     for tname, edits in touched.items():
135:         p = os.path.join(TABLES, tname + ".json"); assert os.path.exists(p), f"unknown table {tname}"
136:         ensure_orig(p); base = json.load(open(p + ".orig", encoding="utf-8")); ks = table_keys(tname, base)
137:         index = {rowkey(r, ks): r for r in base if rowkey(r, ks)[:1] not in ((None,), (0,))}; owner = {}
138:         for mid, rows in edits:
139:             for e in rows:
140:                 if "$copyRows" in e:
141:                     spec = e["$copyRows"]; src = [r for r in base if all(r.get(f) == v for f, v in spec["where"].items())]
142:                     for r in src:
143:                         n = json.loads(json.dumps(r)); n.update(spec.get("set", {}))
144:                         for sw in spec.get("setWhere", []):
145:                             if all(n.get(f) == v for f, v in sw["match"].items()): n.update(sw["set"])
146:                         if spec.get("idOffset") and ks and ks[0] in n: n[ks[0]] = n[ks[0]] + spec["idOffset"]
147:                         kk = rowkey(n, ks)
148:                         if ks and kk in index and kk[:1] not in ((None,), (0,)) and not spec.get("allowDuplicateKeys"):
149:                             raise AssertionError(f"{mid}: {tname} $copyRows would duplicate key {kk} (set allowDuplicateKeys for multi-row-per-id tables)")
150:                         base.append(n); index[kk] = n; owner[(kk, "*")] = mid
151:                     print(f"    {mid}: {tname} copied {len(src)} rows where {spec['where']} -> {spec.get('set')}")
152:                     continue
153:                 k = rowkey(e, ks)
154:                 if e.get("$append"):
155:                     r = {kk: v for kk, v in e.items() if not kk.startswith("$")}; base.append(r); owner[(k, "*")] = mid; continue
156:                 if e.get("$new"):
157:                     assert k not in index, f"{mid}: {tname} row {k} already exists"
158:                     r = {kk: v for kk, v in e.items() if not kk.startswith("$")}; base.append(r); index[k] = r; owner[(k, "*")] = mid; continue
159:                 assert k in index, f"{mid}: {tname} row {k} not found (use \"$new\": true to insert)"
160:                 r = index[k]
161:                 if e.get("$delete"): base.remove(r); del index[k]; owner[(k, "*")] = mid; continue
162:                 if e.get("$replace"):
163:                     r.clear(); r.update({kk: v for kk, v in e.items() if not kk.startswith("$")}); owner[(k, "*")] = mid; continue
164:                 for f, v in e.items():
165:                     if f.startswith("$") or f in ks: continue
166:                     prev = owner.get((k, f))
167:                     if prev and prev != mid and r.get(f) != v and not depends_on(mods, mid, prev): report.append(f"CONFLICT table {tname} row {k} field {f}: {prev} vs {mid} (declare {prev} as a dependency to override it)")
168:                     r[f] = v; owner[(k, f)] = mid
169:         json.dump(base, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
170:         print(f"  table {tname}: {sum(len(r) for _, r in edits)} row edits from {[m for m, _ in edits]}")
171:     return list(touched)

```


## E06｜JS 组合与语法检查


来源：`Launcher/bbmod.py`，第 176–224 行。

SHA-256：`89cde5d98d5cbb69b058b2125f767583c66d18c7a421cf612976d8dffe49eb77`


```text

176: def registry_code(order, mods):
177:     aliases = {}
178:     for mid in order:
179:         for k, v in mods[mid].get("content", {}).get("spriteAliases", {}).items(): aliases[k] = v
180:     modlist = [{"id": m, "name": mods[m]["name"], "version": mods[m]["version"]} for m in order]
181:     taliases = {}
182:     for mid in order:
183:         for k, v in mods[mid].get("content", {}).get("textureAliases", {}).items(): taliases[k] = v
184:     return ("/* ===== generated by bbmod: ModRegistry ===== */\n"
185:             "exports.ModRegistry={mods:" + json.dumps(modlist, ensure_ascii=False) + ",spriteAlias:" + json.dumps(aliases, ensure_ascii=False) + ",textureAlias:" + json.dumps(taliases, ensure_ascii=False) +
186:             ",gameBuild:" + json.dumps(game_build()) + ",built:" + json.dumps(time.strftime("%Y-%m-%d %H:%M")) + "};")
187: def compose_js(order, mods, report):
188:     touched = {}
189:     for mid in order:
190:         c = mods[mid].get("content", {})
191:         for spec in c.get("js", []): touched.setdefault(spec["file"], []).append((mid, spec))
192:         for logical, rel in c.get("jsFiles", {}).items(): touched.setdefault(logical, []).append((mid, {"wholeFile": os.path.join(mods[mid]["_dir"], rel)}))
193:     if order: touched.setdefault(REGISTRY_MODULE, []).append(("bbmod", {"append": registry_code(order, mods)}))
194:     for logical, specs in touched.items():
195:         p = js_path(logical); assert os.path.exists(p), f"unknown js module {logical}"
196:         ensure_orig(p); s = open(p + ".orig", encoding="utf-8").read(); anchors = {}
197:         whole = [m for m, sp in specs if "wholeFile" in sp]
198:         if whole:
199:             if len(specs) > 1: report.append(f"CONFLICT js {logical}: whole-file replacement by {whole} plus other edits by {[m for m, _ in specs if m not in whole]}")
200:             s = open(specs[0][1]["wholeFile"], encoding="utf-8").read()
201:         else:
202:             appends = []
203:             for mid, sp in specs:
204:                 for old, new in sp.get("replace", []):
205:                     if old in anchors and anchors[old] != mid: report.append(f"CONFLICT js {logical}: anchor patched by {anchors[old]} and {mid}: {old[:60]!r}")
206:                     n = s.count(old)
207:                     if n == 0: report.append(f"ERROR js {logical} ({mid}): anchor not found: {old[:80]!r}"); continue
208:                     if n > 1: print(f"    WARNING js {logical} ({mid}): anchor matches {n} times and ALL are replaced -- make it unique: {old[:70]!r}")
209:                     s = s.replace(old, new.replace("@ROOT@", ROOT.replace("\\", "/"))); anchors[old] = mid
210:                 if sp.get("append"): appends.append(sp["append"])
211:                 if sp.get("appendFile"): appends.append(open(os.path.join(mods[mid]["_dir"], sp["appendFile"]), encoding="utf-8").read())
212:             if appends:
213: 
214:                 appends = [x.replace("@ROOT@", ROOT.replace("\\", "/")) for x in appends]
215:                 marker = "\n//# sourceMappingURL="; i = s.rfind(marker)
216:                 s = (s[:i] + "\n" + "\n".join(appends) + s[i:]) if i >= 0 else s + "\n" + "\n".join(appends)
217:         open(p, "w", encoding="utf-8", newline="\n").write(s)
218:         if shutil.which(NODE) is None:
219:             print(f"  js {logical}: {len(specs)} edit set(s) from {[m for m, _ in specs]}  (syntax check skipped: Node.js not installed)")
220:             continue
221:         r = subprocess.run([NODE, "--check", p], capture_output=True, text=True)
222:         if r.returncode != 0: report.append(f"ERROR js {logical}: syntax check failed:\n{r.stderr[:400]}")
223:         print(f"  js {logical}: {len(specs)} edit set(s) from {[m for m, _ in specs]}  {'OK' if r.returncode == 0 else 'SYNTAX ERROR'}")
224:     return list(touched)

```


## E07｜资源操作入口


来源：`Launcher/bbmod.py`，第 272–301 行。

SHA-256：`89cde5d98d5cbb69b058b2125f767583c66d18c7a421cf612976d8dffe49eb77`


```text

272: def apply_asset_ops(tree, spec, mid, report):
273:     if spec.get("treeFile"):
274:         p = os.path.join(mdir(mid), spec["treeFile"])
275:         if not os.path.exists(p): report.append(f"ERROR asset {spec['bundle']} ({mid}): treeFile {spec['treeFile']} missing"); return
276:         src = json.load(open(p, encoding="utf-8"))
277:         for k, v in src.items():
278:             if not k.startswith("m_") or k == "m_Name": tree[k] = v
279:     if spec.get("copyTreeFrom"):
280:         import UnityPy
281:         src = spec["copyTreeFrom"]; env = UnityPy.load(slice_bundle(find_entry(src["bundle"]))); env.typetree_generator = typetree_gen(); st = None
282:         for o in env.objects:
283:             if o.type.name == "MonoBehaviour":
284:                 t = o.read_typetree()
285:                 if t.get("m_Name") == src["asset"]: st = t; break
286:         if st is None: report.append(f"ERROR asset {spec['bundle']} ({mid}): copyTreeFrom source {src} not found"); return
287:         for k, v in st.items():
288:             if not k.startswith("m_") or k == "references": tree[k] = json.loads(json.dumps(v))
289:         if "references" in tree: tree["references"]["RefIds"] = [r for r in tree["references"]["RefIds"] if r.get("type", {}).get("class") != ""]
290:     for op in spec.get("set", []):
291:         c, k = resolve_path(tree, op["path"]); c[k] = {"value": int(round(op["fp"] * 4294967296))} if "fp" in op else op["value"]
292:     for cp in spec.get("copyActions", []):
293:         src = next((a for a in tree["_actions"] if a["Name"] == cp["from"]), None)
294:         if src is None: report.append(f"ERROR asset {spec['bundle']} ({mid}): copyActions source '{cp['from']}' not found"); continue
295:         new = json.loads(json.dumps(src)); new["Name"] = cp["name"]
296:         for op in cp.get("set", []):
297:             c, k = resolve_path(new, op["path"]); c[k] = {"value": int(round(op["fp"] * 4294967296))} if "fp" in op else op["value"]
298:         tree["_actions"] = [a for a in tree["_actions"] if a["Name"] != cp["name"]] + [new]
299:     for a in spec.get("addActions", []): tree["_actions"] = [x for x in tree["_actions"] if x["Name"] != a["Name"]] + [a]
300:     for im in spec.get("importActions", []):
301:         import UnityPy

```


## E08｜完整构建顺序


来源：`Launcher/bbmod.py`，第 401–461 行。

SHA-256：`89cde5d98d5cbb69b058b2125f767583c66d18c7a421cf612976d8dffe49eb77`


```text

401: def build():
402:     mods = load_mods(); prof = load_profile(); order = resolve_order(mods, prof["enabled"]); build_id = game_build()
403:     print(f"game build {build_id}; load order: {order}")
404:     for mid in order:
405:         gb = mods[mid].get("gameBuilds", ["*"])
406:         if "*" not in gb and build_id not in gb: print(f"  WARNING {mid} verified on builds {gb}, game is {build_id}")
407:     report = []
408:     if os.path.exists(OUT): shutil.rmtree(OUT)
409:     os.makedirs(OUT)
410:     print("tables:"); tnames = compose_tables(order, mods, report)
411:     print("js:"); jsnames = compose_js(order, mods, report)
412:     locale = compose_locale(order, mods, report)
413:     print("rigs:")
414:     rig_specs = [(m, r) for m in order for r in mods[m].get("content", {}).get("rigClones", [])]
415:     rig_specs += [(m, dict(r, _kind="bundle")) for m in order for r in mods[m].get("content", {}).get("bundleClones", [])]
416:     if rig_specs:
417: 
418:         spec_file = os.path.join(tempfile.gettempdir(), "bbmod_rigspecs_%d.json" % os.getpid())
419:         with open(spec_file, "w", encoding="utf-8") as f: json.dump(rig_specs, f)
420:         r = subprocess.run([sys.executable, os.path.abspath(__file__), "_rigs", "@" + spec_file], capture_output=True, text=True)
421:         try: os.remove(spec_file)
422:         except OSError: pass
423:         print(r.stdout.rstrip())
424:         if r.returncode != 0: report.append("ERROR rigs: child process failed (rc %d): %s" % (r.returncode, r.stderr[-800:]))
425: 
426: 
427: 
428:     for mid in order:
429:         for spec in mods[mid].get("content", {}).get("importers", []):
430:             print("importer %s: %s" % (mid, spec["script"]))
431:             addp = os.path.join(tempfile.gettempdir(), "bbmod_import_%s_%d.json" % (mid, os.getpid()))
432:             r = subprocess.run([sys.executable, os.path.join(mdir(mid), spec["script"])] + list(spec.get("args", [])) + ["--out", OUT, "--adds", addp],
433:                                capture_output=True, text=True, env=dict(os.environ, BBMOD_OUT=OUT))
434:             print("\n".join(r.stdout.rstrip().splitlines()[-25:]))
435:             if r.returncode != 0 or not os.path.exists(addp):
436:                 report.append("ERROR importer %s: rc %d: %s" % (mid, r.returncode, (r.stderr or r.stdout)[-800:])); continue
437:             add = json.load(open(addp, encoding="utf-8")); os.remove(addp)
438:             madd = os.path.join(OUT, "_manifest_add.json")
439:             cur = json.load(open(madd)) if os.path.exists(madd) else {"names": [], "entries": [], "guids": []}
440:             for k in ("names", "entries", "guids"): cur[k] += add.get(k, [])
441:             json.dump(cur, open(madd, "w"), indent=1)
442:     print("assets:")
443:     if any(mods[m].get("content", {}).get("assets") for m in order):
444:         r = subprocess.run([sys.executable, os.path.abspath(__file__), "_assets", json.dumps(order)], capture_output=True, text=True)
445:         print(r.stdout.rstrip()); [report.append(l) for l in r.stdout.splitlines() if l.startswith(("CONFLICT", "ERROR"))]
446:         if r.returncode != 0: report.append("ERROR assets: child process failed (rc %d): %s" % (r.returncode, r.stderr[-600:]))
447:     errs = [r for r in report if r.startswith(("CONFLICT", "ERROR"))]
448:     if errs: print("\nBUILD ABORTED:\n  " + "\n  ".join(errs)); return False
449:     print("encoding:")
450:     for name in tnames:
451:         raw = encode_table(name); verify_table(name, raw); rebuild_bundle(f"data/xlsx/{name.lower()}.ab", name, raw)
452:         if name + "FixedPoint" in SCHEMA and os.path.exists(os.path.join(RAW, "data", "xlsxfixed", name + "FixedPointWrap.bin")):
453:             fraw = encode_fixed_table(name, KEY_OVERRIDES.get(name)); verify_table(name + "FixedPointWrap", fraw)
454:             rebuild_bundle(f"data/xlsxfixed/{name.lower()}fixedpointwrap.ab", name + "FixedPointWrap", fraw)
455:     for lp in jsnames:
456:         src = open(js_path(lp), "rb").read(); key = JSKEYS.get(lp)
457:         rebuild_bundle(lp.lower() + ".ab", lp.split("/")[-1], (b"NOAH" + noah_xor(src, int(key, 16))) if key else src)
458:     build_locale(locale)
459:     json.dump({"gameBuild": build_id, "mods": {m: mods[m]["version"] for m in order}, "built": time.strftime("%Y-%m-%d %H:%M:%S")},
460:               open(os.path.join(OUT, "_build.json"), "w"), indent=1)
461:     print("build OK ->", OUT); return True

```


## E09｜m_mod.m / merge.json 安装与恢复


来源：`Launcher/make_patch.py`，第 267–298 行。

SHA-256：`01889193e0d9ffefc6334aac737141ec3c967ec9e2ddc35f9e35e4db2a104d94`


```text

267: 
268: 
269: 
270: 
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


## E10｜存档备份、清理和安全卸载


来源：`Launcher/entry_point.py`，第 270–307 行。

SHA-256：`046e8ae4eb92ef7eea64a5fc6bf335fc61848d4ea951d0639a34288fd59ef1a6`


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


## E11｜Ruby 的身份及动作基底


来源：`Launcher/mods/char-ruby/build_ruby.py`，第 22–49 行。

SHA-256：`f0e544d52e785567d378636c02279f6c7f89f5a3f0d3fe872e45b2e768a955a8`


```text

22: ACTOR, DONOR, DONOR_LOGIC = 200701, 100101, "rg"
23: LOGIC = ROLE = RC.ROLE            # "rrb": logic, animation role, texture family prefix
24: SKIN = RC.SKIN
25: BID, BLOGIC = 20070101, "rrbb1"    # her projectiles (one bullet logic)
26: TEMPLATE_LOGICS = ("rg", "icey", "no", "tk")
27: 
28: # ---------------------------------------------------------------- data from the player's BBTAG install
29: def source():
30:     import bbtag_read as R, bbtag_rig as RG, bbtag_clips as C, bbtag_moves as M
31:     scr = R.fpac_files(R.read("data/char/char_rrb_scr.pac"))
32:     os.makedirs(RG.CACHE, exist_ok=True)
33:     cats = []
34:     for fn in ("scr_rrb.bin", "scr_rrbea.bin"):
35:         p = os.path.join(RG.CACHE, fn); open(p, "wb").write(scr[fn]); cats.append(C.catalog(p))
36:     clips = RC.sequences(cats[0], RG.normalize, cats[1])
37:     lengths = {n: sum(t for _, t in s) for n, s in clips.items()}
38:     cj = os.path.join(RG.CACHE, "ruby_clip_lengths.json")
39:     json.dump({n: {"frames": v, "ticks": len(clips[n])} for n, v in lengths.items()}, open(cj, "w"))
40:     src = RG.Source("rrb")
41:     return cj, lengths, M.Moves(src, scr["scr_rrb.bin"], src.scale), clips
42: 
43: 
44: # ---------------------------------------------------------------- 1. engine-facing states on her clips
45: # player state -> her clip (ruby_clips name), "fit" = over the donor's timing
46: LOCO = {
47:     "stand": "stand", "standby1": "standby", "standby2": "appeal",      # idle, idle fidget, idle taunt
48:     "runStart": "run_start", "run": "run", "runBrake": "runbrake",
49:     "squat": "squat", "squat_loop": "squat_loop", "squat_to_stand": "squat_to_stand",

```


## E12｜Ruby 生成角色表与运行时钩子


来源：`Launcher/mods/char-ruby/build_ruby.py`，第 1796–1889 行。

SHA-256：`f0e544d52e785567d378636c02279f6c7f89f5a3f0d3fe872e45b2e768a955a8`


```text

1796: def write_mod(port, by, btree):
1797:     copyrow = lambda where, setv, **kw: [{"$copyRows": dict({"where": where, "set": setv}, **kw)}]
1798:     rows_ = input_rows(port, by)
1799:     row_icons(rows_)
1800:     ptabs, ploc, pbuffs = rrb_pots.content_v2(sys.modules[__name__])   # V2: per language
1801:     # a trigger her own rows grant must never have been stripped from her trees as "a donor's" (strip_foreign_hooks)
1802:     granted = {int(m.group(1)) for r in ptabs["PlayerBattleTriggerDetail"] for m in re.finditer(r"Id:(\d+)", str(r.get("OPParams") or ""))}
1803:     granted |= {r["Idx"] for r in ptabs["PlayerBattleTriggerDetail"]}
1804:     clash = sorted(i for i in granted if any(j in STRIPPED_TRIGGERS for j in range(i, i + 5)))
1805:     if clash: raise SystemExit("donor hooks were removed for triggers her own rows grant: %s (build_ruby.foreign_triggers)" % clash)
1806:     T = {
1807:         "HeroConfig": copyrow({"Id": DONOR}, {"Id": ACTOR, "LogicRes": LOGIC, "Skin": [SKIN], "MoveSpeed": 7.2, "Describe": LOGIC,
1808:                                                "Boxwidth": 0.5, "Boxheight": 1.45, "Colwidth": 0.9, "Colheight": 1.45, "CueSheets": __import__("rrb_sound").CUE_SHEETS}),
1809:         "BaseActorConf": copyrow({"ActorId": DONOR}, {"ActorId": ACTOR, "PotentialPoolId": ACTOR, "SortNum": 105, "PvpUnlocked": 0,
1810:                                                        "InheritSkill": [], "Talents": [{"Id": TALENT, "Quality": 1}], "Name": NAME_LOC["chs"]}),
1811:         "BaseActorAttrConf": copyrow({"ActorId": DONOR}, {"ActorId": ACTOR, "Attr": ATTRS}),
1812:         "PvpBaseActorAttrConf": copyrow({"ActorId": DONOR}, {"ActorId": ACTOR}),
1813:         "FesActorAttrInheritConf": copyrow({"ActorId": DONOR}, {"ActorId": ACTOR}),
1814:         # her select / result portraits: solved so she stands as tall as Hibiki with his eye line (rrb_portrait.py)
1815:         "HeroPortraitOffsetConfigUI": __import__("ruby_ui").portrait_rows(),
1816:         "ActorConfig": copyrow({"Id": DONOR}, {"Id": ACTOR}),
1817:         "ClientSkinConf": copyrow({"Id": 100101020}, {"Id": ACTOR * 1000 + 20, "HeroId": ACTOR, "SkinName": SKIN, "Color": "#c8102e"}),
1818:         "SkinUnlockConf": copyrow({"Id": 100101020}, {"Id": ACTOR * 1000 + 20}),
1819:         "BulletConfig": [{"$copyRows": {"where": {"Id": 10030101}, "set": {"Id": BID, "LogicRes": BLOGIC}}}],
1820:         "SkillActivate": rows_,
1821:         "SkillDamage": damage_rows(by, btree),
1822:     }
1823:     for k, v in ptabs.items(): T[k] = T.get(k, []) + v
1824:     for k, v in legacy_rows().items(): T[k] = T.get(k, []) + v
1825:     T["BaseActorConf"][0]["$copyRows"]["set"]["InheritSkill"] = [L["id"] for L in LEGACY]
1826:     enu = {}   # the Legacy texts in English: the fallback for a language rrb_text.LEGACY_TEXT lacks
1827:     import rrb_text as TX
1828:     for L in LEGACY:
1829:         enu.update({"InheritSkill_%d" % L["id"]: L["name"], "InheritSkillDesc_%d" % L["id"]: L["desc"], "InheritSkillDescUpgrade_%d" % L["id"]: L["up"]})
1830:     AT = TX.ACTOR_TEXT
1831:     loc = {}
1832:     for lang in LANGS:
1833:         actor = {"BaseActor_chs_%d" % ACTOR: NAME_LOC[lang], "ActorSkill_%d" % ACTOR: AT["skill"][lang], "ActorSkillDesc_%d" % ACTOR: AT["skill_desc"][lang],
1834:                  "ActorUltra_%d" % ACTOR: AT["ultra"][lang], "ActorUltraDesc_%d" % ACTOR: AT["ultra_desc"][lang]}   # rrb_text.ACTOR_TEXT
1835:         d = dict(actor, **enu); d.update(ploc[lang]); d.update(actor)
1836:         for L in LEGACY:   # the Legacy texts in each language (rrb_text.LEGACY_TEXT)
1837:             lt = TX.LEGACY_TEXT.get(L["id"]) or {}
1838:             for key, f in (("InheritSkill_%d", "name"), ("InheritSkillDesc_%d", "desc"), ("InheritSkillDescUpgrade_%d", "up")):
1839:                 v = lt.get(f)
1840:                 if isinstance(v, dict) and v.get(lang): d[key % L["id"]] = v[lang]
1841:         loc[lang] = d
1842:     import rrb_power   # the runtime (Dust, power stages, the Petal Burst gust) with its constants from rrb_power.py
1843:     js = [{"file": "data/js/gameplay/buff/BuffFuncs",
1844:            "append": rrb_power.js_config(rrb_pots, sys.modules[__name__]) + io.open(os.path.join(HERE, "src", "rrb_runtime.js"), encoding="utf-8").read()},
1845:           # 0.8.0: her SP badge on the battle HUD (the game shows SP only on the Ultra card's icon; her Dust spends it)
1846:           {"file": "data/js/window/battle/BattleUI",
1847:            "append": io.open(os.path.join(HERE, "src", "rrb_hud.js"), encoding="utf-8").read().replace("@ACTOR@", str(ACTOR))},
1848:           {"file": "data/js/core/ActorUtil",
1849:            "append": "/* char-ruby: economy tables use Ragna's rows (donor) until her own exist */\n"
1850:                      "try{globalThis.BB_ACTOR_DONOR=globalThis.BB_ACTOR_DONOR||{};globalThis.BB_ACTOR_DONOR[%d]=%d;(globalThis.BB_HUD_SPRITES=globalThis.BB_HUD_SPRITES||{})[\"Talent_%d\"]=\"IconPotential%d\"}catch(e){}" % (ACTOR, DONOR, TALENT, ACTOR)}]
1851:     import ruby_ui
1852:     pids = ruby_ui.card_ids(rrb_pots.ICON_CARDS, rrb_pots.UNLEASHED)   # the 38 cards + Potential Unleashed (IconId 20799)
1853:     content = {
1854:         "tables": T, "locale": loc, "spriteAliases": ruby_ui.aliases(pids), "textureAliases": {}, "js": js,
1855:         # the art (rig + every UI texture, icon and her HUD atlas) is built at build time from the player's own BBTAG
1856:         "importers": [{"script": "import_ruby.py", "args": ["all"]}],
1857:         # refTypesFrom: bundles whose condition-class registrations are merged into the clone, so the tree may use a
1858:         # class its donor file never declared. Base-game bundles only (until 0.6.11 Bullet's `bl` and `blbullet`, paid
1859:         # DLC, were listed too: they add no class the others lack; INTEGRATION_AUDIT O2). check_ruby_build confirms
1860:         # every class her trees use is registered in the built bundles.
1861:         "bundleClones": [
1862:             {"from": "actor/logicdata/%s" % DONOR_LOGIC, "to": "actor/logicdata/%s" % LOGIC,
1863:              "rename": [["LogicData/%s.asset" % DONOR_LOGIC, "LogicData/%s.asset" % LOGIC]],
1864:              "refTypesFrom": ["actor/logicdata/%s" % lg for lg in TEMPLATE_LOGICS if lg != DONOR_LOGIC] + ["actor/logicdata/pt"]},
1865:             {"from": "actor/logicdata/nobullet", "to": "actor/logicdata/%s" % BLOGIC, "rename": [["LogicData/nobullet.asset", "LogicData/%s.asset" % BLOGIC]],
1866:              "refTypesFrom": ["actor/logicdata/rg"]},
1867:         ],
1868:         "assets": [{"bundle": "actor/logicdata/%s.ab" % LOGIC, "asset": DONOR_LOGIC, "treeFile": "gen/%s_tree.json" % LOGIC},
1869:                    {"bundle": "actor/logicdata/%s.ab" % BLOGIC, "asset": "nobullet", "treeFile": "gen/%s_tree.json" % BLOGIC},
1870:                    {"bundle": "actor/buff/buff.ab", "asset": "Buff", "copyItems": pbuffs},
1871:                    {"bundle": "ui/texture/metrics.ab", "asset": "metrics", "appendItems": ruby_ui.metrics_rows(pids)}],
1872:     }
1873:     mp = os.path.join(HERE, "mod.json")
1874:     m = json.load(io.open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
1875:     m.update({"id": os.path.basename(HERE), "name": "Ruby Rose (Cross Effect, alpha)", "author": "BBEE modding project", "version": VERSION,
1876:               "description": "Ruby Rose from BlazBlue Cross Tag Battle as a playable character (ActorId 200701). Built on your machine from "
1877:                              "your own BlazBlue Cross Tag Battle install; requires BBTAG and all of its DLC. Unofficial.",
1878:               "gameBuilds": ["25478197", "25598842", "25621352", "25627491"], "dependencies": ["bbee-sdk", "bbee-actors"], "content": content})
1879:     io.open(mp, "w", encoding="utf-8", newline="\n").write(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
1880:     print("mod.json: %d tables, %d input rows, %d damage rows, %d Potentials, %d text keys" % (
1881:         len(T), len(T["SkillActivate"]), len(T["SkillDamage"]), len(rrb_pots.CARDS) + 1, len(loc["enu"])))
1882: 
1883: 
1884: def main():
1885:     # her moves, timings and boxes are derived from the player's Cross Tag Battle script: the ownership check comes
1886:     # before anything is read from that install (it used to run only at install; INTEGRATION_AUDIT O3)
1887:     import import_ruby
1888:     import_ruby.require_ownership()
1889:     port, by, btree = build_logic()

```


## E13｜固定点数值


来源：`Launcher/mods/char-ruby/own/bossport.py`，第 35–37 行。

SHA-256：`81cee570fe48f271a4987be7a33670b68a5952a4570e48f00f6c8cc4f77ea225`


```text

35: FP = 4294967296.0
36: def fp(x): return {"value": int(round(x * FP))}
37: def fv(v): return v["value"] / FP if isinstance(v, dict) and "value" in v else (float(v) if isinstance(v, (int, float)) else 0.0)

```


## E14｜条件引用创建


来源：`Launcher/mods/char-ruby/own/bossport.py`，第 156–182 行。

SHA-256：`81cee570fe48f271a4987be7a33670b68a5952a4570e48f00f6c8cc4f77ea225`


```text

156: class Refs:
157:     """New condition references (the boss never needed them). Their classes must be in the output bundle's ref_types:
158:     pass refTypesFrom [rg (Input/GroundCheck/Trigger), bl (MP, Input), pt (BulletCount)] to the bundle clone."""
159:     def __init__(self, base): self.base, self.items = base, []
160:     def new(self, cls, data):
161:         rid = self.base + len(self.items)
162:         self.items.append({"rid": rid, "type": {"class": cls, "ns": "GamePlay", "asm": "Assembly-CSharp"}, "data": dict({"Invert": 0}, **data)})
163:         return {"rid": rid}
164:     def input(self, key, mode, sticky=0.0):   # InputCmd 1 Attack 3 Skill 5 Summon 55 Dash 800 Jump; mode 0 Pressed 2 Pressing 3 NotPressing
165:         return self.new("ActionLogicCondition_Input", {"InputKey": key, "InputKeyMode": mode, "InputStickyTime": fp(sticky), "InputStickyTimeEnd": fp(0)})
166:     def buff(self, bid, invert=0, stack_min=0, stack_max=None):
167:         return self.new("ActionLogicCondition_Buff", {"Invert": invert, "BuffId": bid, "Str": {"Min": fp(0), "Max": BIG},
168:                                                       "Stack": {"Min": fp(stack_min), "Max": fp(stack_max) if stack_max is not None else BIG}, "IncludeRootCaster": 0})
169:     def mp(self, lo, hi=100, slot=2): return self.new("ActionLogicCondition_MP", {"Slot": slot, "Min": fp(lo), "Max": fp(hi)})
170:     def ground(self, off): return self.new("ActionLogicCondition_GroundCheck", {"OffGroundCheck": off})   # 1 in the air, 2 on the ground
171:     def trigger(self, tid, invert=0):   # the character holds Potential/trigger tid (levels tid..tid+4); works from projectiles
172:         return self.new("ActionLogicCondition_Trigger", {"Invert": invert, "TriggerIdMin": tid, "TriggerIdMax": tid + 4, "IncludeRootCaster": 1, "CDCheck": 0})
173:     def hit(self, within=0.1):         # this actor hit something in the last `within` seconds
174:         return self.new("ActionLogicCondition_Hit", {"HitSuccTimeEllaps": fp(within), "HitSuccCheckType": 0})
175:     def inputdir(self, lr=0, down=0, up=0, invert=0):
176:         return self.new("ActionLogicCondition_InputDir", {"Invert": invert, "CheckLR": lr, "CheckDown": down, "CheckFront": 0, "CheckBack": 0, "CheckUp": up})
177:     def bullets(self, logic, tag, names, none=True):
178:         return self.new("ActionLogicCondition_BulletCount", {"Invert": 1 if none else 0, "BulletActionGroup": logic, "ActionNames": names,
179:                                                              "BulletTag": tag, "Min": 1, "Max": 999})
180: 
181: # Ragna's player states (the engine-facing flow: physics, timings, transitions the controller expects)
182: PLAYER_STATES = ["stand", "standby1", "standby2", "runStart", "run", "runBrake", "squat", "squat_loop", "squat_to_stand",

```


## E15｜逻辑树组装与引用检查


来源：`Launcher/mods/char-ruby/own/bossport.py`，第 326–344 行。

SHA-256：`81cee570fe48f271a4987be7a33670b68a5952a4570e48f00f6c8cc4f77ea225`


```text

326:         used = set()
327:         def walk(o):
328:             if isinstance(o, dict):
329:                 if "rid" in o and len(o) == 1: used.add(o["rid"])
330:                 for v in o.values(): walk(v)
331:             elif isinstance(o, list):
332:                 for v in o: walk(v)
333:         walk(acts)
334:         refs = [r for r in self.B["references"]["RefIds"] if r["rid"] in used and r["type"]["class"]] + \
335:                [r for r in self.R["references"]["RefIds"] if r["rid"] in used and r["type"]["class"]] + \
336:                [r for r in self.refs.items if r["rid"] in used]
337:         missing = used - {r["rid"] for r in refs} - {-2}
338:         if missing: raise SystemExit("unresolved reference ids: %s" % sorted(missing)[:5])
339:         tree = {k: copy.deepcopy(v) for k, v in self.B.items() if not k.startswith("m_") and k not in ("_actions", "references")}
340:         tree.update({"m_Name": name, "ALGType": 0, "_actions": acts, "references": {"version": self.B["references"]["version"], "RefIds": refs}})
341:         return tree
342:     def bullet_tree(self, src, dst, extra=None):
343:         T = copy.deepcopy(logic(src))
344:         for a in T["_actions"]:

```


## E16｜帧、网格、动画数据与依赖


来源：`Launcher/mods/char-ruby/own/tools/bbtag/bbtag_rig.py`，第 501–534 行。

SHA-256：`b86ac2eb7326193bb0fcedb476237157ec712e536fbfa76e6a01971a4d67db41`


```text

501:     ni = {n: i for i, n in enumerate(names_m)}
502:     donor_deps = [names_m[int(d, 16)] for d in next(d for i, d in entries_m if int(i, 16) == ni[DONOR_CLIP])]
503:     for name, seq in clips.items():
504:         if not seq:
505:             continue
506:         dst = "actor/animation/role/%s" % name.lower()
507:         mg = clip_group[name]
508:         env = _env(bbmod, UnityPy, DONOR_CLIP)
509:         cab = list(env.file.files.keys())[0]; sf0 = env.file.files[cab]
510:         mb = next(o for o in sf0.objects.values() if o.type.name == "MonoBehaviour")
511:         t0 = mb.read_typetree(); mfid = t0["Frames"][0]["mesh"]["m_FileID"]
512:         old_mesh_cab = sf0.externals[mfid - 1].path.split("/")[-1]
513:         sf, _ = _retarget(env, dst, None, {old_mesh_cab.lower(): _cab(mg)})
514:         t = t0
515:         t["m_Name"] = name
516:         frames, ends, tick = [], [], 0
517:         for s, ticks in seq:
518:             frames.append({"mesh": {"m_FileID": mfid, "m_PathID": mesh_pid[(mg, s)]}, "textureIdx": fr[s]["place"][0], "mountPoints": []})
519:             tick += max(1, int(ticks)); ends.append(tick - 1)
520:         t["Frames"] = frames; t["Indeces"] = ends; t["TotalFrameCount"] = tick
521:         t["Context"]["AnimationRoleName"] = role
522:         mb.save_typetree(t)
523:         ab = _bundle_obj(sf); at = ab.read_typetree()
524:         script_pid = t["m_Script"]["m_PathID"]
525:         pre = [{"m_FileID": 0, "m_PathID": script_pid}, {"m_FileID": 0, "m_PathID": mb.path_id}]
526:         pre += [p for p in at["m_PreloadTable"] if p["m_FileID"] not in (0, mfid)]              # the material
527:         pre += [{"m_FileID": mfid, "m_PathID": pid} for pid in sorted({f["mesh"]["m_PathID"] for f in frames})]
528:         at["m_PreloadTable"] = pre
529:         at["m_Container"] = [["Assets/AssetBundle/Actor/Animation/Role/%s.asset" % name, {"preloadIndex": 0, "preloadSize": len(pre), "asset": {"m_FileID": 0, "m_PathID": mb.path_id}}]]
530:         at["m_Name"] = dst + ".ab"; at["m_AssetBundleName"] = dst + ".ab"
531:         at["m_Dependencies"] = [d if d.lower() != old_mesh_cab.lower() else _cab(mg).lower() for d in at["m_Dependencies"]]
532:         ab.save_typetree(at)
533:         _save(env, out_dir, dst)
534:         adds["names"].append(dst)

```


## E17｜Ruby 资源导入入口


来源：`Launcher/mods/char-ruby/import_ruby.py`，第 73–104 行。

SHA-256：`3785296e81230f6db7d0e16a50ce47d56d00eb6f47ac0342528721dce0a509cf`


```text

73: def main():
74:     ap = argparse.ArgumentParser()
75:     ap.add_argument("what", choices=["all", "rig", "ui", "audio"])
76:     ap.add_argument("--out", required=True)
77:     ap.add_argument("--adds", required=True)
78:     a = ap.parse_args()
79:     require_ownership(a.out)   # first: nothing below runs for a player who doesn't own Cross Tag Battle and its DLC
80: 
81:     import bbtag_clips, bbtag_rig, bbtag_read, ruby_clips
82:     if not os.path.isdir(os.path.join(bbtag_read.INSTALL, "asset")):
83:         sys.exit("Cross Effect: BlazBlue Cross Tag Battle not found at %s (set BBTAG_DIR)." % bbtag_read.INSTALL)
84:     src = bbtag_rig.Source("rrb")
85:     src.scale_mul = ruby_clips.EFFECT_SCALE
86:     scr = bbtag_read.fpac_files(bbtag_read.read("data/char/char_rrb_scr.pac"))
87:     os.makedirs(bbtag_rig.CACHE, exist_ok=True)
88:     cats = []
89:     for fn in ("scr_rrb.bin", "scr_rrbea.bin"):
90:         tmp = os.path.join(bbtag_rig.CACHE, fn); open(tmp, "wb").write(scr[fn]); cats.append(bbtag_clips.catalog(tmp))
91:     clips = ruby_clips.sequences(cats[0], bbtag_rig.normalize, cats[1])
92:     adds = {"names": [], "entries": [], "guids": []}
93:     if a.what in ("all", "rig"):
94:         r = bbtag_rig.build_rig(src, clips, a.out, ruby_clips.ROLE, ruby_clips.SKIN)
95:         for k in adds: adds[k] += r[k]
96:         import ruby_fx   # Red Reaper's astral sky: her BBTAG background art in a clone of BBEE's Astral Heat backdrop
97:         r = ruby_fx.build_astral(a.out)
98:         for k in adds: adds[k] += r[k]
99:         import ruby_clashbg   # Clash Assault's backdrop (the colour burst) and start flash: BBTAG's own, from the player's install
100:         # (0.8.0: the diamond vortex, CLASH_FX, is no longer built: one backdrop for the whole move; rrb_power.clash_bg)
101:         r = ruby_clashbg.build(a.out, which=(ruby_clashbg.FINISH_FX, ruby_clashbg.START_FX))
102:         for k in adds: adds[k] += r[k]
103:         # (her rose afterimage, ruby_fx.build_afterimage, is no longer built: no action names Role/Rrb/rrb_afterimage
104:         #  since the effects pass of 2026-09-30, "no afterimage copies"; INTEGRATION_AUDIT D5)

```


## E18｜Kris 第一段地面普攻的数据

以下为实际 JSON 对象的精选字段；JSON Pointer 中数组下标从 0 开始。固定点的解码值由 E13 的换算规则计算，不是游戏内测量。

```json

{
  "scope": "Static source trace, not measured gameplay timing or damage",
  "sources": {
    "input": "Launcher/mods/dr-party/mod.json#/content/tables/SkillActivate/0",
    "action": "Launcher/mods/dr-party/gen/kris_tree.json#/_actions/71",
    "damage": [
      "Launcher/mods/dr-party/mod.json#/content/tables/SkillDamage/2"
    ],
    "fixed_point_converter": "Launcher/mods/char-ruby/own/bossport.py:35-37"
  },
  "input": {
    "$new": true,
    "ActorId": 200801,
    "Group": 1,
    "Order": 1,
    "Action": "kris_a1",
    "AllowActiveState": true,
    "AutoTurn": 1,
    "ActionpointInputTag": 1,
    "ActionpointInputTag2": 1,
    "Preinputtime": 0.2,
    "ActdurStrict": 0.22,
    "AllowGround": true,
    "Input": "Attack",
    "StartTrigger": [
      "Start_1"
    ],
    "Mutelist": "\"all\":0.05,\"5\":0.01,\"7\":0.05",
    "Timeout": 0.45
  },
  "action": {
    "Name": "kris_a1",
    "Animate": "kris_atk1",
    "AnimateDuration": {
      "raw": 1503238554,
      "decoded": 0.35000000009313226,
      "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
    },
    "TotalDuration": {
      "raw": 1503238554,
      "decoded": 0.35000000009313226,
      "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
    },
    "first_hit_window": {
      "Start": {
        "raw": 214748365,
        "decoded": 0.05000000004656613,
        "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
      },
      "End": {
        "raw": 715827883,
        "decoded": 0.16666666674427688,
        "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
      },
      "HitInterval": {
        "raw": -4294967296,
        "decoded": -1.0,
        "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
      }
    },
    "first_hit_box": {
      "Min": {
        "x": {
          "raw": -2491081032,
          "decoded": -0.5800000000745058,
          "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
        },
        "y": {
          "raw": -830360344,
          "decoded": -0.1933333333581686,
          "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
        }
      },
      "Max": {
        "x": {
          "raw": 5626407158,
          "decoded": 1.3100000000558794,
          "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
        },
        "y": {
          "raw": 6781276142,
          "decoded": 1.5788888889364898,
          "encoding": "raw / 4294967296; explicitly identified fixed-point wrapper"
        }
      }
    },
    "AddEffects_raw": [
      {
        "Start": {
          "value": 0
        },
        "ConditionGroup": {
          "Combine": 0,
          "Conditions": []
        },
        "NameEx": {
          "UseExpression": 0,
          "ConstValue": "Role/Kris/kris_slash_1",
          "Expression": {
            "Source": ""
          }
        },
        "Rotation": {
          "x": {
            "value": 0
          },
          "y": {
            "value": 0
          }
        },
        "Scale": {
          "x": {
            "value": 4294967296
          },
          "y": {
            "value": 4294967296
          }
        },
        "RandomScale": {
          "x": {
            "value": 4294967296
          },
          "y": {
            "value": 4294967296
          }
        },
        "Binding": 1,
        "KillMode": 2,
        "Position": {
          "x": {
            "value": 0
          },
          "y": {
            "value": 0
          }
        },
        "AbsolutePos": 0,
        "BindPos": 0,
        "RandomPlay": 0,
        "OnGround": 0,
        "HideEffectWhenNoVisible": 0,
        "HideEffectIfNotSelf": 0,
        "CheckExistingByName": 0,
        "Layer": 678496669,
        "OverrideFXLifeTime": {
          "value": 0
        },
        "BindDirType": 1,
        "LodCheckType": 0
      }
    ]
  },
  "damage_rows": [
    {
      "ActorId": 200801,
      "Action": "kris_a1",
      "HitTimes": 1.0,
      "SkillGroupId": 1,
      "FluctMin": 1.0,
      "FluctMax": 1.0,
      "DamageRatio": [
        1.1
      ],
      "VibrateName": "3_mid_short",
      "DamageRatioPvp": [
        1.1
      ],
      "$append": true
    }
  ]
}

```

## E19｜独立离线验证

`static_audit.json` 记录文件语法、描述符路径、依赖、六棵已提供动作树的引用检查；`composer_tests.json` 记录四项隔离组合测试。

表组合测试仅执行了人工审阅的 table_keys、rowkey、depends_on、ensure_orig、compose_tables 和字面量 KEY_OVERRIDES，临时目录中使用合成原版行及上传包 dr-party 的真实表补丁。没有执行 bbmod 的顶层初始化、完整构建、安装或游戏。