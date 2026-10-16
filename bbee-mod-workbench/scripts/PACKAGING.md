# 本地交付与宇文逸启动

工程与保留进度入口已完成。用户最新直接回复“已解锁，可以实机”，主会话实际核对unlocked，覆盖先前只离线历史停点；当前原生图像QA收尾后用下述正式play入口，按 [唯一实机清单](../docs/work/yuwen-yi/acceptance.md#实机最小清单) 集中验收，结果仍pending，不预称已交付。

本工作台固定在 `E:\AAA MOD\bbee-mod-workbench`，游戏build为25627491。角色包是现有工作台的源码、冻结素材和原生构建产物覆盖包，不包含游戏、解释器、不可变基线、私有配置或任何存档，也不承诺换盘/任意目录免配置。原Steam目录保持输入用途。

2026-10-16状态：修复批工程18阶段passed，179包strict／重复构建一致、完整安装事务及工作／基线／源各2,397hash通过。交付闭包补修后重新141编译／291回归（289通过2跳过，93.872秒），native字节与输入闭包未变，未重复重建native；31离线事件通过。旧首测和managed声明失败保留为历史，实际体验仍pending；权威 [工程收据](../evidence/yuwen-yi/engineering-acceptance.json)及 [交付闭包收据](../evidence/yuwen-yi/delivery-closure-acceptance.json)的覆盖由 [角色工作记录](../docs/work/yuwen-yi/acceptance.md) 持有。

所有启动、配置、恢复与打包命令使用同一便携Python3.14.8，避免系统Python的目录身份差异；`-B`避免本轮生成源码缓存：

```powershell
$bbeePython = 'E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Interpreter\pythoncore-3.14-64\python.exe'
```

## 打包入口

全部实现、统一编译、角色完整构建、重复构建和事务还原验收通过以后，才执行：

```powershell
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\package_patch.py'
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\package_patch.py' --character
```

无参数生成基础设施与本profile五个mod的文本源码补丁，PNG/原生AB不参与文本diff。`--character`生成独立本地角色ZIP：完整native patch_out、五个mod相关文本源码、角色作者/准备素材、实际manifest声明的参考闭包、完整视觉review、profile与复现脚本。每项记录哈希并重新打开ZIP校对；源代码/素材/descriptor或构建闭包变化会拒绝交付。ZIP不会自动解压、安装、启动或改存档。

独立交付审阅发现审核JSON引用的5张外部PNG漏装，现已纳入哈希绑定的交付闭包；不是仅装审核JSON却遗漏其证据图。当前 `_build.json` 为 `a85afaa34a33698b2719e232d37e90ce6f9ce8520fa63c4aea180db58ddf4a49`，候选将命名为 `delivery/bbee-yuwen-yi-local-a85afaa34a33698b.zip`与 `delivery/bbee-yuwen-yi-local-a85afaa34a33698b.receipt.json`，存在及ZIP重读结果以实际打包收据确认，本段不预称已生成／交付。

门禁读取工程收据、角色`reproducibility.json`及patch_out的`_build.json/_verification.json`，核对成功阶段、profile、全部原生文件与递归输入闭包。平台旧记录不能替代角色结果。当前 [角色实机收据](../evidence/yuwen-yi/character-runtime-acceptance.json)已创建并精确绑定新a85构建与profile，status及character_selection／combat／reopen全部pending，明确未启动。也可用`--runtime-receipt <工作台内公开角色收据>`指定，passed须三项均通过。只把公开状态装入ZIP，原始运行日志与存档资料不收录。

三个状态是打包器最小摘要，不能代替唯一6项实机清单。pending本地候选须如实标待验，不能称角色体验已完成；当前未预称角色ZIP已交付。

## 复现

既有基线、已解码schema和固定依赖必须预先存在。素材冻结后的常规角色prepare/build命令为：

```powershell
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\workbench.py' prepare --profile 'E:\AAA MOD\bbee-mod-workbench\profiles\yuwen-yi.json'
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\workbench.py' run --label yuwen-build --profile 'E:\AAA MOD\bbee-mod-workbench\profiles\yuwen-yi.json' bbmod.py build
```

完整工程验收入口为 `scripts/yuwen_acceptance.py --visual-review <本批准确视觉审阅JSON>`，覆盖源码编译、素材准备、全回归、事件／表审计、完整及重复构建、安装／更新／撤回／卸载与副本输入恢复。本修复批使用 `evidence/yuwen-yi/complete-art-visual-review-first-playtest-repair.json`，旧prepared55文件已按哈希归档后才移出owned目录重备。旧素材、收据及失败历史仍保留；不要手删未知文件来强行重跑。

代码修复且素材未变时可用显式 `--reuse-prepared-art`，仍核对全部producer／合同／像素／时序／UI哈希，不能复用漂移素材。该工程入口结束会卸载，使用的是显式测试存档合同，不是日常游玩按钮，也不证明玩家当前进度已迁移或保留。

## 保留当前进度并转正式游玩

本批入口配置已实际完成：[persistent-entry-configuration.json](../evidence/yuwen-yi/persistent-entry-configuration.json)记录旧run成功release，原备份与当前44文件备份verified、进度exact、存档零写入／恢复；guard已归档，`configure --from-preserved-run`成功、配置阶段未launch。无需重复restore／release／configure。配置时副本卸载保持2,397文件pristine，首次双击根 `play-yuwen-yi.cmd`会自动安装已验候选。以下迁移命令仅供未来新测试run使用。

目标始终为 `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\game\BlazblueEntropyEffect.exe`，不会改到源Steam安装。配置与日志留E盘private，不自动搜索账号或存档根；正常保存与新进程重开仍须实机。

未来若有新的active测试guard，先正常关闭游戏并确认run。仅当 `private/runtime/launcher.json` 仍active时执行下面restore；已复位则跳过，重复restore会拒绝无active launcher前态。本批旧launcher与guard均已归档，不能照抄这些迁移命令重做。

```powershell
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\runtime_launcher.py' restore
```

确认launcher已复位后，再依次执行保留进度release和配置：

```powershell
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\runtime_guard.py' release --keep-progress
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\play_launcher.py' configure --from-preserved-run '<release成功返回的run_id>'
```

每一步成功后才继续。`release --keep-progress`核验测试前备份，再备份并回读当前进度，绑定run／根身份／文件集合／manifest SHA；不把旧文件写回实际存档，也不宣称实机验收通过。配置迁移再次核验两份备份及release记录。失败须保留私有journal和备份，不改用旧 `guard.finish` 回滚当前进度。

首次配置且没有旧guard时，显式指定已经授权的真实根；下面是占位示意，不能照抄为实际目录：

```powershell
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\play_launcher.py' configure --save-root '<明确选择的真实存档根>'
```

## 正常启动、保存与异常收尾

当前配置与工程门禁已完成，用户也已明确允许实机；原生图像QA收尾后可采用以下入口：

日常可双击工作台根目录的 [play-yuwen-yi.cmd](../play-yuwen-yi.cmd)。它使用固定便携解释器和E盘临时目录进入同一 `play`；首次正式配置及工程门禁未满足时会停止，不自动发现存档。等价命令为：

```powershell
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\desktop_session.py' check
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\play_launcher.py' play
```

`play`核对最新角色工程收据／profile／全部native文件／metadata／递归源码闭包；若未安装，则通过同一安全安装器安装该已验构建。准备与测试guard互斥，锁屏或未知会话拒绝启动。它核验游玩前存档备份，固定EXE和cwd，显式把子进程TEMP／TMP放 `private/temp/play`、Player.log放私有run目录，启动并等待游戏退出。不要以Steam库按钮或手开快捷方式替代此正常入口的环境合同。

游戏内正常保存并关闭后，`play`自动执行正常finish：回读游玩后备份和当前文件集合，只复位自有代理隔离／AppID／快捷方式，角色仍安装，当前进度不恢复为游玩前状态。游戏自己的正式存档仍在配置的真实位置，未声称迁到E盘。实际保存、退出及新进程重开保留进度的结果，须由同构建实机证明。

启动器崩溃、被中断或COM创建失败后，先确认游戏已关闭，再执行：

```powershell
& $bbeePython -B -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\play_launcher.py' finish
```

该finish仍不恢复／覆写存档。未知公开文件或哈希漂移会停止并保留恢复证据；只对本run私有staged快捷方式允许隔离未登记候选，未知公开快捷方式仍拒绝处理。不要手改journal、删除备份或覆盖未知文件来绕过恢复。

## 可回滚测试与卸载

`runtime_guard.py begin`＋`runtime_launcher.py prepare/restore`＋`runtime_guard.py finish`继续保留原可回滚测试语义：finish恢复测试前存档，试玩进度丢弃。仅在明确选择可回滚测试时使用，不能用作本批正式进度保留或日常退出。旧guard转正式游玩按上节显式release，不改变原finish语义。

安装／更新／撤回／卸载是独立事务。`workbench.py run ... entry_point.py uninstall`默认绑定 `private/test-saves`，不能据此宣称已经清理真实玩家的角色状态。涉及真实存档的卸载必须游戏关闭、明确绑定 `BBEE_SAVE_ROOT`，先核验备份与计划，再执行同一事务入口；正常退出不卸载、不回滚进度。原Steam目录与源ZIP始终只读。
