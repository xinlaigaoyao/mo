# BBEE Mod 独立工作台

最新实机：用户确认普攻截断改善，但选中潜能图标、三段动作区分与对应武学特效仍需修复，见 [第二轮实机工单](docs/work/yuwen-yi/issues/02-second-playtest.md)。当前角色实机未通过；a85候选的离线通过不覆盖下一修复批。正式入口仍保留当前进度。

用户最新直接回复“已解锁，可以实机”，主会话实际核对unlocked；此前“人在寝室外／先只离线”保留为历史停止点。工程及保留进度入口完成，当前原生图像QA收尾后集中执行 [宇文逸实机最小清单](docs/work/yuwen-yi/acceptance.md#实机最小清单)，实际结果仍pending，未预称通过或已交付。

本目录用于补齐 Zenith Terminal 0.3.0-alpha 的基础设施并制作宇文逸。目标游戏 build `25627491`、Unity `2022.3.62f2`。非角色平台 readiness 已完成 **`engineering-passed / runtime-passed`**：120 份源码编译、265 项回归中 263 通过／2 跳过、29 包严格回读和双构建一致、安装更新撤回卸载均通过；Inspector 0.4.1 的实机 F9、effect hook、同构建重开与退出还原已完成。这是平台阶段结果。

宇文逸 ActorId `200901`／skin Id `200901020` 已正式分配；旧首测的连按、潜能UI和特效缺陷已实施整批修复，失败历史保留。2026-10-16新批工程18阶段通过：141份编译、291项回归中289通过／2跳过、31离线事件；179包strict及重复构建一致，完整事务和工作副本／基线／源游戏各2,397hash通过。交付闭包补修后另重新编译／回归，native字节未变、没有再次重建。实际体验仍pending；规格见 [宇文逸规格](docs/work/yuwen-yi/spec.md)，权威结果与SHA见 [角色工作记录](docs/work/yuwen-yi/acceptance.md)，根因见 [首测修复清单](docs/work/yuwen-yi/issues/01-first-playtest.md)。其他角色可操作不能替代宇文逸验收。

平台状态以 [基础设施验收](docs/work/mod-infrastructure/acceptance.md) 为准，角色状态以上述角色工作记录为准。原研究和上次审计是历史证据，附件中的操作指令没有被当作用户授权；此前“允许实机”的历史授权不改变当前先做完离线项的安排。

## 目录和入口

`baselines/25627491/game` 是完整物理输入快照；`ZenithTerminal/Launcher/game` 是另一份可写物理副本。二者均无硬链接或目录联接。原 Steam 游戏仅作为输入。快照代表本机现有兼容组合，不是 Steam depot 纯净认证；敏感代理配置不复制、不读取。

`scripts/workbench.py` 固定便携 Python、显式 build、构建环境和证据目录。默认绑定 `private/test-saves`，空测试目录会明确报告没有备份，不会冒充实际存档已受保护。Unity 的真实存档位置不因构建用的 USERPROFILE 环境变量而被假定隔离。

正式配置已完成，正常入口为根目录 [play-yuwen-yi.cmd](play-yuwen-yi.cmd)或 [scripts/play_launcher.py](scripts/play_launcher.py)。旧guard已保留进度release归档：原始备份与当前44文件备份均核验、当前进度exact，零存档写入／恢复，见 [入口配置收据](evidence/yuwen-yi/persistent-entry-configuration.json)。配置时副本卸载保持2,397文件pristine，首次play会自动安装已验a85候选。它显式绑定真实根，前后备份，正常退出只恢复owned启动配置并保留进度及角色；TEMP／日志在E盘。实际保存／退出／重开仍pending，命令及恢复由 [PACKAGING.md](scripts/PACKAGING.md) 持有。旧 `runtime_guard.finish`回滚测试进度，不能用于日常游玩。

下面是工程操作，不是正常游玩步骤。完成全部实现后，统一执行编译、fresh 解码、prepare、完整构建、重复构建、回归及物理副本安装/更新/卸载：

```powershell
python -X utf8 "E:\AAA MOD\bbee-mod-workbench\scripts\final_acceptance.py" --profile "E:\AAA MOD\bbee-mod-workbench\profiles\framework-runtime.json"
```

日常重新构建使用下列入口；prepare 处理递归依赖，并在需要生成时恢复已核验的原始表/脚本。缓存命中不会重写输入。GUI 和 CLI 安装均调用相同准备入口。

```powershell
python -X utf8 "E:\AAA MOD\bbee-mod-workbench\scripts\workbench.py" prepare --profile "E:\AAA MOD\bbee-mod-workbench\profiles\framework-runtime.json"
python -X utf8 "E:\AAA MOD\bbee-mod-workbench\scripts\workbench.py" run --label build --profile "E:\AAA MOD\bbee-mod-workbench\profiles\framework-runtime.json" bbmod.py build
```

产物只有同时具有成功 `_build.json` 和 `_verification.json`，且束集合、metadata、baseline 哈希一致时才可安装。原独立写 manifest、直接复制资源等入口已封闭，安装涉及的 bundle、索引、manifest、安装记录及计划中的存档变更必须共用可恢复事务。跨卷提供日志恢复和整组回退，不承诺多文件瞬时同时可见；游戏运行时拒绝安装。

```powershell
python -X utf8 "E:\AAA MOD\bbee-mod-workbench\scripts\workbench.py" run --label install --profile "E:\AAA MOD\bbee-mod-workbench\profiles\framework-runtime.json" entry_point.py install
python -X utf8 "E:\AAA MOD\bbee-mod-workbench\scripts\workbench.py" run --label uninstall entry_point.py uninstall
```

这些命令操作本工作台副本，默认不操作私人存档。真实存档使用必须显式绑定，备份先回读核验，再规划变更；恢复会保留恢复前备份。不能把移除 Mod 文件夹视作完整卸载。

本轮验收明确使用 `framework-runtime.json` 的完整非角色集合，其中中性资源 probe 以不改业务对象字节的原始资源克隆覆盖 importer、新 CAB 和 manifest 新增。本 profile 的 external PPtr 检查数实际为 **0**，不构成外部引用正向样本。省略 `--profile` 会采用原包默认角色集合；该集合已实际生成 1,154 个包，但严格门禁发现 Ruby 专属素材生成器的悬空引用而拒绝安装，详见 `evidence/resource-reference-diagnostic.json`。旧角色源文件保留待办，未将其失败计作非角色 profile 通过。

## 复现与验收边界

依赖版本见 `dependencies.lock.json`，源码编译收据、完整命令日志、测试汇总、构建回读和安装证据保存在 `evidence`。重复资源构建应逐束哈希一致，执行时间等记录元数据单独保留。普通整数、大整数和固定点按精确语义比较，浮点按实际字段表示规范化；未知 wire 保留，不能静默丢字段。

JS 重复锚点只允许 `compatibility-contracts.json` 中按 build、模块 SHA、锚点 SHA、精确旧/新文本和次数核定的四条合同。其它歧义继续阻止构建。

TypeTree 必须与实际游戏版本及元数据绑定，并通过真实对象严格回读。原生 API 的布局不自动算正确；已验证嵌入布局可以缓存后离线使用。原生依赖只安装在本工作台的便携环境，没有全局升级。静态 Il2CppDumper 本地源码构建已移除 Windows LoadLibrary 回退；来源及哈希见 `evidence/dumper-source-assessment.json`。

本机工具源文件和下载缓存保留在 `tools`，统一验收会重新编译静态工具。若在另一工作台重建，需要 [Il2CppDumper v6.7.46 源码](https://github.com/Perfare/Il2CppDumper/releases/tag/v6.7.46)，源码 ZIP SHA-256 为 `30ed88daf62b2da25ed2a82ffc31b9cf97371292d2fb8131cc4c39ffc8690f43`，随后覆盖本补丁中的 `Program.cs`、`Utils/PELoader.cs` 并使用 `tools/NuGet.Config` 编译。便携环境新增的 [TypeTreeGeneratorAPI 0.0.10](https://pypi.org/project/TypeTreeGeneratorAPI/) wheel 哈希和下载地址见 `evidence/typetree-package-assessment.json`；使用 `requirements.typetree.lock.txt` 的单一固定版本，不自动升级。

递归指纹只排除明确声明且与生产源码哈希绑定的派生诊断输出；当前精确合同见 `Launcher/build-input-contracts.json`。整个 `gen` 目录、真正素材及生成树继续纳入输入，生产源码变动会使旧排除合同失效。

实际画面、F9 诊断、重开、原内容回归与存档绑定另行记录，构建成功不替代它们。可回滚测试 `runtime_guard.py` 在启动前创建已验证私人备份，`finish`会恢复并核对目录原态；正式play只备份、保留当前进度。原始日志、账号目录和存档字节只留在受限 `private` 目录。

独立副本直接启动时，[Steamworks 官方说明](https://partner.steamgames.com/doc/sdk/api#initialization_and_shutdown)提供 `steam_appid.txt` 开发提示，按目标进程当前工作目录查找；它不替代正常许可条件。早先三轮未通过实机验收：记录到黑色窗口或 Steam 重定向，并完成当时的文件与存档恢复。后来核对发现，旧记录中的工作目录只来自 Node 工具，未证明游戏目录；旧黑图也缺少桌面锁定前态，不能据此归因代理 DLL。本轮曾实际确认锁屏时连 Explorer 都截图全黑，解锁后重新开展运行验收。

使用 `scripts/desktop_session.py check` 只读核对当前桌面会话；锁定或未知均阻止测试或正式启动准备，恢复入口不受锁屏限制。测试启动准备要求已验证的存档guard，只临时隔离副本三个已核对代理，创建带正确WorkingDirectory的owned快捷方式与副本AppID提示，不自动启动游戏、不改Steam或原安装。

运行保护、正式游玩、启动准备和恢复必须使用同一固定便携 **Python 3.14.8**。系统Python3.11.9的 `st_dev` 表示与已绑定前态不同，已被正确拒绝，见 [解释器身份记录](evidence/runtime-interpreter-identity.json)。统一验收通过并完成显式配置后的正常入口为：

```powershell
$bbeePython = "E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Interpreter\pythoncore-3.14-64\python.exe"
& $bbeePython -B -E -s "E:\AAA MOD\bbee-mod-workbench\scripts\desktop_session.py" check
& $bbeePython -B -E -s "E:\AAA MOD\bbee-mod-workbench\scripts\play_launcher.py" play
```

`play`等待游戏正常退出后执行保留进度的收尾。若启动器中断，先确认游戏已关闭，再用同一解释器恢复owned启动配置：

```powershell
& $bbeePython -B -E -s "E:\AAA MOD\bbee-mod-workbench\scripts\play_launcher.py" finish
```

历史平台run `9a95cfaa547b4837868243de38886267` 的Inspector0.4.1实机报告记录effect订阅成功 **1次**、`fx+` **118次**、warnings **0**；同构建重开看到主菜单和fresh探针，保存路径／cwd匹配。该run存档精确还原、代理／快捷方式／AppID复位和卸载均完成，工作与原输入各2,397项哈希通过；“无active记录”仅描述该历史结束点，不能推定当前角色run状态。见 [实机修复验收](evidence/inspector-fixed-runtime.json)、[运行还原](evidence/runtime-acceptance.json) 和 [最终输入恢复](evidence/runtime-final-restoration.json)。精确存档范围为字节、名称、目录、mode和mtime，atime仅best effort；新增角色专属分支另验收。

宇文逸参考工具完成两份源码内存编译及28项集中检查，核验9个原始成员和5个输出，三个拒绝案例通过，合成临时fixture已移除，见 [参考验收](evidence/yuwen-yi/reference-validation.json)。初批145px头像只有小头像视觉结论；追加画像批的NPC中文名字对照已确认Hero和Hero_WuDang均为宇文逸，并读取6张原图，见 [画像验收](evidence/yuwen-yi/portrait-reference-validation.json)。

身体Paper2D首批曾在 `APNG preview has no frame duration` 失败并停止，原失败保留；修复批21组检查已通过，完整36个flipbook／142个sprite／146个原始keyframe，以staticPNG sidecar或真实APNG保留时序，见 [身体参考验收](evidence/yuwen-yi/body-reference-validation.json)。补制40帧动作与原身体／画像已获视觉准入；本批原作54张来源纹理派生8FX／222帧另有新review。资源准入和prepare不代表Unity播放、潜能UI或角色体验完成，实际结果回填角色工作记录。

每次对话收尾清理明确的临时解码目录、编译缓存与临时文件，保留正式产物、证据、源码、独立基线及必要备份：

```powershell
python -X utf8 "E:\AAA MOD\bbee-mod-workbench\scripts\workbench.py" cleanup
```

单人范围内验收；未验证联机。该目录没有初始化 Git，也没有发布、推送或向作者发送内容。
