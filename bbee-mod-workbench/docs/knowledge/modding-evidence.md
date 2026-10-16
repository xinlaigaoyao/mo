# BBEE 与《逸剑》Mod 研究知识

核对日期：2026-10-16。最新用户直接回复“已解锁，可以实机”，主会话实际核对unlocked，覆盖先前只离线历史停点。工程与保留进度入口已完成，原生图像QA收尾后按 [唯一实机清单](../work/yuwen-yi/acceptance.md#实机最小清单) 集中验收，结果仍pending。本文维护可复用结论与证据指针；原始存档、账号目录和完整日志不进入知识库。

## 运行证据与工作目录

`nodeRepl.cwd` 是工具的目录，不能证明目标游戏的进程 cwd。[Steamworks API](https://partner.steamgames.com/doc/sdk/api#initialization_and_shutdown)明确从目标当前工作目录寻找 `steam_appid.txt`；其重启函数可能退出当前副本并启动 Steam 库里的安装版本。因此副本 EXE 被调用、出现一个游戏窗口、工具目录存在 AppID 文件，均不能证明副本 Mod 已加载。

本地静态信息已找到 `SteamManager.InitSingleton` 的重启调用，且主 EXE 的已观察 PE 导入仅含 UnityPlayer 与 KERNEL32；目前证据不支持直接断言这是 Steam DRM wrapper。诊断先核官方 API 和真实运行位置，不从重定向现象反推不可更改的原因。

[Windows Shell link](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-ishelllinkw-setworkingdirectory)支持设置 WorkingDirectory。测试用 `runtime_launcher.py prepare` 只创建有明确起始位置的快捷方式、临时隔离本副本已知代理并写入 owned AppID 提示，不自动执行游戏，也不修改原 Steam 目录或其配置。真实运行位置由当前 nonce 的游戏内 managed `System.Environment.CurrentDirectory` 比较布尔值证明，快捷方式配置读回只是准备证据。新的正式 `play_launcher.py play` 另以固定EXE、cwd和E盘TEMP／日志启动该副本；两种入口的存档语义见下文，不能混用。

Unity 的窗口模式和尺寸参数按[当前版本 Player CLI](https://docs.unity3d.com/2022.3/Documentation/Manual/PlayerCommandLineArguments.html)设置；窗口化用于可观察交互，不以修改渲染参数替代实机通过。

运行保护与启动准备必须使用同一固定便携 Python。已在本机核实：系统 3.11.9 与便携 3.14.8 对同一目录报告的 inode 一致、st_dev 不一致；混用会被目录身份门禁拒绝。正确处理是使用同一运行时，不删除 device 比较或手改保护 journal。证据见 `evidence/runtime-interpreter-identity.json`。

## 黑图与锁屏不能混为游戏故障

本轮资源管理器也出现全黑截图。对本进程会话执行只读 WTSInfoEx 查询，确认 SessionFlags=0、session 匹配，证明当时桌面锁定。[微软字段定义](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w)规定现代 Windows 的 0 为 locked、1 为 unlocked；Win7/Server2008R2 有已知反转，不能跨版本盲用。

因此仅凭历史黑色截图，不能确定是代理、Unity渲染或游戏自身卡死；窗口输入超时也不证明游戏逻辑挂起。旧失败记录保留并补充证据边界。锁屏时停止桌面输入，继续不依赖桌面的工作，何时恢复听取用户当前安排；恢复UI前重新核实会话，不把旧回复替代实际检查。

解锁并实际复核 WTS 后，本轮明确起始目录的副本已显示主菜单和基地，当前轮次的 managed 探针确认 loaded、save_root_matches、working_directory_matches、is_playing 均为 true。启动初段仍短暂显示黑色，但随后正常进入画面；这只能证明本次运行恢复，不能倒推出全部历史黑图的原因。F9 必须在正常更新的 BattleUI 中验证，基地/主菜单的脚本探针不能替代战斗诊断报告。

## 模块循环依赖与诊断订阅

真实 F9 报告发现 inspector 的 effect hook 失败。当前 build 的 VFXManager 及事件绑定仍存在，根因是 `Core/Util → BattleJs → BattleUI → Core/Util` 的加载环：模块求值时把尚为 undefined 的 `Util_1.U` 缓存在局部 U，此后不会随导出初始化更新；同时旧逻辑在订阅成功前就标记 hooked，导致永久不重试。

0.4.1 改为调用时动态读取 U、成功订阅后才置 hooked，并以一秒间隔重试；相同原因不逐帧刷警告，原因变化及恢复前历史继续保留。统一回归覆盖延迟导出、订阅异常和延迟 singleton；实机报告确认 1 次成功订阅、118 个特效生成事件、0 个警告，见 `evidence/inspector-fixed-runtime.json`。这是实际捕获事件的证据；不以“报错消失”代替跟踪成功，也不据原生角色证明新增角色全部分支已通过。

## 资源引用与克隆合同

更换 external CAB 不会自动把旧 donor 的 PathID 改成新 donor 的对象 ID。缓存键至少需要区分实际 donor、目标身份和输入内容；只用目标短名合并不同来源会生成表面可读、实际悬空的资源。

本项目默认旧角色全集的 1,154 包、17,857 对象均可严格读取，仍有 710 个悬空引用，涉及 126 个 Ruby effect 包。私有生成器把两种 donor 纹理复用同一目标，以及替换 mesh 后遗漏闲置 Renderer 和 AssetBundle.m_PreloadTable，是可复用的失败样例。仅禁用 ParticleSystem 没有消除 Renderer 的引用；预加载表也必须参与一致的映射。详细指针、生产位置和源码哈希见 `evidence/resource-reference-diagnostic.json`，不靠关闭 PPtr 检查放行。

“全部对象能读”与“所有引用有效”是不同验收层。新 manifest 名称、依赖、GUID、内部 PathID、managed RID、表/JS payload 以及最终安装字节集合分别核对；某个 profile 没有 external 实例时，明确记录 0，不能写成已实测外部引用的正向覆盖。

宇文逸首轮完整构建又暴露表身份合同缺口：`SkillDamage.HitTimes` 是普通浮点伤害字段，当前 build 的 `Xlsx.XlsxLoader_SkillDamage` 用 `Dictionary<ValueTuple<uint,string>,SkillDamage>`，`Get(uint actorId,string action)`，真实键为 `(ActorId,Action)`。不得改 HitTimes 为虚假唯一数值或放宽真实重复检查来换取构建通过。审查也确认画像 `(Id,Key)`、弹体 `(Id,StartAction)`、天赋 `(TalentId,Quality)` 等复合键；默认值必须依据 protobuf，省略 StartAction 等价空字符串，省略 Trigger Lvl 等价0。另一方面 SkillActivate、SkillAttr、SkillFromTeacher 原生只有 List；composer 用于定位编辑的合成身份不能冒称原生唯一键，合法多行仍须保留和显式 `$match`。静态名称引用闭合不能证明这些索引合同正确。

首测修复批完整构建又暴露每个资源自己的managed类型闭包：角色 `ywy::rg`成功，不代表从 `nobullet`克隆的 `ywybullet`带齐类型。旧模板只有GroundCheck／Hit／Trigger，新增视觉清理条件用 `ActionLogicCondition_Script`时，UnityPy找不到GamePlay／Assembly-CSharp声明。修复从准确原生 `actor/logicdata/rg`导入ref_types，再严格序列化／回读，第二轮179包通过；首轮失败候选未安装且历史保留。不能把actor成功、JS名称存在或共享TypeTree可用冒作弹体闭包，也不能删除清理条件规避失败。

结构、图像与Unity表现仍是不同层次：67条原生时间线、434帧PPtr和293帧结构读回通过，不能自动替代原生纹理像素／UV／tick／世界尺度的独立QA；新构建须绑定新检查，不能套用旧62动画接触表。本批正在补当前a85的独立图像QA，之后实际材质、场景可读性、动作流畅性与性能仍须实机。

## 《逸剑》参考提取

本地参考目录带有 UE4SS 和两个覆盖 pak；基础包与覆盖来源分开，文件清单不是 Steam depot 原版认证。已核主 pak 为 v11、UE4.26 分支、Zlib，无索引/成员加密标记；包内成员和三索引哈希已核对。具体补丁版本、图像身份、技能效果和动画时序不能单凭路径名确认。

白名单读取工具固定基础包路径和 SHA256，逐成员检查索引、header、压缩流、长度、存储 SHA1 与导出回读 SHA256；拒绝路径越界、链接、未知压缩和无上限导出。一次选择性提取已取得 9 个原始成员，10,050,762 字节，正式来源 manifest 在 `references/wandering-sword/20261015T122045Z-a69abc003aec/manifest.json`。原始 uasset/uexp/locres 已导出不等于图像、音频或技能表已转换成功。

初批解码器完整读取 835 行带标签 NPCResources、1506 条 locres v3 文本项，并生成两张 145×145 RGBA 头像，PNG 回读像素与 BGRA 转换结果一致。初批看图只能确认同一黑发青年、金色/蓝色衣领，不能把小头像称作完整立绘。初批输出见 `references/wandering-sword/20261015T124534Z-a62a5e5c879d/manifest.json`；身体和身份随后由以下独立批补充。

身体修复批已完整读取两行 36 个 flipbook、142 个 sprite、11 张 atlas 和 146 个原始 keyframe，验证原 BGRA 像素裁切、PPU/顶点推导的脚底枢轴及 FrameRun/FPS。Pillow 会把相同视觉帧合并，最终只有一个视觉状态时合法输出普通 PNG，没有 APNG duration；此时必须以原始时间 sidecar 保留时长，不能伪造不同帧或直接丢弃时序验证。多状态 APNG 仍逐帧核像素与时长。首批失败和修复批分别保留，见 `evidence/yuwen-yi/body-reference-validation.json`。

追加画像批从 NPCResources 的明确 TeamImage/DlgImage/FightImage 引用读取 6 张原图和 NPC 中文 locres。Hero.Id=0 与 Hero_WuDang.Id=1 对应 NPCs namespace 的 0_Name/1_Name 均为宇文逸；这是直接本地文本对照，没有假称解码 NPCs 主表。原 TeamImage 900×835 是带底部渐隐的半身图。原图 alpha0 区域大量 RGB smear 是纹理隐藏颜色，不能仅看忽略 alpha 的预览就误判抠图破损；正确合成后核图，并使用预乘 alpha 的缩放路径。证据 `evidence/yuwen-yi/portrait-reference-validation.json` 与 `portrait-composite-review.png`。

俯视原作攻击帧不自动满足 BBEE 受击、倒地及空地衔接。已明确原身体没有受击映射、倒地引用为空，新增 40 帧补制姿势，分别标注派生创作来源。不同源图分辨率使用每张图一次站立标定的统一缩放，禁止把倒地、蹲下的每帧都拉成站立高度；保留原 alpha、统一脚底锚点，并绑定源图、脚本、裁切几何和输出哈希。root 接触表视觉批准仅准入整合，不证明实际动画流畅或 Unity 行为，见 `evidence/yuwen-yi/complete-art-visual-review.json`。

## 武学设计证据

原作官方成就可确认太极拳、太极剑、太极神功、云相太极和自创流云太极；详细招式效果还需社区资料与本地资源交叉。参考来源和版本差异见 `docs/work/yuwen-yi/research/combat-references.md`，不把社区解析异常值或自动生成攻略当作原作数据。

用户要求爽快、强势、高难可玩。当前改编以流云太极拳剑联动、梯云纵、真武剑气为主；出生完整循环与潜能增强已有源码和旧构建，实际强度仍须实测。知识库区分源码配置、离线回调和C#／Unity中的真实表现，不把设计数值、无敌窗或纸面资源循环自动认作运行通过。

## 角色级运行证据

2026-10-16核对：宇文逸首测已实际入战，root画面与F9确认ActorId200901／逻辑组ywy，体验缺陷及旧diagnostic保留。修复批 [工程总收据](../../evidence/yuwen-yi/engineering-acceptance.json)18阶段passed，179包strict／repeat及完整事务、工作／基线／源各2,397hash通过，新build为a85afaa34a33698b…；141编译／291回归（289通过2跳过）／31离线事件有实际记录，仍不证明C#调度和Unity实际玩法。当前 [角色实机收据](../../evidence/yuwen-yi/character-runtime-acceptance.json)精确绑定新build／profile，选择／战斗／重开全pending。根因见 [首测修复清单](../work/yuwen-yi/issues/01-first-playtest.md)，权威范围见 [角色工作记录](../work/yuwen-yi/acceptance.md)；其他角色或旧静态资源结果不能替代本角色验收。

打包器的角色运行摘要必须绑定ActorId200901、实际`patch_out/_build.json` SHA与角色profile SHA；passed要求character_selection／combat／reopen三个具名状态均passed。它只验证声明及绑定，不自动判读图像或报告。平台`runtime_guard`的启动／窗口／F9通用标记不是角色动作验收，先前Inspector通过不能证明新角色已可玩。未来写入时记录实际覆盖与未验分支，保留选择／战斗／新进程重开和恢复的独立证据，不把离线19事件或原生艺术接触表升级为Unity运行结论。

知识库只保存去敏结论与公开证据路径／哈希，实际存档根、账号目录、原始日志和恢复备份留private。用户暂停、只离线及随后允许实机都是有时间范围的要求，当前执行应按最新直接回复及实际会话检查，不能把历史授权、锁屏或停止点当成永久状态。旧guard.finish会回滚试玩存档，不能默默解释成正常保存入口。

### 连段入口与输入复用的实际失败

报告`7face148038baf69625c1595ea83cab953a6133b7fa5ca3bac46ed795bc7f0f1`记录第三段→首段约.080–.084秒，而第三段标称.6秒且命中窗在第10–19帧；剑气也在约.16秒自重入。相邻两例重启之间没有新对应输入。旧源码有原生技能链自动入口与ActionSwitch双路径，统一all静默.08、重复Start_1等配置与表现对应。因此动画资源完整、单击播放正常、离线命中回调通过均不能证明连续输入正确。

当前修复让两入口共用 `YwyGate` 的实际动作时间／输入时间戳资格，`YwyStart` 在真正起招后消费该次输入；原生 `SetPressInputSatisfied` 与物理 `Pressing` 是不同状态，不能通过假释放解决长按重入。跳跃独立入口、地冲预算、空冲与脱身须保留各自资格。源图也需与命中窗共同审查：六张原始剑姿势0／1／2在蓄力，3／4／5才伸剑；旧首剑只取前三张，单纯延长播放仍不会出现峰值。本批按原图显式60 Hz曝光，末帧是伸剑保持，不冒作新绘收剑帧。上述是已实现合同，Unity连续输入仍待同构建实机；本批离线31场景明确不证明C#集成。

### 潜能展示是数据图，不只是文案

原生 `BaseActorPotentialConf.RelationId → ActorActionConf`，`Inherit/Type` 决定招式根和增强关系，`ActorActionInput/Desc/Label` 负责提示；`PotentialComboConf.Potentials + RelationId` 决定关联条件及获得状态，真实键为 `(Id,)`。原生完整页直接取根的首个关联潜能，因此不能留下无潜能／图标的可见根。增强项 `Type=2` 不直接绘制Input，按钮须同时进入Label；详情大图另用 `UI/Texture/IconPotential/Potential_<pid>`，小图atlas存在不能证明详情纹理齐全。消费代码见原始 `PotentialUtil.js`、`WidgetActionsDesc.js`、`DataActorAction.js`、`PotentialCombosBase.js`，本批生成合同由角色 `potential_content.py` 持有。

首测12独立根／空按钮／无关联表是历史失败。本批12卡改为 `Type=2` 增强项，接到11项出生说明组织的8个根，补真实条件与取消边界、12张独立大图及4组既有叠加：静中反照、百川相生、轻身入无极、圆转续剑。组合只描述已实现双卡叠加，不增加奖励回调或假解锁；具体数值由修复合同持有。源码和数据闭包须与原生UI显示、实际卡效果分层验收。

绝式已完成原生静态映射追踪：存在 `InputCmd.Ultra=4` 不等于存在名为Ultra的Rewired动作；`ProcessInput`解析到Dynamic后，`UpdateDynamicCmdBinding`先默认Summon，再由角色虚拟按钮数据覆盖。为200901/style0新增无潜能条件的单命令4入口，才能把实际Dynamic键映射Ultra；提示应为 `<action=Dynamic>`，原召唤战术仍用 `<action=Summon>`。原生Slot3扣100与真实设备按键／图标须分别实测，不能只验证按钮字符串存在。

### 原版效果来源与跨引擎重建分开

首测 `body_source.effect_frames` 的ImageDraw八帧几何图不是逸剑原版VFX，旧资源QA不能冒称原作移植通过。GA实际import确认真武剑气指向waveSlash1／flare1／flareInpact，流云太极剑拳指向xuli2／xuli4／flashImpact，心法指向xuli1。本批有界读取54张原版纹理并保留参考manifest，8种派生FX共222帧，`body_source.py`改为消费哈希绑定的原作素材候选。来源、实际使用子集与适配详见 [original-vfx.md](../work/yuwen-yi/research/original-vfx.md)；54张收集纹理不等于每种效果都使用全部纹理。

UE粒子、网格与材质程序不能直接作为Unity资源运行。本批原纹理裁片／SubUV层经过横版投影、旋转缩放、RGB遮罩转alpha、染色、软边与叠层；这些是明确改编，不称无损还原。保留像素来源和发射器参数证据，同时绑定枢轴、世界比例及60 Hz时序。最终生产帧画布上限96像素，世界尺寸单独记录，不能把缩画布误当缩命中盒。原生材质混合、场景可读性与性能须实机判断，接触表视觉批准仅准入prepare/build。

纯视觉跟随／命中层不额外制造伤害；有限弹体与外观实例分开。视觉存活需绑定施法者、战场／房间和原动作实例；循环蓄势正常TimeEnd可延续，Interrupt、受击、死亡、退战或旧实例失效必须清理，不能只按动作名判断是否同一招。本批先统一原生回读，再实际验证出手、飞行、命中和消散；不能根据PNG数量宣布特效质量合格。

### 可还原测试与正常保存是不同合同

测试 `runtime_guard.finish` 会恢复测试前存档。本批新增 `release --keep-progress` 是显式替代退出：游戏关闭，owned launcher仅在active时先恢复，已经复位则跳过重复restore；核验原始备份和当前进度新备份，绑定run／根身份／文件集合／manifest哈希后归档guard，不执行存档恢复。该收据只证明进度保留，不自动宣称实机通过；保留当前进度时不能在release失败后退回旧finish。

正式 `play_launcher.py`要求显式根或已成功release的run，测试／游玩共享互斥锁；启动前核对相同profile、native完整集合、metadata及源码闭包，前后分别备份，正常finish只恢复自有代理／AppID／快捷方式并保留角色和进度。异常留下journal，未知公开文件拒绝覆盖；COM中断但未登记哈希的私有staged快捷方式可隔离保留，不能扩展为删除未知公开文件。本批旧run已真实release：原备份和当前44文件备份verified，进度exact、存档零写入／恢复，guard归档且正式配置成功；[公开配置收据](../../evidence/yuwen-yi/persistent-entry-configuration.json)明确配置时未launch，不能据此宣称实际保存重开通过。

仅把快捷方式放在E盘不会改变游戏TEMP或Player.log。正式play显式给子进程E盘TEMP/TMP及日志路径，账号根配置／存档备份在private；正式游戏存档仍在明确配置的真实位置，不冒称已迁移。以上实现与失败边界已进入本批集中回归，正常保存、退出与新进程重开仍待实机。规范命令由 [PACKAGING.md](../../scripts/PACKAGING.md) 持有。

### 交付审核引用也必须闭包

审核JSON存在，不代表它引用的图片已装入ZIP。独立审阅发现5张外部PNG漏装后，打包器补齐引用／SHA绑定，并重新141编译、291回归（93.872秒、无失败／错误、2宿主跳过）。角色native_art／common／provenance及全部原生字节未变，metadata和递归输入闭包再次验证；[交付闭包收据](../../evidence/yuwen-yi/delivery-closure-acceptance.json)明确未重建native，不能把这次验证写成再次完成179包构建。交付文件与ZIP回读仍以实际打包收据为准，文档预告名字不证明产物已存在。

## 继续学习与验证

### Tryout训练设置会改变资源与生命试验条件

本机build25627491的原始脚本 [BattleTryoutExtraSettings.js.orig](../../ZenithTerminal/Launcher/decoded/data/js/gameplay/battle/BattleTryoutExtraSettings.js.orig) 中，`Reset()`显式把`SettingsManager.MiscSettings.TrainingAutoRecover`设为true；`MonsterGroupSetting`初始化和Reset也默认`LockHp=true`。这是原始默认合同，不能据此推断用户当前界面设置仍未修改。

[BattleTryout.js.orig](../../ZenithTerminal/Launcher/decoded/data/js/gameplay/battle/BattleTryout.js.orig) 的`NotifyTimeSecond`每秒检查TrainingAutoRecover：开启时给所有主玩家添加／续上`train_add_SPMP`恢复buff和`train_InheritedSpeedUp`，关闭时移除两者；`refreshRecoverBuff`在界面更新时同步处理。开启时还把生命比例低于0.6的Monster恢复满血。因此默认Tryout下“MP／SP不下降或马上回满”不能证明角色消耗失效、自然回复或循环收支正确；必须先明确关闭该恢复并观察buff实际移除，才能验普通资源条件。仅测输入与动画可以使用训练环境，但应记录设置，不能外推普通战斗数值。

默认锁血还有独立路径：[BattleUITryoutMode.js.orig](../../ZenithTerminal/Launcher/decoded/data/js/window/battle/BattleUITryoutMode.js.orig) 按该MonsterGroup的`LockHp`添加或移除buff`1109`；原始BattleTryout初始化默认Monster也会添加该buff。目标血条不下降／无法击杀不能直接证明招式没伤害。试验实际扣血、击杀和强度前，应分别确认怪物锁血与TrainingAutoRecover状态；只关闭其中一项仍可能被另一项改写生命表现。以上结论来自原始脚本静态核对，不是本轮宇文逸伤害或资源实测。

发现缺口时先写清具体证据、尚未核实的假设和受影响行为，再实施完整批次；冻结后集中编译、验证和验收。资料、模拟回归、真实资源读写、构建、进程状态、画面和实际操作分层记录。新增证据推翻旧归因时，补充更正，不篡改不可变历史检查点。

每次结束清理本轮临时产物，保留正式源码、参考 manifest、证据、独立基线及恢复必要备份；知识库只保存结论和权威路径。
## 2026-10-15：恢复收尾与桌面中断

宇文逸工程验收实际完成 18 阶段。安全安装保留的 `manifest.orig`、`manifest.orig.build`、`merge.json.orig`、`merge.json.orig.build` 属于任务工作副本的四份恢复备份；必须把独立基线、当前恢复索引、备份字节及 build stamp 逐一绑定，私有归档回读后，才使用白名单事务删除。保持完整文件集验收，不能将四份备份加入忽略名单。

重复构建的临时目录允许依工作区约束清理；续验必须绑定原始通过收据、日志、清理记录、重复构建一致性和当前构建字节，并明确 `readback_now=false`，不能声称重新读取已不存在的目录。当前角色构建 146 资源工程通过，但物理 Esc 中断发生于实机启动前；`e590ad1585024475a35c0aea7df048a7` 已完整恢复，未获得角色战斗证据。



## 2026-10-16 第二轮实机纠正

- 原生Texture/atlas离线解码正常，不代表选中材质正常。a85候选实际选中图标出现白绿饱和，须把未选中、选中、已获得/未获得及Texture/atlas分支作为同一UI状态验收。不能直接关闭原生选中效果掩盖。
- 同一SwordRightFlipbooks槽的切片和曝光变化不构成三套不同普攻。用户确认截断改善，但视觉仍只一段；原body导出仅选择sword_slots:[0]，原作资源范围必须从实际NPCResources重新核对，不能把导出子集当素材全集。
- 已定位蓝衣Hero_WuDang的14个非空右剑槽及22个右拳槽，待新批提取/视审后选三套；这是元数据调查线索，未移植/未验收。
- 原素材剑气/太极重建不等于所有潜能对应武学均已移植。新增武学映射需逐项绑定GA/粒子/材质/纹理来源及真实行为，保留跨引擎适配边界。
- 当前实机失败与保护现场见docs/work/yuwen-yi/issues/02-second-playtest.md；physical Escape后不继续UI或强关游戏，正式play入口正常退出仍保留进度。
