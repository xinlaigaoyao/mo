# 宇文逸首轮实机反馈与修复清单

当前安排：**用户最新直接回复“已解锁，可以实机”，主会话实际核对unlocked，覆盖只离线的历史停点。** 工程与保留进度入口已完成，原生图像QA收尾后集中实机；179包／完整事务工程通过，实际体验仍pending。更新日期：2026-10-16，北京时间。

先睡觉／只写文档、允许实机、人在寝室外先只离线均保留为历史，当前以最新“已解锁，可以实机”为准。操作从 [验收记录的唯一最小清单](../acceptance.md#实机最小清单) 开始；正式存档和当前进度保留，不能用旧 `guard.finish` 回滚。

## 被测版本与实际覆盖

被测游戏为工作副本 `ZenithTerminal/Launcher/game`，游戏 build `25627491`。角色 ActorId `200901`、逻辑组 `ywy`，运行保护 ID 为 `67946a5463a5467786d4b548e3a498b5`。

- `_build.json` SHA256：`4a11c43b047db4b44dd068da24b5886ff5bdfb41aa9caccb617f241a4e9d62ff`。
- `profiles/yuwen-yi.json` SHA256：`cd7763272595eb7e9f9f6cb4693f9acef2c336e7baa1f1b20482f611fd5baed8`。
- root 实际观察了宇文逸战斗身体与真气／太极势 HUD，F9 确认 `player.id=200901`、`player.logic=ywy`。
- 诊断时间为 2026-10-15 23:52:45，北京时间；报告 SHA256 为 `7face148038baf69625c1595ea83cab953a6133b7fa5ca3bac46ed795bc7f0f1`。
- 公开摘要：[first-role-diagnostic.json](../../../../evidence/yuwen-yi/first-role-diagnostic.json)。原报告已归档在私有运行目录，公开材料不复制账号、存档根或完整原始日志。
- 动作与输入切片：[first-playtest-motion-analysis.json](../../../../evidence/yuwen-yi/first-playtest-motion-analysis.json)，保留 18 次第三段循环、8 次剑气自重入及两段无新输入的观察窗口；这是对旧诊断的只读整理，不是执行新测试。

最近 900 条事件中有 197 条动作切换、106 条技能事件和 36 条命中事件；警告列表共 61 条。它们能定位输入与动作问题，不能把每条警告都直接认定为缺陷，也不能证明全部潜能和高难性能已通过。

18 阶段工程通过、146 资源闭包和双构建一致属于被测版本的工程证据；用户实测已暴露玩法与表现缺陷，角色不能据工程收据宣布完成。

## 1. 普攻连按截断动画与输入复用

用户实测：单次平 A 动画完整；连续输入反复停留在起手帧，攻击频率缺少合理限制。修复须保留即时首击、强势连段与冲刺取消。

| 已确认项目 | 实机／源码证据 | 影响 |
|---|---|---|
| 第三段回首段 | 18 次第三段→首段，运行仅约 .080–.084 秒，第三段标称 .6 秒 | 第三段命中窗第 10–19 帧尚未开始就可能被循环入口截断 |
| 第二段接第三段 | 当前切换点约 .16 秒，第二段仍有第 13–17 帧命中窗 | 连按可能丢失第二段后半招 |
| 剑气自重入 | 8 次 `ywy_zhenwu`→自身，约 .158–.164 秒重启，标称 .533 秒 | 同类问题影响技能节奏与表现 |
| 无新输入也重启 | history 的 375.868→375.949 三段→首段间无新 Attack；376.115→376.278 剑气自重入间无新 Skill | 还需阻止同一次按下事件被重复消费 |
| 技能链与动作树双入口 | `skill_rows` 默认 `ActdurStrict=.16`、all 静默仅 .08；剑二、剑三重复带 `Start_1`；`cancel()` 给攻击加入首段入口 | 只改动画播放或其中一条入口不足以修复 |

源码：[build_yuwen.py](../../../../ZenithTerminal/Launcher/mods/char-yuwen-yi/build_yuwen.py)、[actor.js](../../../../ZenithTerminal/Launcher/mods/char-yuwen-yi/js/actor.js)。原生对照为 `decoded/tables/SkillActivate.json.orig` 和 `decoded/assets/actor_logicdata_rg.ab__rg.json`。Ragna 首段启动、中段继承、末段退出的合同须保持一致；现有 `SkillAttr` Ragna 行是传承技能数据，不能冒作普攻冷却依据。

本批已写入源码、尚待统一验证的合同：

1. 技能链自动入口和显式 ActionSwitch 共用资格判定，依据实际 `ActionMgr.Time`、命中窗与合法衔接窗，防止技能链退出后越过当前动作。
2. 修正 `StartTrigger/PreSkillOrder/ExitTrigger`，移除攻击中无条件回首段的通道；第三段合法结束后可继续循环。
3. 动作真正启动后才记录已消费输入时间戳；资格检查只读，不提前吞预输入。同一次按下只起招一次，新输入可在合法窗口衔接。
4. 保留首剑即时、持续按住约 .30 秒转蓄、约 .80 秒满蓄、短／满蓄释放及低气退出。
5. 冲刺使用独立取消规则。历史中的 .02／.035 秒冲刺脱离可能是设计，不随攻击防重启一起锁死。

`YwyGate` 由原生技能链自动入口与显式 ActionSwitch 共用，读当前动作时间和原生输入时间戳；`YwyStart` 在真正起招后消费该次输入，`SetPressInputSatisfied` 不把物理按住状态改成释放。跳跃采用独立原生 Jump 输入；地面双冲、空冲和脱身保留各自资格。以下60 Hz时间线是本批源码合同，尚未获得新构建播放证据；末尾伸剑保持帧完整保留，不冒作新绘收剑帧，连段窗口不等于删除动画尾帧。

| 动作 | 本批保留的原始帧索引 | 各帧 tick | 合法后续攻击起点 |
|---|---|---|---|
| 剑一 | 0–5，全6帧 | 2、2、2、4、4、10 | 第16 tick |
| 剑二 | 2–5，连续4帧 | 3、7、7、11 | 第20 tick |
| 剑三 | 0–5，全6帧 | 3、3、4、8、6、12 | 第27 tick |
| 空一 | 0–5，全6帧 | 2、2、2、6、5、10 | 第20 tick |
| 空二 | 2–5，连续4帧 | 5、8、8、12 | 第24 tick |
| 真武剑气 | 0–5，全6帧 | 2、2、3、4、3、18 | 第17 tick |

动作、命中窗、普通取消、预输入、素材 sidecar 和原生动画时间须共同核对；不能用静态帧数推断连续操作已经顺畅。

验收：单按完整；快速连按稳定一→二→三→一，剑二两次命中和第三段命中保留；预输入不丢、不重起；同输入仅消费一次；长按、释放、低气与冲刺取消均正常。以旧失败序列补真实输入／技能链回归，现有 19 条离线事件不模拟这一层，不能单凭它们宣称修复。

## 2. 潜能缺少招式、按钮与关联效果

用户要求按原生角色方式展示招式提示、增强／解锁结果及隐藏或关联效果。首测源码的 12 卡全部关联无 `Inherit` 的独立 `Type=1` 动作根，`ActorActionInput` 为空，出生招式与这些根分离，没有关联效果表。`ActorActionNameRuby` 被写成“剑宗／化境／无极”，而原生 Ruby 标题会读取该字段，存在把分类显示为招式主标题的问题。

原生链：`BaseActorPotentialConf.RelationId` → `ActorActionConf`；`Inherit` 连接派生树；`Type=1` 为招式、`Type=2` 为增强项；`ActorActionInput/Desc/Label` 提供按钮、说明和提示。`PotentialComboConf.Potentials + RelationId` 控制关联条件与获得状态，真实主键为 `Id`，`dump/dump.cs:178198` 有 `Get(uint id)`。

消费代码位于 `decoded/data/js/core/PotentialUtil.js.orig`、`window/potential/WidgetActionsDesc.js.orig`、`DataActorAction.js.orig`、`PotentialCombosBase.js.orig`。

下表已由 [potential_content.py](../../../../ZenithTerminal/Launcher/mods/char-yuwen-yi/potential_content.py) 写入完整提示数据，保留潜能 `209001–209012`／动作 `909001–909012`。它们全部为 `Type=2` 增强项，并通过 `Inherit` 接到对应出生招式。**源码已实现不代表原生 UI 或实际效果验收通过**：

| 潜能 | 必须展示的条件、效果与边界 |
|---|---|
| 两仪连华 | 地面第三段剑首次命中追加两道剑气；第二道为第一道的 70%，每次第三段结算一次 |
| 真武三清 | 真武剑气追加上下侧刃，各为主刃 75%；均有有限寿命 |
| 梯云追月 | 追身剑启动重置二段跳、空中梯云纵；不能扩写为重置全部空连 |
| 剑势不绝 | 剑圈启动返 5 真气，持续到 .45 秒追加双剑气；提前取消不保证追击发出 |
| 以静制动 | 化劲窗 .35→.45 秒；精准窗仍为前 .20 秒 |
| 云相反照 | 成功化劲追加范围反击，精准化劲反击增伤 50%；奖励间隔 1 秒 |
| 拳剑相生 | 本人剑式与主动掌劲交替的首次命中：额外回 5 真气，得 3% 最大生命、持续 3 秒的盾 |
| 轻身破阵 | 梯云纵后 1.2 秒本人直接攻击增伤 25%；完美闪避额外积 1 势并刷新窗口 |
| 圆转不息 | 剑圈最多消耗 2 势，伤害与盾仍读取出手前全部势 |
| 流云归一 | 绝式启动刷新独立脱身机会；绝式出生自带，不是此卡解锁 |
| 百川归流 | 合法剑拳交替首次命中额外回 8 真气、4 绝式资源 |
| 四象无极 | 交替命中达到 5 势触发剑阵、3 秒增伤 40%；剑阵间隔至少 2 秒 |

本批补齐按钮、费用、触发条件、时长、次数／间隔、取消边界与实际招式标题；`Type=2` 的 Label 同时携带按钮提示，因为原生增强项不会直接绘制 Input。出生10招加真实“拳剑流转”机制说明共11项，按8个可见根组织；挑空／空连挂在剑根下，脱身挂在梯云纵下，仍出生自带，不增加潜能锁。原生完整页面会直接读取每个根的首个关联潜能，因此所有可见根都必须有有效潜能和图标，不能留下孤立根。

关联表已写入4组既有双卡叠加，不新增奖励回调或额外战斗解锁；共享与角色审计采用真实 `(Id,)` 键。

| 组合 ID／展示动作 | 必需潜能 | 展示的既有效果 |
|---|---|---|
| 209101／909101 静中反照 | 209005＋209006 | .45秒化劲窗可触发反击；精准增伤50%仍只在前.20秒 |
| 209102／909102 百川相生 | 209007＋209011 | 合法交替合计额外回13真气、4绝式资源和3%最大生命的3秒盾，不再结算第二次积势 |
| 209103／909103 轻身入无极 | 209008＋209012 | 两窗口重叠时本人直接攻击两项倍率相乘为175%；独立剑气只享无极140%，仍须满足5势交替与2秒剑阵间隔 |
| 209104／909104 圆转续剑 | 209004＋209009 | 剑圈返5气、最多耗2势、按全部势强化；持续至.45秒追加双剑气，施放前仍须30／40真气 |

绝式输入已完成静态追踪：`InputCmd.Ultra=4` 存在，Rewired 没有名为 Ultra 的动作；原生 Dynamic 命令按角色 `ActorVirtualButtonConfig` 映射，未注册角色默认回到召唤。生成器新增200901/style0的无潜能条件 `Dynamic→Ultra(4)` 入口，提示使用 `<action=Dynamic>`；原召唤战术继续使用 `<action=Summon>`。费用提示对应原生 Slot3 扣100资源。实际按键／手柄图标、扣费和召唤仍须本批实机验证。

原生详情与关联面板的大图另走 `UI/Texture/IconPotential/Potential_<pid>`，不只使用小图 atlas；本批同时补齐12张独立大图资源合同，待构建及画面回读。

验收原生完整／简略面板、当前／已获／未获样式、派生关系、按钮随绑定变化、关联预览与获得后高亮，并逐卡对照实际触发和数值。

## 3. 剑气与武学特效改为有来源的原版素材

用户认为当前剑气廉价。源码确认 `body_source.py::effect_frames` 使用 `ImageDraw` 绘制八帧几何剑形、圆环和光线，来源标为 `authored_vector_effect`。它们是自制效果，**不是《逸剑》原版特效移植**。旧回读通过只能证明图像存在与可读取。

以下来自已核基础 pak 中 GA 技能资产的实际 import。效果均位于 `/Game/JH/ParticleSystem/` 下。首测后已落盘原版VFX参考、来源参数合同及横版派生候选；它们不能继承旧几何图的回读结果。

| 原版技能资产 | 真实 ParticleSystem 引用（相对上述根） |
|---|---|
| `GA_WD_J_ZhenWuJianQi` | `AdvancedMagicFX09/Particles/P_ky_waveSlash1`、`AdvancedMagicFX15/Particles/P_ky_flare1`、`AdvancedMagicFX01/Particles/P_flareInpact` |
| `GA_WD_J_LiuYunTaiJian`、`GA_WD_Z_LiuYunTaiQuan` | `DZ_Effects/TaiJi/particle/xuli2`、`xuli4`、`MagicFxCollection01/KYmagicFX03/Particles/P_ky_flashImpact` |
| 流云太极心法首批参考 | `DZ_Effects/TaiJi/particle/xuli1` |

参考 manifest 为 [20261016T005054Z-5a4768831a59](../../../../references/wandering-sword/20261016T005054Z-5a4768831a59/manifest.json)，包含54张原版纹理的读取记录；来源参数合同和 [adapted/manifest.json](../../../../ZenithTerminal/Launcher/mods/char-yuwen-yi/assets/original-vfx/adapted/manifest.json) 分别记录来源、实际使用的纹理、派生帧和适配边界。54张来源纹理不等于54张都被每个效果使用。

基础包 SHA256 为 `5e049dc376c36dacadf6edb6fab133942679b54b1809d7f483728deec35beaff`。源 Steam 只读，覆盖包不混作基础包。

本批移植合同与待验边界：

1. 有界读取 Cascade emitter、material、texture／SubUV 与播放参数，保留 pak 成员名、哈希和导出回读 manifest。复杂 `xuli1` 超出旧首批 Package 解码器的 16-export 上限，不能直接放宽旧解码合同换取成功。
2. 导入真实原版剑气贴图／序列，重建主体、余辉、命中、消散；蓄势、剑圈、掌劲与剑阵使用已核来源的对应素材。
3. UE 粒子系统不能直接在 Unity 运行。原版贴图／序列移植与横版朝向、枢轴、比例、时序、叠层、必要材质重建分别标注，不能冒称无损复制。
4. 可见范围、生命周期与命中盒分别处理，不把人物当弹体，不继续把固定八帧几何圈称作原版效果，也不靠堆粒子掩盖动作截断。
5. 保留旧正式素材与哈希证据，整批替换 producer 后统一准备、审核和构建。

派生候选共8种FX、222帧：短剑气24、真武波30、命中24、化劲反击30、无极剑阵30、蓄势30、剑圈24、绝式场30。原版纹理裁片／SubUV层作为来源；横版投影、旋转缩放、RGB通道转透明遮罩、染色、软边、枢轴、叠层与60 Hz时序属于明确的BBEE改编。生产帧画布最大96像素，世界比例单独记录以满足atlas／源像素边界，不改变命中盒。Cascade／材质参数用于来源证据，未在Unity执行UE发射器、网格或shader，也不称逐粒子无损复制。

本体命中与纯视觉层分开：蓄势／剑圈／绝式／命中特效层不添加伤害表或命中盒；跟随与清理绑定施法者、房间和原动作实例。蓄势跨正常循环保留绑定，取消／受击／死亡／退战须结束；剑气有独立寿命与有限命中预算。root已查看8FX接触表／源剑姿势并在 [新完整视觉审核](../../../../evidence/yuwen-yi/complete-art-visual-review-first-playtest-repair.json) 批准候选。旧prepared55文件按 [归档收据](../../../../evidence/yuwen-yi/history/prepared-art-c7655acab1f753a2b5481cb4a4152d8ca83223f1b96a24be40d95d00b696d753.json) 保留后重备，新179包原生全回读通过；独立图像／UV／tex／tick／尺度QA正在补，Unity材质与实际动作待实机。

验收同时看逐帧／时间线和真实场景的出手、飞行、命中、消散，覆盖左右朝向、侧刃、多剑气同屏、首领、取消残留与性能。静态 PNG 或 bundle 回读不能代替实际视觉结果。

## 其他未闭合事项

F9 有 Jump／Skill／Dash 未成技能、summon 启动后进入 drop 的记录。须逐条结合前后动作、地空、CD、资源、输入时间与原生规则区分合法限制、预输入丢失、入口缺失、正常恢复，不能把 61 条警告全部当作缺陷。

正式入口 `scripts/play_launcher.py`／根 `play-yuwen-yi.cmd`已通过集中回归。旧launcher复位、guard成功 `release --keep-progress`归档，原始与当前44文件备份verified、进度exact、存档零写入／恢复；E私有配置显式绑定，配置时未launch，见 [入口配置收据](../../../../evidence/yuwen-yi/persistent-entry-configuration.json)。当时副本卸载保持2,397文件pristine，首次cmd会自动安装已验候选。正常退出只复位owned配置、保留进度和角色；不得重做迁移或用旧finish回滚。真实保存／重开待验，规范命令见 [PACKAGING.md](../../../../scripts/PACKAGING.md)。

## 收尾与下一次实机

1. 当前工程、179包事务和正式入口迁移已完成；游戏保持关闭，只补当前native图像QA及其结果，不重做旧guard或已通过构建。
2. 当前已经获准实机；QA收尾后只按 [唯一6项清单](../acceptance.md#实机最小清单) 集中完成核心输入、潜能详情、FX清理、高难与持久重开，记录难度、恢复／锁血设置和未验范围。
3. 实际结果回填后再冻结文档和打包，完整保留失败历史与备份；未验项仍pending，不因授权或启动成功写通过。
4. 失败保留具体证据，修完整批再集中复验受影响项，不逐个小功能反复全套测试。

## 历史停止点：先文档时的落盘与收尾状态

普攻、潜能和正式特效 producer **没有修复落盘**。中断前资产研究新增一份调查草稿：[collect.py](../../../../ZenithTerminal/Launcher/mods/char-yuwen-yi/assets/original-vfx/collect.py)，7,715 字节，SHA256 `bd5923a2bfdbfdba5e23e951f7b64d47e60b191a0ac0fa6db431ee7258634c2d`；尚未执行、编译或验收。该目录只有草稿，没有导出纹理、帧图、缓存或 partial。它改变了源码文件集合，旧编译快照不能覆盖它；保留草稿不代表读取器完成。

用户要求先文档后，已中断并行实施，未继续生产修改、导出、编译、测试、构建或桌面操作。正式素材、旧构建及源 Steam 输入未因这批研究变化。

停止桌面后的只读进程核对未发现游戏进程，但 `private/runtime/guard.json`、`launcher.json` 和安装记录仍在，**存档恢复、启动配置复位、卸载尚未执行**。私有已验证备份与 journal 是必要恢复材料，不能作为垃圾删除。最后现场为暂停菜单／暂停模拟附近，不据旧截图推定当前桌面。

上述“没有修复落盘”和残留状态只描述暂停时点，已被本批源码与素材候选进展替代，不代表当前进程状态。恢复时读本文与 [acceptance.md](../acceptance.md)，不按旧PID盲操作，不新建guard覆盖旧保护。保留源ZIP、正式参考、源码、构建、证据和私有备份。

## 本批离线结果与实机边界

本批首轮统一阶段已完成141份Python编译；素材prepare为52semantics／67动画束／293唯一可见帧，production SHA256 `872e2e0bab5061f444488df446670fd2df56388f06be84fd82e571ede5a110c1`；291项回归无失败／错误、2项宿主symlink跳过；31项离线原生事件passed，仍不证明C#集成。

随后complete-build实际失败：UnityPy `get_ref_type_node`找不到 `ActionLogicCondition_Script / GamePlay / Assembly-CSharp`。角色 `ywy::rg` 已构建成功；缺口在 `nobullet→ywybullet` 的managed `ref_types`，旧弹体模板只带GroundCheck／Hit／Trigger，新视觉清理条件需要Script声明。修复采用从原生 `actor/logicdata/rg` 导入准确声明，不放松共享校验或删除清理逻辑。首轮失败记录保留，候选未安装；修复后的新源码须统一重验，以最后同批总收据为准，不把修复前通过阶段冒写为新快照通过。

第二轮重新141编译／prepared校验／31离线事件，framework回归曾按137个覆盖SHA一致复用。之后179包strict与重复构建逐资源一致、安装／更新／撤回／卸载、四owned索引归档及工作／基线／源各2,397hash通过；[工程总收据](../../../../evidence/yuwen-yi/engineering-acceptance.json)18阶段passed，SHA256 `fd5bfbabe0cd2303083d2aaf0d704d24cf1557988eefc471c8ad08b41472998c`。新build为 `a85afaa34a33698b2719e232d37e90ce6f9ce8520fa63c4aea180db58ddf4a49`。

交付审核发现5张审核引用外部PNG漏装，已补闭包，再141编译／291回归（93.872秒、289通过2跳过、无失败／错误）；native字节及递归输入闭包未变，未再次重建，见 [交付闭包收据](../../../../evidence/yuwen-yi/delivery-closure-acceptance.json)。当前仅独立native图像QA待补；进度release／正式配置已实际成功。新 [角色实机收据](../../../../evidence/yuwen-yi/character-runtime-acceptance.json)精确绑定a85／profile，选择／combat／reopen全pending且未launch。旧146／270／19及其他角色可玩都不能替代本批结果或实际体验。

文档更新说明：保留首测失败和暂停历史，补齐本批已实现合同、首轮集中结果与真实构建阻塞，区分候选视觉批准、工程验证和角色体验。工作区无Git，本轮没有创建提交；本文件更新没有运行测试或操作桌面。

本批交付说明：[commit-note-first-playtest-repair.md](../commit-note-first-playtest-repair.md)。验证与限制按最终实际收据回填，不以提交说明代替验收。
