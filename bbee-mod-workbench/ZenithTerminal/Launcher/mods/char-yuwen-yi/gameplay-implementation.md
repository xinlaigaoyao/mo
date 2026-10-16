# 宇文逸玩法实现批

核对日期：2026-10-16。本文件记录首测修复批的实现合同。旧构建已通过工程验证并实际入战，但用户首测发现连击重启、潜能展示和特效质量问题；旧结果不能覆盖本批源码。当前修复批将在完整实现后统一编译、验证和实机验收，未通过的项目不记为通过。权威外观接口为同目录 `character-contract.json`，执行状态与证据由工作区 `docs/work/yuwen-yi/issues/01-first-playtest.md` 持有。

## 首测修复合同

SkillActivate.PreScriptCall 与 ActionSwitch 共用 `YwyGate`；资格检查只读当前动作时钟和输入边沿，实际动作开始才消费输入。持续按住不能被当成多次平A，地剑/空剑/剑气必须在前序动作的明确开窗后才允许衔接；预输入窗口为0.48秒。冲刺、跳跃和普通受击脱身保留独立资格，不用全局大冷却堵住操作。

原剑六帧的前3帧是蓄力，后3帧才前伸。地剑采用6/4/6个原姿态，逐帧曝光分别为 `[2,2,2,4,4,10]`、`[3,7,7,11]`、`[3,3,4,8,6,12]`，衔接点为16/20/27模拟tick；空剑和真武也将命中/出气与实际前伸对齐。原帧像素与原始权重保留，曝光是为BBEE横版战斗重新设计的时序，不声称原作本来这样播放。

空一、空二、真武的曝光分别为 `[2,2,2,6,5,10]`、`[5,8,8,12]`、`[2,2,3,4,3,18]`，衔接点为20/24/17 tick。六招的 `chain_after_ticks` 与 `source_keyframe_ticks` 由角色合同持有，生成器的输入策略与角色审计必须一致；每招末姿态在普通衔接前至少曝光2 tick。真武第9 tick发气位于实际前伸帧，持续1.5秒的主弹体使用90 tick的原素材改编序列。

`potential_content.py` 为12张潜能生成原生Type2/Inherit展示树、招式按键、实际条件与数值、出生招式提示，以及4组已有代码效果的真实组合说明。大图使用独立原生Texture，与潜能atlas保持相同像素；不会用文案虚构额外解锁或隐藏伤害。绝式由自有 ActorVirtualButtonConfig 将原生Dynamic按钮接到Ultra命令4/技能组3，战术召唤保留独立入口。

`original_vfx.py` 使用原作PAK提取的纹理、SubUV及Cascade参数重建8组有限寿命效果，共222帧。UE的材质程序、扭曲和网格形变没有无损移植；投影、透明遮罩、颜色、尺寸与时序的适配由manifest记录。蓄势、剑圈、绝式和命中闪光的附属视觉弹体无HitData、BehitBox或SkillDamage；真实伤害仍由原生主体盒负责。视觉跟随绑定本次动作实例，取消、受击、死亡和场景退出必须回收。正式来源边界见工作区 `docs/work/yuwen-yi/research/original-vfx.md`。

## 数据与动作

正式 ActorId `200901`、ClientSkinConf.Id `200901020`、角色名 `ywy`、皮肤 `02`。`gen/id-ownership.json` 保存对全部 stock `.orig` 表及其他 Mod/shared JSON 的精确值查重记录；它是编号来源核对，不是行为测试。

`build_yuwen.py` 仅在 prepare 阶段生成描述符和逻辑树，build importer 只读这些输入。它从 build 25627491 的 Ragna native ActionLogicGroup 取得序列化字段和基础运动/受击/死亡规则，删除 donor 攻击、声音、FX、投技、潜能、条件 RID、弹体与脚本，再建立自有剑拳判定、移动、输入、取消、MP 和弹体。头像及身体只由资产生产模块持有，不能用 Ragna 身体兜底。

出生完整动作包括三段地剑、上挑、两段空剑、真武穿透剑气、地空追身剑、下技能主动太极拳、短/满蓄剑圈、地面两次和空中一次梯云纵、独立七秒脱身、原生 Ultra 三段绝式。原召唤仍走 `SummonSkill` 与 `CreateBullet_summon`，治疗瓶保留 `UseHealthFlaskSucc`。主动招式主体由 `ActionLogicGroup.HitDataList` 和 `SkillDamage` 构成；没有依赖 HUD 伤害 tick。

## 原生输入与资源合同

普通剑首击立即起手。持续按住 Attack 至约0.30秒，由原生 `ActionLogicCondition_Input.InputKeyMode=4` 进入移动蓄势；释放由 mode=3 分派短蓄/满蓄，满蓄要求蓄势动作至少0.50秒。只有最终 `SkillActivate.Mps` 扣30/40真气；不足40但有30可短放，不足30直接退出蓄势。蓄势允许梯云纵、跳跃、技能与绝式取消，不先扣资源再补回。

Slot 2 真气0～100，出生100，HeroConfig 原生自然恢复3点/秒；天赋额外原生 Type141 `Slot=2` 回气。基础剑命中一次动作最多回6/6/10，空剑6/10，上挑6；敌对罐子、同阵营对象和剑气自身不能递归刷资源。Slot 3 为原生绝式，出生100，绝式启动一次扣100；资格行与真实 `Input=Ultra` 动作行分别存在。Slot 11 保留装备召唤。

太极势0～5由原生首次命中/剑拳交替/化劲事件积累。剑圈出手按势快照强化，并获得不超过15%最大生命、持续3秒的真实原生盾上限 Buff，再设置实际盾量；不会由界面模拟承伤。短盾仍需要实机检查 Buff 属性刷新、盾扣除和过期。房间开始、死亡、重开、退出清理由 native StartStage、Dead Action 和 BattleJs.BattleExit 路径负责。

## 化劲与取消

太极拳本身有实际掌劲盒，化劲失败仍会攻击。前0.35秒由 `BehitBoxs.BehitPreproc` 将本次来袭的 `IncomingDamageScale` 置0、禁止该次被动反应；前0.20秒为精准奖励。每招及每秒最多一次奖励，后续同窗攻击仍被化解但不重复刷气。窗后至0.50秒只有70%减伤，随后正常承伤。化劲潜能可把窗延长到0.45秒；反击潜能产生独立、有限寿命和命中预算的范围弹体，不把敌人受击强制改成可控制状态。

梯云纵0.30秒原生 Invincibility，免费；两次地面连续位移由原生开始事件维护预算及0.45秒恢复，SkillActivate.PreScriptCall 与 ActionSwitch 使用同一 `YwyGate`，不能通过改动作名绕过。不再给第二次地冲额外施加共享技能链CD，以免重复恢复限制同时堵住空冲或脱身。空中次数和二段跳由 native CDList 落地重置；二段跳新增真实Jump输入行，原生动作CD仍检查。解控入口只在列明的普通受击/躺倒动作中满足新输入和独立七秒 `YwyGate`，使用原生直接动作切换，明确排除死亡、CinemaControl 与抓取，不全帧清除任何负面状态。

显式技能分派同时绑定原生 InputDir 条件；不能假设 `SkillActivate.InputDir` 会替显式 `ChangeToSkillByActionName` 过滤方向。普通技能模式为中立剑气、上追身、下掌劲；普通地剑排除上方向，上攻击走挑空。次段连击只在实际前序动作的开窗中出现。付费及有原生次数限制的技能检查使用15，即GroundState+CD+MP+ActiveState；stock常见13不含CD，不能用它假装检查了空中次数。蓄势进入、低气退出和通过独立资格的无费用普通受击脱身使用直接状态切换。

剑圈用原生 ForceFields 聚普通敌人。免聚首领仍受到同等主体盒与每目标一次创建的附着剑气；附着在出生后一模拟 tick 才开始原生跟踪，给 TargetMgr.SetTarget 留出确定时序。每个弹体的同盒预算采用 native `IdCasterAttackerAction`，双剑气不能意外共享同一命中次数。真武剑气为有限1.5秒寿命，不无限穿越关卡。

## 三条潜能路线

剑宗扩展双追剑、三向剑气、空中二跳/轻功恢复和剑圈后续；化境扩展化劲窗、精准反击、交替短盾与轻身追击；无极保留剑圈势、绝式恢复脱身、交替双资源收益与满势主动剑阵。12张卡均有明确事件行为；基础动作不会被卡牌锁住。数值是强势候选，尚未通过高难首领和清场实测。

`js/hud.js` 只读原生 MP、原生 Shield 与事件状态，显示气/势/盾/脱身恢复；既不创建战斗状态，也不扣气、判定化劲或执行弹体/伤害。依赖在回调时读取，不在模块加载时取得未就绪 Util。原生 BattleExit 包裹保留原函数与参数、返回值，并在退出前回收角色状态和自有 HUD 对象。

## 静态来源

- `decoded/assets/actor_logicdata_rg.ab__rg.json`：移动/受击字段、MotionType3、Input 条件、Invincibility 与 HitData 实际形状。
- `decoded/assets/actor_logicdata_nobullet.ab__nobullet.json`：原生弹体 ActionLogicGroup 对象布局。
- `decoded/assets/actor_logicdata_icey.ab__icey.json`：AttackerCalls `CalcStage=1/3` 的真实使用。
- `decoded/assets/actor_logicdata_mi.ab__mi.json`：CrossHit 使用 BehitPreproc 的实际原生入口。
- 当前 stock `actor/buff/buff.ab::Buff`：只读核到10501 Type73盾上限、10161_baoqi Type141 `Slot`、24401_cd Type143 `group`；未修改源 bundle。
- `decoded/data/js/gameplay/battleactor/ActorFuncs.js.orig`：`pubfuncs` 和 `(actorJs, params, obj)` 绑定接口。
- `decoded/data/js/gameplay/battle/BattleJs.js.orig`：BattleExit 原生生命周期。
- `dump/dump.cs`：ActorAttrMgr.SetMP/GetMP/SetShield、BuffMgr.RefreshBuffAttrForce、ActorTagMgr.HasTag、ActorCountDown.SetCountDown、BulletMgr.CreateBulletByParams、InputKeyMode、SkillGroup 与实际枚举。

## 集中验证交付

首轮统一验证已由根 agent 执行：130份源码编译、艺术准备、86动作生成、265回归（263通过、2跳过）与19个离线事件场景通过；随后完整构建在表组合阶段严格拒绝，原因是框架把 SkillDamage 错当 `(ActorId,HitTimes)` 键，19个真实动作均有合法 HitTimes=1。当前 dump 的 `Xlsx.XlsxLoader_SkillDamage.Pk` 是 `ValueTuple<uint,string>`，`Get(uint actorId,string action)`，真实键明确为 `(ActorId,Action)`。HitTimes 是伤害元数据，不能编造不同值避开冲突。共享键由根 agent 修复；角色保留普通 `$new`，不使用 `$append` 豁免伤害表。

角色新增 `native_table_contract.py`，在完整 prepare 阶段审计所有18张角色表：从当前 dump 的 typed Get 获取真实键、与 schema 字段对应，展开恰好一条 stock copy 源并按实际 protobuf 类型编码，拒绝真实键冲突；检查全部打击 Action→自有 SkillDamage→正伤害比例→动作内命中时间/预算，以及潜能和天赋 Trigger/Effect 闭包。`SkillActivate` 的原生加载器是 list，其角色操作身份采用 ActorId/Group/Order；`ActorConfig` 在此 dump 无 XlsxLoader 声明，改用 `decoded/data/js/gen/Xlsx.js.orig` 的真实注册 `c(ActorConfig,$pb.act91.ace.ActorConfig,["id"])` 原文断言，输出收据绑定此源文件 SHA，不伪称找到 typed native Get。

角色身份与缺省值复用共享 `native_table_keys.py` 的 `NATIVE_TABLE_KEYS`、`NATIVE_KEY_DEFAULTS` 和 `native_identity`，并绑定模块 SHA。stock JSON 省略的 Lvl 必须按真实 protobuf 默认0处理，不能沿用 composer 旧默认1或角色临时 None。新增自有行则另行硬要求显式给出身份字段；BulletConfig 的通用 StartAction 可按真实空字符串默认。角色审计不会另造一套放宽后的主键规则。

已逐表核对的实际键：

| 表 | 实际 native 身份 |
|---|---|
| HeroConfig、ClientSkinConf、SkinUnlockConf、BaseActorPotentialConf、ActorActionConf、PotentialComboConf | Id |
| BaseActorConf、BaseActorAttrConf、FesActorAttrInheritConf、PvpBaseActorAttrConf | ActorId |
| BulletConfig | Id / StartAction |
| SkillDamage | ActorId / Action |
| PlayerBattleTriggerDetail | Idx / Lvl |
| BaseActorTalentQualityConf | TalentId / Quality |
| TalentEffectConf | EffectId |
| HeroPortraitOffsetConfigUI | Id / Key |

每个含 HitData 的角色/弹体 Action 必须拥有自己的唯一 ActorId/Action 伤害行。三段剑、两段空剑、挑空、追身、掌劲、短/满剑圈、绝式，以及7种原生弹体共有18个真实打击 Action；真武本体另有一条无直接盒、供弹体归属的 source skill 行。每行真实 HitTimes=1，实际多段权重在 HitData.Victim.DamageMultiply 中明确分配，不能把 HitTimes 当动作索引或修改既有 DamageRatio 来迁就错误键。

原生潜能 atlas 容量由实际 donor 对象决定，不能按图片大概尺寸推算。初选100101只有14个 Sprite slots，完整构建已严格拒绝16图请求。资产侧随后只读核对18个 stock atlas，确认103401有16个 Sprite对象、16个独立120×120矩形、976×244页面；生成器改消费画像 spec 明确提供的 `donor` 和 `rename`，不硬编码另一个猜测 donor，16张自有图标保持全部存在。原生 `PotentialUtil.GetPotentialIcon(t,true)` 使用潜能行自身的 actorId/IconId；宇文逸12行没有 IconId5000，因此此 atlas 不额外复制其他角色的 Potential_5000，原生其他行仍读取原actor atlas。

全部实现与资产准备冻结后，根 agent 统一执行源编译、`tests/native_events.cjs` 的离线事件场景、完整表/JS/资源闭包、双构建和事务验证，再进入新角色实机验收。离线测试覆盖一次动作多目标奖励、递归抑制、化劲窗和奖励去重、盾上限、保势潜能、有限三向弹体、首领附着预算、脱身条件和 native 生命周期；mock 不证明 C# 回调确实触发、物理盒有效、UI可见或角色强度合格。

实机必须额外核对：自有身体/头像与技能FX、方向/地空/长按释放/低气、普通敌人和免控首领实际命中、化劲 Calc 入口、真实盾过期与天赋恢复、12卡抽取及各路线操作变化、召唤与治疗瓶、暂停/房间/死亡/退出/重开与撤回。任何失败先修完整受影响集合，再集中重验，不按每一张卡反复跑整套。

本批源码的离线事件用例共31项声明，新增输入消费与重启拒绝、预输入、实际动作时钟优先、长按状态保留、冲刺取消、Jump边沿、视觉动作实例绑定和命中表现预算；尚未执行，不记为31通过。统一流程须先艺术prepare和角色generator生成 input-policy.json，再执行这些用例。实际按键、Native ActionSwitch排序、跟随效果、六招峰值与高难性能仍以本批实机为准。

本批改动说明：针对用户连按重启、招式提示缺失和效果质量反馈，统一修复输入双入口、原姿态曝光、原生潜能树与绝式真实输入，并接入有来源的纯视觉附层。保留首击即时、蓄势与防御取消，通过事件消费、当前动作时钟和显式曝光合同约束重复启动。当前工作区无Git，未创建提交；玩法子任务没有单独执行编译、测试、角色生成器或构建，最终验收记录由根任务集中填写。

统一验收已完成141份源码编译、291项框架回归（2项跳过）及31项离线事件场景；随后完整构建在弹体逻辑写入阶段严格拒绝缺少 `ActionLogicCondition_Script` 的原生类型描述。日志中角色 `ywy.ab::rg` 已成功写入，实际失败对象是继承 `nobullet` 的 `ywybullet`，不是Ragna角色供体。`nobullet` 的类型集合不含新增Script/Input条件；原版rg包含它们。描述符因此显式给弹体clone声明 `refTypesFrom:["actor/logicdata/rg"]`，复用既有 `bbchar.clone_bundle` 合并原生SerializedFile.ref_types的能力，只补类型元数据，保留原有门控与nobullet业务布局。角色审计检查该唯一声明及生成引用的(class,ns,asm)闭包，真正序列化和类型回读仍由接下来的统一完整构建证明。此修正尚未执行单独编译、测试或构建，之前的通过收据不能覆盖新输入。
