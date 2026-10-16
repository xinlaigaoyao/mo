# 宇文逸：BBEE 整合架构研究

核对日期：2026-10-15。状态：研究方案，尚未制作角色、运行本方案测试或构建。本文只读当前源码、已解码 stock 表和正式参考库存；没有启动游戏、改原游戏或存档。平台 Inspector 新 hook 的集中验证与实机结论由根 agent 持有，不能由本研究代替。

用户的角色体验和招式方案由 `E:\AAA MOD\bbee-mod-workbench\docs\work\yuwen-yi\spec.md` 与 `E:\AAA MOD\bbee-mod-workbench\docs\work\yuwen-yi\research\combat-references.md` 持有；本文只说明如何落实为引擎对象和资源，不另定一套平行数值。角色生产须在平台新 hook 实机门槛满足后开始。

## 路线选择

选择 `dr-party` 的**单人 Kris 身体导入＋Ragna 原生 ActionLogicGroup**作为最小结构参考，而不是复制整个 Party Mod。Party 的同伴、指令菜单、减速、专有 FX、音频编码和字体都不属于宇文逸基础整合。其 `import_kris.py` 已说明通过 `bbtag_rig.build_rig` 接收自定义 Source，输出原生 sprite rig；不需要继承 DELTARUNE 读取器或素材。

本地三个完整角色样例均有额外复杂性，没有可直接改名的“小而完整”模板。Nine 的描述符含 102 个 bundleClones、49 条 SkillActivate、110 条 SkillDamage，并从 boss 逻辑派生，复杂度高于上述单人身体链。Ruby 的私有 effects 已出现被门禁拒绝的引用问题，不作为新 importer 模板。历史默认 fixture 的全对象回读不能升级为这几个角色的当前完整实机验收。

原生 donor 采用拉格纳 `ActorId=100101`、`HeroConfig.LogicRes=rg`，保留成熟的行走、跳跃、落地、受击、死亡及基础物理规则，另建宇文逸逻辑和身体资源。`actor/logicdata/rg` 的实际 `VisualType=0`、`AnimationJsons=["rg"]`，是原生序列帧渲染路线，不是 Spine；本方案无需 `content.rigClones` 或 Spine SkeletonDataAsset GUID。复用动作状态框架不等于沿用拉格纳外观、技能判定或潜能。

推荐新描述符目录 `mods/char-yuwen-yi/`，角色短名暂用 `ywy`、skin 暂用 `02`，均是方案标识，尚未创建。依赖 `bbee-sdk`、`bbee-actors`；inspector 作为开发验收 profile 的独立依赖。描述符、生成树和所有角色素材在 prepare 阶段就绪并冻结，build importer 只消费这些输入，不能在构建中修改 `mod.json`、`gen` 或身体源图。

## 对象和编号来源

| 类别 | 已核到的来源 | 宇文逸合同 |
| --- | --- | --- |
| ActorId | `decoded/tables/HeroConfig.json.orig` 中 100101；已有 Mod 为 Nine 200401、Ruby 200701、Party 200801 | 新编号须 `>=190000`，并在本次 profile 的 stock、所有声明和生成产物中查重。200901 在本次有限 HeroConfig／现有 Mod ActorId 声明扫描中未使用，可作候选；**未预留，不能直接当正式分配** |
| 皮肤 Id | `ClientSkinConf.json.orig` 中 donor `Id=100101020`、`HeroId=100101`、`SkinName=02` | 新 HeroId 与皮肤 Id 分别分配并查重；不要把 ActorId 与 skin Id 混用 |
| 操作命令 | `dump/dump.cs` 的 `GamePlay.InputCmd` | Attack=1、Skill=3、Ultra=4、Summon=5、Dash=55、Jump=800。这是引擎命令，不是固定键盘字母 |
| 技能组 | 同一 dump 的 `GamePlay.PlayerSkillGroup` | Attack=1、Skill1=2、Ultra=3、AttackAir=4、Dash=5、DashAttack=6、Jump=7、LongAttack=8、CustomUse1/2=9/10、Summon=11、Burst=12；**组号不等于 InputCmd 号** |
| Action 名 | `decoded/assets/actor_logicdata_rg.ab__rg.json` 的 `_actions`；Party `gen/kris_tree.json` 说明替换方式 | 行走受击等 stock 状态按其真实名字保留；新招式使用 `ywy_*`，所有 Action、Next/Drop/DeadAction 与 SkillActivate.Action 必须闭合 |
| 表行 Id／潜能／Trigger | 当前各 `.json.orig`、所有启用描述符及生成后清单 | ActorActionConf.Id、Potential.Id、TalentId、EffectId、PlayerBattleTriggerDetail.Idx、BulletId 分开管理；不套用其他角色编号，不假设 ActorId 乘十即可无冲突 |
| Unity PathID／MonoScript | 实际 donor bundle 与 build 25627491 TypeTree 绑定 | 克隆时保留真实对象类型／MonoScript；从实际读取的 donor 对象取得 PathID，不能从本文手填常量或套用其他 Unity build |
| managed rid | donor ActionLogicGroup 的 `references.RefIds`，rg 当前有 1,984 个原始记录 | 复制条件时连同类型与数据建立唯一 rid 映射；没有类型的占位记录按当前 composer 合同处理。每个使用的 rid 必须有唯一可读定义，不得只改数字 |
| CAB／GUID | `bbchar.clone_bundle` 与 `tools/bbtag/bbtag_rig.py` 的 `_cab`／`_guid` | CAB 绑定逻辑路径；原生纹理页 GUID 进入 manifest 并供 textureRefs 查找。记录来源、哈希和映射，禁止随机 UUID 造成重复构建不同 |

这里的 donor 数字来自已验证输入，不是新角色正式 ID 表。正式生产应生成一份角色所有权清单，列 ActorId、skin、潜能、Trigger、Bullet、locale key、logical path、CAB、GUID 及所引用 stock 项；由全量组合预检拒绝冲突。`entry_point.py::enabled_actor_ids` 会读取启用描述符中的六位新增 ActorId，存档清理依赖正确描述符和安装绑定，不能另做隐藏注册。

## 完整数据与输入链

| 层次 | 必需表／对象 | 必须成立的行为 |
| --- | --- | --- |
| 角色注册 | HeroConfig、BaseActorConf、BaseActorAttrConf、ActorConfig | 新角色在选择列表存在，LogicRes 指向新逻辑，Skin 指向已生成 family；身高、碰撞盒和脚底尺度对应新身体。基础属性和基础循环出生可用 |
| 继承及皮肤配套 | FesActorAttrInheritConf、ClientSkinConf、SkinUnlockConf；必要时 donor 的 PvpBaseActorAttrConf 配套行 | 界面读取、意识体生成与继承不缺行。保留单人范围及 PvpUnlocked=0，不据配套表存在宣称联机支持 |
| 招式入口 | SkillActivate | 每个输入、方向、地空条件、Group/Order、StartTrigger、Preinputtime、ActdurStrict、Timeout、Mutelist 与资源结算明确；重复键只按实际带条件行处理，禁止盲目复制 donor 全组 |
| 命中与数值 | SkillDamage、ActionLogicGroup.HitDataList | Damage 行的 ActorId／Action／命中组与逻辑判定一一对应；有有效命中时间、盒、次数及敌方反应，不能只有动画、FX 或文本 |
| 剑气／附着剑气 | BulletConfig、新 bullet ActionLogicGroup（采用时） | AddRoles 的 BulletId、逻辑名、开始 Action、生命周期、命中预算及清理对应；免聚／免浮首领仍保留主体伤害，不能每渲染帧无限重生弹体 |
| 图标与动作说明 | ActorActionConf、locale、图标 atlas／texture | ActionId、潜能 RelationId 和说明图连通；普通招式说明不冒充已实现能力 |
| 潜能 | BaseActorPotentialConf、PotentialComboConf、PlayerBattleTriggerDetail | PotentialPoolId 指向宇文逸自己的池；每张卡的 TriggerInfo 指向实际效果。至少有操作变化，不能全是文字＋百分比装饰 |
| 天赋 | BaseActorTalentQualityConf、TalentEffectConf、对应 Trigger | BaseActorConf.Talents 与质量／Effect／Trigger 全链存在；局内、继承及重开清理各自有合同 |
| 传承技能 | SkillFromTeacher、SkillAttr、FesActorSkillLevelConf（若首版提供） | 传承编号、技能组、效果、图标及升级行完整；尚未做时显式空 InheritSkill，不能沿用拉格纳传承装成新武学 |
| Buff 与状态 | `actor/buff/buff.ab::Buff` 的受控新增项、原生触发条件 | 真气／势／护盾／化劲窗／解控恢复是实际可核验状态；计数范围、重入、防止自触发、死亡／房间切换／卸载有明确结果 |

`bbee-actors` 的接口需要角色主动声明：

- `BB_ACTOR_DONOR[A]=100101`：缺少角色专有经济表时由已有 stock 行提供转换／奖励配套；不把 `PotentialPoolId` 设为 donor 而偷偷继承拉格纳潜能。
- `BB_SELF_TRIGGERS[A]=[Idx,...]`：只给该角色添加持久自身触发器。原生 `BattleJs.addPersistantSelfPlayerTriggers` 合并这些行；触发器函数按 Party 的 `trigFuncs` 注册方式加独立命名空间，并在调用时读取依赖。
- 选择界面目前把 `ActorId>=190000` 角色自动加入，并禁用缺失的原生介绍影片按钮；这条分支需要新角色实际选择验收，stock 试用没有覆盖。
- HUD 名称使用 `BB_HUD_SPRITES[SpriteName]=AtlasName` 预载真实图标；`BB_HUD_TICKS["char-yuwen-yi/resource"]` 只读状态并更新表现，依赖须延迟读取，避免复制 Nine 历史 HUD 的模块加载期 `U=Util_1.U` 写法。

资源结算放在原生技能激活、命中及触发器事件中，固定点秒数遵守当前编码合同。HUD 的逐渲染帧回调不能作为伤害、无敌、资源扣除或化劲成功判定的唯一执行者。真气使用 Slot 2、绝式使用 Slot 3 是现有方案候选与 stock 接口相符的路线，但 Max／初值／恢复／继承必须在正式角色合同里锁定并实测，不能直接复制 donor 的整段 MpRecover。

原生绝式并非“Group=3、填一个 Action”就完整。当前 Ragna Group 3 的首行是含 ReqTriggerId 5317 与 Slot 3 Limit 100 的 UI／资格行，本身无 Action；其他 stock 行（例如 ActorId 103501）另有 `Input=Ultra`、`Start_3`、Slot 3 `MpChange=-100` 的实际动作入口。宇文逸出生自带绝式必须同时建立 UI／资格、真正动作入口和一次资源结算，去掉与拉格纳潜能有关的 ReqTriggerId，不用潜能解锁基础绝式，也不劫持 Summon。

## 动作逻辑与新身体

新逻辑建议克隆 `actor/logicdata/rg` 到 `actor/logicdata/ywy`，保留基础运动／受击／死亡通路，生成明确的新 `_actions` 和 managed 条件集合。`AnimationJson`／`AnimationJsons` 指向 `ywy`；每个 Animate 都能找到准确大小写的 clip，不能仅把图片页路径从 rg 改成 ywy。Party 通过 `bundleClones` 克隆逻辑、`content.assets.treeFile` 覆盖非 Unity 身份字段，随后 importer 生成身体；可复用这一分工。

新攻击 Action 至少包含实际时序、Animate／TotalDuration、HitDataList、动作移动、取消和落地路径；按需求使用 AddRoles、AddEffects、Invincibility、Armors、AddBuff、ActionSwitchs。只拷贝模板的类型与基础默认值，重新审计所有有效字段，尤其是 donor 自带 BulletId、效果、声音、条件、脚本、抓取和 NextAction；不能通过清空未知条件后假设行为等价。

身体 Source 最小接口参考 `DRSource`：`code`、`palette`、`scale`、`frame(key)->(RGBA uint8, anchor)`、`mul(key)`，可选 extra_page。用已经核验的原作身体帧或补制的横版帧做输入，**不实例化 BBTAG Source、不读取 Party 素材、不调用其他游戏所有权接口**。

必须先建立身体动作合同：stand、run_start/run/run_stop、turn、squat 及恢复、jump/jump2、drop_start/drop/dropend、地空 dash、地空受击、击退、倒地／起身、dead、出生／退场／继承演出；另外覆盖三段剑、上挑、空剑、真武剑气、追身剑、太极掌、蓄力起／循环／短放／满放、绝式每个实质打击阶段。现有 Party 列出了 16 个 `<role>_<cinematic>` 别名，可作引擎名称清单参考，不是宇文逸动作完成证据。

每帧记录原引用／像素 SHA、朝向、裁切、原 canvas、脚底 anchor、世界单位尺度、持续 tick 和用途；每个动作记录循环／结束、60Hz 总 tick、逻辑持续时间及关键打击／取消 tick。原作俯视纸片的左右翻面不自动成为横版跳跃和受击，缺失的这些动作需要实际补制。出生只换一张 stand 图、其余仍显示拉格纳，或把缺帧自动变透明，均不能通过。

原生资源闭包为：

```text
HeroConfig.LogicRes -> actor/logicdata/ywy
  _actions[].Animate -> actor/animation/role/ywy_<clip>
    Frames[].mesh PPtr -> actor/mesh/ywy/g<N>
    textureIdx -> actor/texturefamily/ywy_02.textureRefs
                    -> manifest GUID -> actor/sprite/ywy/02/ywy_page_<N>
    Context.material -> 原生 spritepalette 材质依赖
  额外通道 -> texturefamily/ywy_extra、ywy_extra2 及对应页
```

`bbtag_rig` 目前 donor 为 `actor/sprite/rg/02/rg_atk_1_c`、`actor/texturefamily/rg_02`、`actor/animation/role/rg_stand`；mesh 容量模板来自 hb/base、arboss20/ace、ma/attack。借用的是 Unity 对象布局，不是把对应角色身体留在最终外观里。原生 clip 会产生真正的 external mesh／material PPtr，因此角色资源闭包应出现并验收正向 external 引用，不能用 framework probe 的 external checked=0 代替。

## importer 的最小合同

描述符通过 `content.importers` 给出角色目录内 Python 脚本。`bbmod.py` 调用方式是 `python <script> [args...] --out <OUT> --adds <private-temporary-json>`，并设置 `BBMOD_OUT`。脚本成功才交付 `{"names":[],"entries":[[logical,[dependencies...]]],"guids":[[logical,guidhex]]}`；只有产物都存在并回读后才写 adds。错误必须非零退出，由父构建终止安装。

1. 固定 workbench／build／身体输入 manifest，验证帧文件集合、原始像素、锚点、clip tick 与生产源码哈希。OUT 必须等于父进程 BBMOD_OUT、位于工作台 staging 且在 game／源码外；adds 只写父进程本次指定文件，不另写游戏 manifest。
2. 在调用底层 builder 前完成全帧检查。当前 `build_rig` 会把 `src.frame()==None` 的缺帧替为 null；宇文逸 adapter **必须预先拒绝**所有非明确设计的缺帧／空身体，不能继承该宽松行为。故意不可见的过场单帧须单列语义，不能占普通攻击身体槽。
3. 当前 `build_frames` 缓存键只有 code／palette／帧名／页参数／FRAME_VERSION，不包含真实帧像素。新 adapter 必须把所有源图、anchor、scale、clip 与处理代码内容摘要加入 code／palette 或采用独立内容寻址缓存；读缓存再核对输出摘要。改身体字节时必定重建，不能靠人工改版本串碰碰运气。
4. 色页按 stock premultiplied-alpha 渲染合同处理；Extra／Extra2 家族、UV、页索引、mesh AABB、顶点通道、纹理尺寸都完整生成。只有 opaque 占位页或纯色 tint 而无真正身体动作不算完成。
5. 每个新 bundle 的 CAB、container、m_Name、m_Dependencies、externals、preload、局部 PPtr 都一致；textureRefs 的 GUID 必须在 adds 中有唯一目标，原依赖不能随意删除。继承的 MonoScript 和 managed 类型来源绑定当前 build；不复制 Ruby 私有 VFX 的整体 remap 策略。
6. 新技能 FX 优先从已知可读的 stock 模板作最小明确克隆，保留实际 material／texture／mesh 依赖，再绑定新剑气／拳劲行为。原作参考 FX 有限解码完成前可以采用说明清楚的改编演出，但必须有真实判定和生命周期，不以换颜色替代技能实现。
7. 所有生成 bundle 写入 OUT，缓存限工作台自有路径，build 期间不修改角色源输入。将产物、adds 及输入摘要写正式回读证据；父构建最终验证 UnityFS／对象／PPtr／RID／GUID／表和 JS payload，成功产生 `_build.json`＋`_verification.json` 才可事务安装。重复构建逐 bundle 哈希一致。

不直接调用 `bbchar.write_manifest`／`apply_manifest_additions`；前者在当前工作台已禁用。新增路径、GUID 和依赖由父构建合并成最终 manifest，再交给已验证的整组安装事务。

## 头像、立绘、技能图标与 HUD

小头像、完整立绘、战斗图标分开验收。目前两张原作头像是 145×145，只适合对应小头像槽，不能放大后冒充完整立绘。人物身份仍按来源文档 pending；身体研究批次独立，不由本方案宣布完成。

画像路线参考 `kris_portraits.py::spec/build`：新 actor 对应的 UI/Texture 路径，ui/texture/metrics 的 width/height 项，HeroPortraitOffsetConfigUI 的实际界面 Key、PivotX/Y/Scale，必要的 Head/EvoHead/Off/PDA 等 spriteAliases 同时匹配。Party 的画像 importer 允许缺图跳过；宇文逸正式交付应把约定必需槽列为硬缺口，不能静默沿用 donor 身份。

潜能／天赋 HUD 使用真正 `ui/atlas/iconpotential<A>/iconpotential<A>` Sprite atlas，SpriteName 与 Potential.IconId／Talent 名一致，再由 BB_HUD_SPRITES 预载。SDK 的 `tex:` 动态 sprite 只覆盖相应 JS LoadSprite 路径，不保证原生 C# HUD 同样接受，所以不能只填 spriteAliases 就宣布全界面正常。

真气和太极势状态由逻辑层持有，HUD 显示当前值、耗用／化劲奖励和解控恢复，不另造一套与技能实际资源不同步的数值。注册回调只作用于新 ActorId，换回 stock／死亡／退出时回收对象、监听和计数；依赖用函数内延迟读取，避免加载环。首屏、暂停、重开、不同 UI scale 与 stage 切换均有可见验收。

## stock 实机尚未覆盖的新角色分支

| 验收组 | 必须观察的实际结果 | stock 试用不能证明的原因 |
| --- | --- | --- |
| 注册与选择 | 无付费解锁依赖，新增角色选择、皮肤、介绍影片禁用、进入意识体／试用、回到 stock 正常 | stock ActorId 不经过 >=190000 自动授予和 donor fallback |
| 身体与资源 | 自有身体各必需动作可见，朝向／脚底／遮挡／UV／材质正确，所有 clip 与真正 external PPtr 可用 | 中性 clone 没有新身体，external checked=0 |
| 输入和绝式 | 短按、长按、释放、方向、地空、取消、落地和低气不吞键；绝式出生可用、使用 Ultra 并只扣一次 Slot 3 | 仅 stock 操作未验证新 SkillActivate 条件、资源和 Action 映射 |
| 真实招式 | 剑气穿透与寿命、掌劲主动攻击和成功化劲、剑圈聚杂兵／免聚首领替代收益、完整绝式主体命中 | 片段／参数／FX 存在不证明命中或首领有效 |
| 潜能与天赋 | 自有池抽取、RelationId 说明、条件触发、三条明显打法、跨房／死亡清理，无重复监听或递归刷资源 | stock 未触发 BB_SELF_TRIGGERS[A]、OPFunc 与自有潜能池 |
| 图标和 HUD | 角色身份全部正确，真实 atlas 图标、资源表／HUD 同步，暂停与切换恢复 | stock 没有新 spriteAlias／textureAlias／BB_HUD_SPRITES 分支 |
| 存档、重开、撤回 | 新角色意识体／继承记录重开可读，撤回清理新 ActorId，卸载还原且 stock 存档可用 | 当前平台 guard 保护了 stock 运行，不等于新角色序列化生命周期通过 |
| 强度与稳定性 | 相同难度／房间条件下清杂、单首领、高难生存、长连续连段、转阶段／无目标／低资源均流畅 | 平台 F9 和程序运行不是角色“爽”或完整关卡验收 |

这些项目应先完成全部受影响实现并冻结，再集中做源码／表／资源／双构建／事务及实机验收；失败先定位和修复，再验证受影响集合，不逐张图、逐行表反复跑整套。新外部引用或缺帧不能通过降低当前 verifier 换取成功。临时 fixture、失败 staging 与渲染草稿在每轮收尾清理，正式素材、来源记录、可追溯产物与必要恢复备份保留。

## 权威文件索引

以下均为本次实际读到的完整路径；路径表用于后续实现定位，不表示它们的历史角色说明等于本机验收。

- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\shared\bbee-actors\mod.json`：注册、经济 donor、PotentialPoolId、持久 trigger 的共享接口。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\shared\bbee-sdk\mod.json`：sprite／texture alias、真实 HUD atlas 与 LateUpdate hook。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\dr-party\mod.json`：完整表分类、最少三个 bundleClones、treeFile、JS appendFile 与 importer 组合的结构样例。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\dr-party\import_kris.py`：将自定义 Source／clips 接入 build_rig 的 importer CLI。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\dr-party\dr_source.py`：frame／anchor／scale adapter 示例；不使用其中 DELTARUNE 读取器。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\dr-party\kris_clips.py`：核心动作、60Hz tick 及 16 个过场别名的名称参考。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\dr-party\gen\kris_tree.json`：真实新 ActionLogicGroup 结构样例，含 HitDataList、AddRoles、ActionSwitchs 与 managed refs。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\dr-party\js\potentials_trig.js` 和 `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\dr-party\js\potentials.js`：trigger 函数注册、角色状态与延迟依赖读取参考。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\dr-party\kris_portraits.py`：画像资源、metrics、界面 offset 与 alias 链。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\tools\bbtag\bbtag_rig.py`：原生 sprite／family／mesh／clip 生产布局，以及本方案要求封住的缺帧和缓存合同。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\bbmod.py`、`E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\bbchar.py`：组合、bundle clone、asset patch、importer 和 manifest adds 的实际执行入口。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\framework-validation-probe\import_stock_probe.py`：边界检查、输出回读和 adds 合同的中性参考。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\decoded\assets\actor_logicdata_rg.ab__rg.json`：当前 build Ragna 187 个原始动作与 managed 条件来源。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\decoded\tables\HeroConfig.json.orig`、`E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\decoded\tables\SkillActivate.json.orig`、`E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\decoded\tables\SkillDamage.json.orig`：donor 行及技能／资源合同；其他表使用同目录对应 `.json.orig`。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\dump\dump.cs`：InputCmd、PlayerSkillGroup 及对象类型的 build 绑定静态来源。
- `E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\prepare_mods.py`、`E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\build_provenance.py`、`E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\build_verification.py`、`E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\entry_point.py`：生成输入、构建漂移、严格回读、事务安装及 ActorId 生命周期。
- `E:\AAA MOD\bbee-mod-workbench\references\wandering-sword\20261015T124534Z-a62a5e5c879d\manifest.json` 与 `E:\AAA MOD\bbee-mod-workbench\evidence\yuwen-yi\reference-validation.json`：已完成的限定参考范围；身体／Paper2D 后续批次另行记录，不能由这里预认定完成。

本文没有新增角色描述符、表行、JS、资源 importer 或资源；未进行编译、测试、构建或实机操作。
