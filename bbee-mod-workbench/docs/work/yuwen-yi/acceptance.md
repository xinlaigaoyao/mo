# 宇文逸工作记录

## 最新：第二轮实机未通过，桌面操作已停止

用户确认普攻不再截断，但报告选中潜能图标混乱、普攻仅一段，并要求潜能对应武学原版特效。root已实际看到选中图标白绿饱和异常；本轮F9请求被physical Escape停止，未取得新诊断，也未继续输入或替用户关游戏。当前正式游玩run `d66e51203de94e60b8d54bba7f1ac4a3` 仍active，正常退出由正式入口备份和保留进度。新问题、14个原剑招槽的调查线索及下一修复批见 [第二轮实机工单](issues/02-second-playtest.md)。下面离线passed与原生图像QA只覆盖a85候选；新三项尚未修复，角色实机不能写通过。

## 2026-10-16 当前状态：工程通过、正式入口已配置，获准集中实机但尚待验

用户最新直接回复“已解锁，可以实机”，主会话已实际核对桌面unlocked，覆盖此前“人在寝室外／先只离线”的历史停止点。本批工程与保留进度入口完成；当前独立原生图像QA收尾后采用正式play入口集中实机，保留当前进度。6项实机结果仍pending，未提前宣称通过或ZIP已生成。

本批[工程总收据](../../../evidence/yuwen-yi/engineering-acceptance.json)18阶段passed，SHA256为 `fd5bfbabe0cd2303083d2aaf0d704d24cf1557988eefc471c8ad08b41472998c`：141份Python编译、291项回归中289通过／2宿主symlink跳过、31离线原生事件通过；179包全资源严格回读和重复构建逐资源字节一致，安装／更新／撤回／卸载、四owned索引归档通过，工作副本／独立基线／源游戏各2,397文件集合与哈希通过。角色新构建 `_build.json` SHA256为 `a85afaa34a33698b2719e232d37e90ce6f9ce8520fa63c4aea180db58ddf4a49`。这些是离线结果，实际连续输入、潜能详情、特效观感、高难和持久重开仍未验。

用户首测曾报告连按截断、潜能提示缺失、剑气表现不足；root画面与F9确认旧构建ActorId200901／逻辑组ywy，摘要见 [first-role-diagnostic.json](../../../evidence/yuwen-yi/first-role-diagnostic.json)。旧第三段约.08秒回首段、剑气约.16秒自重入及修复批第一次managed声明构建失败均保留为历史，没有改写成通过。根因与可观察合同见 [首测修复清单](issues/01-first-playtest.md)。下一次实机只从下方单一清单开始。

改动原因、实现与交付限制由 [本批交付说明](commit-note-first-playtest-repair.md) 汇总；工程和实机结果仍以本文权威收据为准。

旧launcher已恢复三个代理、移除AppID／owned快捷方式并归档journal。run `67946a5463a5467786d4b548e3a498b5` 已实际执行 `release --keep-progress`：原始备份与当前44文件备份均verified，进度精确保留，存档零写入／恢复，guard归档。正式 `configure --from-preserved-run`已成功，E私有配置显式绑定实际根；[入口配置收据](../../../evidence/yuwen-yi/persistent-entry-configuration.json) SHA256为 `a70c4b53585f8295d72b614041e4215e140a34c56d150a583fa27d0379aea22b`，明确配置阶段未launch。当时副本卸载后2,397文件pristine，首次 `play-yuwen-yi.cmd`将核对并自动安装同一已验候选。不能再次release已归档guard或用旧finish回滚；异常恢复说明由 [PACKAGING.md](../../../scripts/PACKAGING.md) 持有。

## 实机最小清单

六项全部pending，当前已获准在原生图像QA收尾后集中执行。根目录 `play-yuwen-yi.cmd`进入同一已验构建；旧guard保留进度迁移与正式配置已完成，无需重做。原始备份和当前44文件备份保留，公开证据只记摘要／哈希；异常恢复命令统一在 [PACKAGING.md](../../../scripts/PACKAGING.md)。

| 顺序 | 一次集中观察 | 通过要求 |
|---|---|---|
| 1. 正常进入 | 正式入口启动工作副本，选择宇文逸并入战，采本次fresh probe／F9 | Actor200901、skin200901020、实际副本／cwd／保存根匹配；身体、画像与真气／太极势HUD正确 |
| 2. 核心输入 | 单按、快速连按一→二→三→一、预输入、长按蓄势／释放／低气；同时看跳跃、地空方向、冲刺取消和绝式／召唤 | 单按完整且有伸剑峰值；连按保留剑二／三命中，不无新输入自重启；蓄势能放能退、机动不锁死；Dynamic可发绝式并真实扣100，召唤仍可用 |
| 3. 潜能详情 | 完整／简略详情检查12张209001—209012的名称、按钮、条件、数值和大图；获得卡后看4组关联预览／高亮 | 12张均作为出生招式的增强项，不误称解锁；静中反照／百川相生／轻身入无极／圆转续剑只显示真实双卡叠加，触发与取消边界吻合 |
| 4. 特效与清理 | 短剑气、真武波、命中、反击、无极剑阵、蓄势、剑圈、绝式场；左右朝向、多剑气；取消、受击、死亡和退战 | 出手／飞行／命中／消散完整、alpha与比例可读，侧刃正常；旧动作／旧房间视觉不残留，纯视觉层不重复伤害，同屏性能可接受 |
| 5. 普通与高难战斗 | 关闭训练自动恢复及怪物锁血后观察资源／扣血，再打清杂和单首领／高难片段 | 记录难度与设置；真实伤害、资源、盾／化劲／脱身和潜能收益成立；首领免控时核心循环仍强势，不能由训练场回血推断强度 |
| 6. 保存与重开 | 游戏内正常保存、退出；正常finish后重新启动同构建新进程 | 保留退出前实际进度；前后备份可回读，owned启动配置已恢复，角色仍可选／入战；不调用旧guard.finish回滚 |

任一项失败就记录具体动作、设置、构建和证据，保持未验项pending，修完整批再集中复验受影响项。三项打包摘要不能代替上面六项；数值／逐帧／逐卡定位时再查下方详细矩阵和修复清单。

### 本批修复与验收矩阵

| 范围 | 已完成离线证据／合同 | 剩余实机验收 |
|---|---|---|
| 输入与普通连段 | 双入口共用动作资格／输入时间戳，真正起招后消费；六条时间线按原帧重排，剑一／二／三衔接16／20／27tick；141编译、291回归及31离线事件通过 | 单按、连按、无新输入、预输入、长按／释放、低气、方向、地空、跳跃与冲刺取消的实际观察 |
| 潜能原生UI | 12张 `Type=2`、11出生说明／8根、4真实组合；12独立大图与atlas分开；Dynamic映射绝式且保留召唤，表／引用／179包资源闭包通过 | 完整／简略页面、12卡按钮／数值／触发／取消边界、4组合预览和获得高亮；绝式扣100及实际设备提示 |
| 原作FX | 54来源纹理、8FX／222帧；来源／producer／适配manifest绑定，新prepare及原生动画／帧读回完成；不是UE粒子与shader直接运行 | Unity材质／比例、左右朝向、出手／飞行／命中／消散、侧刃／多剑气、取消／受击／死亡／退战清理、清晰度和性能 |
| 艺术准备 | 候选接触表已批准；52semantics／67动画束／293唯一可见帧prepare，67原生时间线／434帧PPtr／293结构读回完成；当前a85构建独立图像／UV／原始tex／tick／世界尺度QA及接触表尚pending，旧62动画QA不套用 | Unity实际动画、材质、比例、UI与流畅性尚待验；原生图像QA是当前唯一离线待验项，完成后再冻结文档 |
| 工程闭包 | 18阶段passed；179包strict／repeat一致；完整事务、四owned索引归档及工作／独立基线／源各2,397hash通过，native metadata／递归闭包绑定 | 离线工程无剩余项；角色实际行为按上方6项清单验收 |
| 旧保护转正式游玩 | release已成功：原始／当前44文件双备份verified，当前进度exact，零存档写入／恢复；旧guard归档、E私有正式配置成功，未launch | 迁移无剩余操作；日常play启动、退出和持久重开仍待实际观察 |
| 正常保存与重开 | `play_launcher.py play/finish`固定副本和已验构建；E盘TEMP／日志；退出只复位owned启动配置，保留角色及当前进度 | 首次实际launch身份／fresh probe；游戏内正常保存、关闭、finish和新进程重开后进度保留；前后备份回读、owned配置恢复与原输入未变 |
| 角色完整体验 | ActorId／skin正式编号不变；原生角色可操作不能替代宇文逸验收 | 同一新构建选择、核心循环、清杂、单首领和高难生存；记录难度、自动恢复／锁血设置与未验分支；角色公开运行收据及去敏证据 |

本批首轮完成141份Python源码编译；素材prepare生成52个semantics／67个动画束／293个唯一可见帧，production manifest SHA256为 `872e2e0bab5061f444488df446670fd2df56388f06be84fd82e571ede5a110c1`；291项回归无失败／错误、2项宿主symlink跳过，即289通过；31离线事件passed。随后complete-build失败，首轮收据保留6个完成阶段，候选未安装。准确缺口为 `nobullet→ywybullet` 未带 `ActionLogicCondition_Script / GamePlay / Assembly-CSharp` 的managed ref_types；角色 `ywy::rg` 已成功，不能误归因到共享TypeTree。

修复从原生 `actor/logicdata/rg` 导入准确声明，不放松校验或删除视觉清理条件。第二轮重新编译141份、prepared全绑定通过；当时framework回归仅在137个覆盖源码SHA一致后复用原291项收据；[31离线事件合同](../../../evidence/yuwen-yi/native-events.json)重跑passed，仍不证明C#集成。之后179包完整／重复构建与事务均通过，新增actor／frame全读回记录在 [yuwen-build.log](../../../evidence/yuwen-build.log)。首轮失败与第二轮结果分别保留。

交付独立审阅又发现视觉审核引用的5张外部PNG未装入候选ZIP，已补打包闭包。补修后重新141份编译、291项回归（93.872秒，289通过／2跳过、无失败／错误）；角色native_art／common／provenance输入、native metadata与全部原生字节未变，递归输入闭包再次核对。权威 [delivery-closure-acceptance.json](../../../evidence/yuwen-yi/delivery-closure-acceptance.json) 明确 `native_builds_rerun=false`，没有宣称再次重建179包。

最终绑定：`_build.json` 为 `a85afaa34a33698b2719e232d37e90ce6f9ce8520fa63c4aea180db58ddf4a49`，`_verification.json` 为 `ee23860c5e3927d10a0fd658d7689ec81b9160e9dc3730ee8f37eab64e9b6f23`，profile为 `cd7763272595eb7e9f9f6cb4693f9acef2c336e7baa1f1b20482f611fd5baed8`。旧133／270／19／146不冒写为本批结果。独立原生图像QA完成后，剩余仅实际输入／UI／视觉／高难／保存重开；候选包将按当前build命名为 `delivery/bbee-yuwen-yi-local-a85afaa34a33698b.zip`及同名 `.receipt.json`，产物存在与ZIP回读由打包后实际收据确认。

新完整视觉审核：[complete-art-visual-review-first-playtest-repair.json](../../../evidence/yuwen-yi/complete-art-visual-review-first-playtest-repair.json)，SHA256 `c6cf731e8e3fdf6d85c10add641fe476a06781d06de482018c6bb456af6df409`。它批准准确候选进入prepare/build，明确保留Unity播放、战斗、UI、持久进度未验边界。旧prepared55文件已完整哈希归档至 [prepared-art-c7655a…](../../../evidence/yuwen-yi/history/prepared-art-c7655acab1f753a2b5481cb4a4152d8ca83223f1b96a24be40d95d00b696d753.json)，仅移出本任务owned `assets/prepared`后执行本批统一重备；旧工程收据与原生QA已经按哈希保留为历史，没有改写成新批结果。

### 历史快照：2026-10-15 15:44 UTC

以下入战前叙述、旧工程表格与旧哈希是该时点的历史范围，当前状态以上方矩阵及修复清单为准。历史中 `launcher.restore → guard.finish` 是原可回滚测试流程，已被当前“保留进度release后转正式play”的要求替代，不能作为本次收尾命令。

run `67946a5463a5467786d4b548e3a498b5` 的工作副本进程 `117464` 已实际启动，fresh probe 四项均通过。用户接手带宇文逸入战后，下一次只读画面请求再次收到物理 Esc 停止；本轮不再使用桌面工具，角色入战后的身份、战斗与 F9 未观察，仍为 pending。15:44 UTC 核对游戏进程仍在运行，因此 guard／launcher／补丁安装保持保护状态，尚未恢复存档或卸载。任务临时目录已清理；私有备份和必要恢复日志保留。恢复必须先正常关闭游戏，再 launcher.restore → guard.finish → uninstall → 四索引私有归档及完整工作副本核对。

独立交付检查确认还缺正式游玩入口：现有 runtime_guard.finish 会回滚验收前存档，不能用作玩家保留进度的常规流程。后续需补齐工作副本专用、与测试 guard 互斥的持久进度启动／退出流程和中文说明，再集中验证退出重开保留进度。原始 Steam 安装和原 ZIP 仍为只读输入，不能把正式入口指向源安装来绕开该缺口。

2026-10-15 起的角色批，本次接续核对状态：**工程18阶段已通过，146包重复构建一致、事务链和2,397文件精确恢复已完成；本轮游戏已启动，用户正在帮助带宇文逸入战，角色选择／战斗／重开仍pending**。表主键、潜能 atlas 容量和 signed PathID 回读的已知构建阻塞已修复。先前最终恢复文件集合因四个本任务创建的公开 pristine index 副本而失败，现已完成独立哈希绑定、私有归档和限定白名单删除，保留原失败与续验历史。先前非角色实机记录不能替代本轮角色结果。

用户目标和就绪门槛由 [spec.md](spec.md) 持有。本文记录实际发生的结果；研究、数据读取、资源预览、构建和实机分别记录。

| 历史层次 | 当时证据 | 当时状态／覆盖边界 |
|---|---|---|
| 基础设施机械验收 | 最新完整批编译 120 份源码、265 项回归中 263 通过／2 项宿主 symlink 跳过；全部 15 工程阶段通过，29 包全回读、双构建一致、安装／更新／撤回／卸载通过 | 当前非角色平台 engineering-passed；不能由此宣称新增角色资源闭包通过 |
| 历史非角色真实运行 | Inspector 0.4.1 新 F9 报告：订阅成功 1 次、fx+ 118 次、warnings 0；同构建第二进程重开到主菜单，fresh probe 的加载／保存路径／cwd／is_playing 均满足 | 非角色 readiness runtime-passed；历史run 9a95cfaa547b4837868243de38886267 已结束并精确恢复，该历史run的guard／launcher／AppID／shortcut／安装记录无残留，工作与源各 2,397 项哈希通过 |
| 《逸剑》来源 | 基础 pak 三索引校验；9 个成员共 10,050,762 字节导出回读；完整解析 835 行 NPC 映射、1506 文本项、2 张 145×145 RGBA 头像 | 原参考 28 项集中检查通过；追加画像批选择 15 个成员、6 张原图、4586 条 NPC 本地中文文本，Hero 与 Hero_WuDang 的名字均为宇文逸，未假称解码 NPCs 主表 |
| 身体参考独立批 | 修复 Pillow 合并相同视觉帧导致静态 PNG 的合法情况后，36 个 flipbook、142 个 sprite、11 张 atlas、146 个原始 keyframe；30 个 APNG 和 6 个静态 PNG，保留原 FrameRun/FPS 时间线 | 修复批 21 组验证通过，像素裁切、枢轴、时间及哈希已回读；旧失败证据保留。无原受击映射且倒地引用为空，缺失动作另行补制 |
| 补制动作 | 两张派生像素画源图，各用明确站立帧标定一次整体缩放，40 帧覆盖受击、空受击、翻滚、倒地、起身、死亡、蹲下、蓄势、打坐、抱拳 | 44 个正式文件哈希回读通过；root 逐格视觉检查后批准进入整批准备。批准不等于 Unity 播放、动作流畅或实机完成 |
| 原作武学与改编 | 原作中文技能原文、资源来源与 D 级横版改编源码已对照；拳剑联动、梯云纵、太极势、化劲及绝式已实现 | 原生构建通过；实际命中、取消、难度体验与强度仍待实机 |
| 正式编号与角色制作 | ActorId 200901／skin Id 200901020 已完成 stock 原始表和其他 Mod/shared 声明／生成 JSON 全查重并正式分配；contract 和 id-ownership 保留来源清单 | 角色源码、47 semantic clips／62 原生动画／95 可见网格帧、86 原生角色动作和 12 潜能已制作并构建。自动授予、HUD、资源／技能表现及新角色存档行为仍需同构建实机验收 |
| 角色历史失败批 | 首轮表主键校验失败；后续曾遇到 donor100101 仅14槽和回读器错误拒绝负 signed PathID | 原失败收据与日志按哈希保留。SkillDamage 原生键 `(ActorId,Action)`、HeroPortraitOffsetConfigUI 原生键 `(Id,Key)` 已修复；atlas 换为16独立槽103401，实际外部CAB与Mesh对象解析替代错误的正数ID假设 |
| 角色首测前集中构建 | 133 份 Python 编译、17 表原生合同审计、270 回归中268通过／2宿主symlink跳过、19离线角色事件场景通过；146包、474对象、673 local PPtr与584 external PPtr严格回读通过 | 工程总收据18阶段passed：完整角色构建与146包重复构建字节一致，安装／更新／撤回角色／卸载和工作副本2,397文件精确恢复、独立基线／原输入未变均通过。离线事件不等于C#运行命中验证 |
| 原生艺术回读与观察 | 从真实built PPtr、Mesh、GUID texture family和BC7色页回读62动画、230帧引用、95唯一Mesh图、3色页；原生atlas16图标、原生UI12纹理完整 | QA逐像素／原生60 Hz时间／哈希回读通过。root已观察全部8页动画接触表及UI／图标，确认实际身体、补制姿势和独立弹体图像存在；这是原生资源视觉核验，未模拟Unity材质光照／描边，不能据此宣称角色动作实机通过 |
| 首测入战前运行快照 | run `67946a5463a5467786d4b548e3a498b5`，PID117464，实际Sky游戏窗口9112546；root当时fresh probe摘要为loaded／save_root_matches／working_directory_matches／is_playing全true | 当时游戏已启动、等待用户带场。随后实际入战和体验失败见本文顶部；旧快照不能表示当前进程仍在或角色尚未入战 |

首测使用的旧角色 `_build.json` SHA256 为 `4a11c43b047db4b44dd068da24b5886ff5bdfb41aa9caccb617f241a4e9d62ff`，`_verification.json` 为 `d153594aeeaf0b41e3a20e0674853db55a1689f0a1ab3ee6d879483c418e9d26`。当时角色 profile SHA 与已验收据一致，descriptor SHA 与该构建一致；本批新源码／素材必须重新建立完整闭包，不能只凭本段历史哈希放行。

旧146包重复构建临时目录已按AGENTS清理，其收据和绑定日志已由本批工程总收据的 `previous_attempt` 按哈希归档。门禁可对照通过收据中的逐资源哈希和对应发布字节，不要求合法清理的临时full-repeat目录继续存在，但不能因此复用到已改输入的新批。恢复续验保留原构建／事务阶段再追加收尾阶段，不得抹掉失败或虚构重跑。

知识结论与参考来源保存在 research 及项目知识文档；Basic Memory 只保存可检索结论和权威路径。后续集中测试与实际产物使用独立 evidence 记录，不覆盖上阶段失败历史。

平台权威证据：[final-acceptance.json](../../../evidence/final-acceptance.json)、[inspector-fixed-runtime.json](../../../evidence/inspector-fixed-runtime.json)、[runtime-acceptance.json](../../../evidence/runtime-acceptance.json)、[runtime-final-restoration.json](../../../evidence/runtime-final-restoration.json)。之前 run 502113b3109a421e96504b4edacdd3a2 观察过试用场、移动／跳跃／攻击／冲刺和重开 fresh probe，但第二 F9 被人工 Escape 中断；当时 effect hook 缺口随后由 0.4.1 批补齐，保留 [历史重开记录](../../../evidence/runtime-reopen-observation.json)，不与最新证据混淆。

参考验收：[reference-validation.json](../../../evidence/yuwen-yi/reference-validation.json)；身体修复批：[body-reference-validation.json](../../../evidence/yuwen-yi/body-reference-validation.json)；首批失败历史：[body-reference-collection-failed-v1.json](../../../evidence/yuwen-yi/body-reference-collection-failed-v1.json)；补制机械及视觉结果：[authored-poses-validation.json](../../../evidence/yuwen-yi/authored-poses-validation.json)、[authored-poses-visual-review.json](../../../evidence/yuwen-yi/authored-poses-visual-review.json)。正式编号：[character-contract.json](../../../ZenithTerminal/Launcher/mods/char-yuwen-yi/character-contract.json)、[id-ownership.json](../../../ZenithTerminal/Launcher/mods/char-yuwen-yi/gen/id-ownership.json)。编号全查重是静态证据，不是角色行为测试；先前研究中的候选表由本次正式分配结果替代。

首测前角色集中证据：[旧18阶段工程总收据](../../../evidence/yuwen-yi/history/d54a98e126a57927a861bcf721eb735e14a5add23ab926fea1904fcef731d620.json)、[旧19场景原生事件合同](../../../evidence/yuwen-yi/history/d54a98e126a57927a861bcf721eb735e14a5add23ab926fea1904fcef731d620/native-events.json)、[原生艺术回读](../../../evidence/yuwen-yi/native-art-review/build-4a11c43b047db4b4/native-review.json)、[原生图标接触表](../../../evidence/yuwen-yi/native-art-review/build-4a11c43b047db4b4/contact-native-icons.png)、[原生UI接触表](../../../evidence/yuwen-yi/native-art-review/build-4a11c43b047db4b4/contact-native-ui.png)。旧原生QA保留native tick sidecar及全部62个PNG/APNG预览。横banner人物偏小和PDA留白／偏下是当时构图观察，资源存在且透明正常；是否影响对应游戏界面仍须实机判断，未由旧图宣称本批UI通过。

完整角色批的集中入口为 `scripts/yuwen_acceptance.py --visual-review <三批绑定的完整视觉审阅JSON>`；profile 为 `profiles/yuwen-yi.json`。只有玩法、资产与合同全部冻结且视觉审阅批准后执行；结果另存 `evidence/yuwen-yi/engineering-acceptance.json`，不会覆盖平台 `final-acceptance.json`。该入口覆盖编译、准备、回归、全构建、双构建一致、安装、更新、撤回角色、卸载和输入恢复；选择角色、技能效果、高难体验与重开仍须同构建实机记录。代码修复重验可显式 `--reuse-prepared-art`，它完整核对 producer、合同、帧像素、时间线与 UI 哈希，拒绝漂移，不能跳过艺术输入验证；旧失败收据与日志先按哈希归档。

首测前最后恢复采用 `--finish-restoration` 专门入口续验，保留原构建／事务阶段和历史绑定，旧工程总收据为18阶段passed。历史run `e590ad1585024475a35c0aea7df048a7`在启动前遭物理Esc中断并完整恢复，未获角色战斗证据；之后run `67946a5463a5467786d4b548e3a498b5`已经实际入战并发现本文顶部缺陷。“等待带场／尚未入战”只描述旧快照，不能用作当前结论。正式角色ZIP尚未交付；发布门禁要求本批工程总收据passed、相同profile、当前native exact文件／metadata及递归输入闭包一致。没有相同新构建的角色实机收据时状态保持pending，不能借用此前Inspector平台实机结果。

## 角色实机公开收据合同（待采集）

当前已创建 [character-runtime-acceptance.json](../../../evidence/yuwen-yi/character-runtime-acceptance.json)，精确绑定新build／profile且明确全部pending、未启动游戏。以下为真实记录的最小字段摘录，不是实机通过记录：

```json
{
  "status": "pending",
  "actor_id": 200901,
  "build_record_sha256": "a85afaa34a33698b2719e232d37e90ce6f9ce8520fa63c4aea180db58ddf4a49",
  "profile_sha256": "cd7763272595eb7e9f9f6cb4693f9acef2c336e7baa1f1b20482f611fd5baed8",
  "checks": {
    "character_selection": "pending",
    "combat": "pending",
    "reopen": "pending"
  }
}
```

`status`接受pending／failed／passed；三个check采用明确字符串状态，不能写布尔值。两项SHA必须从实际启动的当前`patch_out/_build.json`和`profiles/yuwen-yi.json`取值，换构建就重新绑定。passed要求三个check都为passed；泛用平台收据缺少actor与这两项绑定会被拒绝。打包器验证的是这些声明及绑定，不自动判读截图、诊断报告或恢复证据；缺失收据默认pending，显式failed／pending会作为发布状态保留，不能据此称已完成角色实机验收。

人工判定的最小观察范围：character_selection确认副本内宇文逸200901／skin200901020实际可选且身体、画像正确；combat确认实际控制该角色进行移动／跳跃／冲刺、剑拳核心动作、轻功／绝式及独立弹体，并观察命中与资源HUD；reopen要求关闭后新进程、同构建、fresh probe再次确认副本路径／cwd及角色可选或可进入战斗。只看到窗口或F9报告不足以替代这三项。受击／倒地／恢复、高难强度、潜能分支若未实际覆盖，另列未验范围，不能由三项摘要外推全部玩法通过。

公开收据建议附`evidence`：每项check对应去敏的截图或观察记录相对路径、SHA256及简短结论，并附`run_id`、进程身份与fresh nonce比较布尔值。原始F9日志、实际存档根、账号路径与备份内容保留private；公开材料只保留去敏摘要或哈希。`runtime_guard`四个通用标记process_started／window_observed／f9_triggered／f9_report_observed不能自动转成角色check。3项只是打包器最小摘要，完整体验仍须上方矩阵。当前要求单独引用保留进度release、正式play前后备份／退出／重开及启动配置恢复证据，不能以测试存档回滚作为正常保存通过。

本批结果回填顶部“本批修复与验收矩阵”，保留旧工程与首测失败历史；只把实际观察、覆盖范围与权威收据链接写入知识文档“角色级运行证据”，不提前写完整工程或实机成功。

旧黑图当时没有锁屏前态，不认定代理必为原因；旧 Node cwd 不能作为目标 cwd。新探针比较游戏内 managed cwd。所有运行保护、启动准备和恢复必须使用同一固定便携 Python 3.14.8；系统 3.11.9 的 st_dev 差异已触发拒绝，见 [解释器身份记录](../../../evidence/runtime-interpreter-identity.json)，规范命令由工作台 README 持有。
## 2026-10-15 15:29 UTC 接续核对

`evidence/yuwen-yi/engineering-acceptance.json` 已实际通过全部 18 个阶段。收尾集中编译 133 个 Python 源文件，并在校验与私有归档四份安装索引备份后，核对工作副本完整文件集及 2397 个文件哈希；独立基线和原始 Steam 目录也各通过 2397 个文件哈希核对。270 项回归、19 项事件、双份 146 资源构建与安装事务使用已绑定的原始通过证据，不宣称重新运行。

同一构建已重新安装准备角色实机验收，保存保护 run_id 为 `e590ad1585024475a35c0aea7df048a7`。首次入口操作即被物理 Esc 中断，因此游戏没有启动，角色实机三项仍待验。已恢复启动器隔离、删除自有 AppID 和快捷方式，guard 证实存档未变化且精确恢复，卸载已提交。四份新产生的索引备份也再次校验、私有归档并移除，工作副本完整 2397 文件集和哈希通过。

本次中断恢复收据：`evidence/yuwen-yi/runtime-interrupted-e590ad1585024475a35c0aea7df048a7/engineering-acceptance.json`。下一步为同构建的宇文逸角色选择、战斗、重开实机验收；当前未生成最终交付 ZIP。

