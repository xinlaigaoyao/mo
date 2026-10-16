# 原版特效来源与横版适配

记录日期：2026-10-16，北京时间。工程18阶段及179包完整／重复构建通过，原生独立图像QA正在收尾。最新用户直接回复“已解锁，可以实机”，主会话实际核对unlocked，覆盖只离线历史停点；随后按 [唯一实机清单](../acceptance.md#实机最小清单) 集中观察。PNG/APNG与离线读回不算Unity表现通过。

## 来源与有界读取

基础包为 `E:\SteamLibrary\steamapps\common\Wandering Sword\Wandering_Sword\Content\Paks\Wandering_Sword-WindowsNoEditor.pak`，SHA256 `5e049dc376c36dacadf6edb6fab133942679b54b1809d7f483728deec35beaff`。源安装只读，没有运行 UE、Blueprint、shader、UE4SS 或第三方可执行程序。

读取入口为角色的 `assets/original-vfx/collect.py`，使用独立 UE4.26 tagged Cascade profile，包上限 256、原始成员上限 768、总解压上限 512 MiB；旧九件参考与 Paper2D decoder 的严格合同没有放宽。实际导出 132 包、313 原始成员、68,568,807 字节，解码 54 个真实 Texture2D。格式覆盖本批实际出现的 BGRA8、DXT1、DXT5、BC5；每级 mip 的存储量、维度、inline／ubulk 边界均核对，压缩末级以原生 4×4 块计。

三个 GA 和七个 ParticleSystem 共十个根；只沿实际 `/Game/JH/ParticleSystem/` import 读取美术依赖，不遍历音频或其他游戏逻辑。源包内所有读取成员及像素输出的哈希保存在：

`E:\AAA MOD\bbee-mod-workbench\references\wandering-sword\20261016T005054Z-5a4768831a59\manifest.json`

该 manifest SHA256 为 `81c9be40ba29154614ae81a1f11b8e5406265290f04cec0f53d83f8378c94a3a`。同目录 `vfx-reference.json` 保留 tagged property、对象引用、native tail 长度与哈希。native mesh 与 cooked shader 尾部是保留的来源证据，不是已模拟内容。

`assets/original-vfx/source-contract.json` SHA256 为 `e2a970596041c4383d1f865de14c0facf421b93c8abad1b11acaff256cb6c4ba`，将第一 LOD 的 emitter→required material→显式寿命／延迟／SubUV 参数和 material override 名称整理成可审阅合同。缺失的 tagged 字段保留为 null，表示 UE 类默认值未在此猜测；LOD 或 shader 的完整行为不冒作已复刻。

## 实际引用与生产用途

| 原 GA／粒子来源 | 本批可见素材 | 适配用途 |
|---|---|---|
| `GA_WD_J_ZhenWuJianQi` → `P_ky_waveSlash1` | `T_ky_fire01_4x8`、`T_ky_smoke2`、`T_ky_dust_longStar`、`T_ky_flare_a` | 剑气纹理主体、余辉与尾迹 |
| 同一 GA → `P_ky_flare1` | `T_ky_shockwave04_4x4`、`T_ky_shine01_4x4` | 剑气弧形前缘与独立命中特效 |
| 同一 GA → `P_flareInpact` | `T_circle9_4x4` 等实际依赖 | 绝式／剑圈的光压层 |
| `GA_WD_J_LiuYunTaiJian`、`GA_WD_Z_LiuYunTaiQuan` → `xuli2`、`xuli4` | 原阴阳纹理 `fx_Ink_A51`、墨旋 `fx_Ink_A7`、墨环 `fx_Ink_A17`、掌压遮罩 `fx_Ink_A61` | 蓄势、掌劲、剑圈、剑阵与绝式 |
| `P_ky_flashImpact` | `T_ky_decoLinesC` 等实际依赖 | 剑阵与绝式的压力线层 |
| `xuli1` | 太极资源原引用与参数 | 来源闭包和蓄势参考，未宣称完整模拟其 mesh／折射 |

原 `P_ky_waveSlash1` 的 `ParticleModuleRequired_13` 指定 4×8 SubUV、`PSUVIM_Linear_Blend`，显式寿命约 .30–.40 秒、延迟约 .13 秒。`xuli2` 的两组显式寿命分别为 1 秒与 .5 秒，阴阳／水墨材质为真实引用。BBEE 的 90 tick 飞行与各出招时长是模组适配值，不等同这些 UE emitter 生命周期。

## 材质与透明度处理

UE 粒子不能直接在 Unity sprite rig 运行。本批使用原贴图和实际 SubUV 格子，重新组合有限寿命的二维层；颜色、朝向、枢轴、比例、时序、层叠与透明度转换都属于明确的跨引擎适配，不称无损原版效果。

- `fx_Ink_A51`、`fx_Ink_A7` 原本有真实 alpha，保留阴阳黑白与墨旋颜色、透明轮廓。
- `fx_Ink_A61` 的原 A 通道全为 255，角落 RGB 为黑。它是材质使用的白色压力遮罩，不能直接 RGBA over，否则旋转时会出现黑矩形／菱形底板。本批将 RGB 亮度转 alpha，并加软边。
- 原火焰 4×8 贴图也为 A=255 的 RGB 编码素材；R 是细节火焰，G 是光核。本批分别转换成 alpha 并重新配色，使用显式 UV 四边软遮罩避免把源矩形平面显示成亮墙。
- 剑气前缘使用同一 GA 所引用 `flare1` 的真实 shockwave 右半幅，源火焰作为较弱后层，源星芒与烟纹理构成负 X 尾迹；这是原素材组合与投影适配，不声称原 UE shader 以同样方式组合。
- 原 shader 的 HDR、折射、native mesh 变形、动态粒子碰撞与三维散射未完整实现，不由静态预览代替验收。

## 冻结的输出接口

适配源码为角色根目录 `original_vfx.py`，manifest 位于：

`E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Launcher\mods\char-yuwen-yi\assets\original-vfx\adapted\manifest.json`

当前 manifest SHA256 为 `e95837cd1023abf8b0453237ddf8671eaf3d493556b30569c4eae56b4e829f94`，包含 8 个 clip、222 张 PNG、逐帧哈希和同名 APNG／contact 预览。所有生产帧最大为 96 像素画布，各效果使用固定 `world_scale_multiplier` 保留设计的世界尺寸，以满足既有 16 页 atlas／64 MiB 源像素上限；人物仍沿原统一尺度，命中盒没有随画布改变。

| Clip | 60 Hz ticks | 循环 | 用途 |
|---|---:|---|---|
| `ywy_sword_echo` | 24 | 否 | 普攻追剑兼容入口 |
| `ywy_zhenwu_wave` | 90 | 否 | 真武主刃与侧刃，修正旧 24 tick 外观配 90 tick 弹体 |
| `ywy_qi_impact` | 24 | 否 | 命中后的独立零伤害外观 |
| `ywy_taiji_counter` | 30 | 否 | 化劲反击掌压 |
| `ywy_wuxiang` | 60 | 否 | 四象剑阵 |
| `ywy_taiji_charge` | 60 | 是 | 蓄势跟随层，必须随动作取消清理 |
| `ywy_taiji_circle` | 48 | 否 | 剑圈跟随层 |
| `ywy_ultra_field` | 90 | 否 | 绝式场域层 |

`body_source.py` 已改为只消费上述冻结原素材，不再执行几何八帧效果生成。完整 production manifest 绑定 VFX manifest、原参考、source-contract 与新增 producer；完整视觉审核须明确批准相同 SHA 的 VFX 后，才能准备整批角色素材。

## 原生潜能 Texture 补齐

`PageActorPotential` 与关联预览会用独立 Texture 路径，而战斗潜能卡使用 atlas sprite。`portraits.py` 已为 `Potential_209001..209012` 增加 `UI/Texture/IconPotential/Potential_<pid>`，与既有 atlas 使用完全相同的自绘 96×96 源像素，补对应 metrics。它们是模组自绘潜能图标，不冒作《逸剑》原贴图。准备阶段同时核对十二条路径、尺寸、metric 和 atlas 原始像素一致。

## 同批身体曝光协调

六张原始 `SwordRightFlipbooks[0]` 图片已实际查看：源 key 0／1／2 都在蓄力，3／4／5 才向前伸剑。旧首剑只取前三张，完整播放也没有挥剑峰值；旧空连和剑气等权重分配也会令命中／发射早于前伸姿态。本批保留原 PNG、枢轴与原始 `1/10` 秒权重，另在 contract 与 production 写入明确的 BBEE `exact_ticks`，完整展示实际伸剑末姿态后再允许连段：

| 身体 clip | 源 key 顺序 | 每 key 的 60 Hz ticks | 最早连段 tick |
|---|---|---|---:|
| sword1 | 0,1,2,3,4,5 | 2,2,2,4,4,10 | 16 |
| sword2 | 2,3,4,5 | 3,7,7,11 | 20 |
| sword3 | 0,1,2,3,4,5 | 3,3,4,8,6,12 | 27 |
| air1 | 0,1,2,3,4,5 | 2,2,2,6,5,10 | 20 |
| air2 | 2,3,4,5 | 5,8,8,12 | 24 |
| zhenwu | 0,1,2,3,4,5 | 2,2,3,4,3,18 | 17 |

峰值接触图为 `E:\AAA MOD\bbee-mod-workbench\evidence\yuwen-yi\source-sword-six-poses.png`。源末帧是伸剑保持，不能冒称原版收剑动画。曝光已纳入本批原生结构读回，独立图像／tick QA正在补；实际连按仍须实机。

## 历史与待验

旧正式prepared此前未由素材任务覆盖；之后root已把55个文件按完整哈希归档到 [prepared-art-c7655a…](../../../../evidence/yuwen-yi/history/prepared-art-c7655acab1f753a2b5481cb4a4152d8ca83223f1b96a24be40d95d00b696d753.json)，仅移出owned `assets/prepared`后执行本批统一重备。旧全构建和工程收据继续保留。草稿 `collect.py`以及透明度／朝向调整前的候选均按manifest hash归档在 `evidence/yuwen-yi/history/`，没有改写为新结果。

root已看8种最终接触表及6张原剑姿势并批准 [同候选完整视觉审核](../../../../evidence/yuwen-yi/complete-art-visual-review-first-playtest-repair.json)，SHA256 `c6cf731e8e3fdf6d85c10add641fe476a06781d06de482018c6bb456af6df409`。本批prepare为52semantics／67动画束／293唯一可见帧，production SHA256 `872e2e0bab5061f444488df446670fd2df56388f06be84fd82e571ede5a110c1`。首轮弹体managed声明失败保留；修复后179包strict／repeat、事务及工作／基线／源各2,397hash通过，[工程总收据](../../../../evidence/yuwen-yi/engineering-acceptance.json)18阶段passed，新build为 `a85afaa34a33698b2719e232d37e90ce6f9ce8520fa63c4aea180db58ddf4a49`。

67时间线／434帧PPtr／293结构读回已完成，当前a85独立图像／UV／原始tex／tick／世界尺度QA及接触表正在补，旧62动画QA不套用。审核引用5张外部PNG交付漏装已补闭包，补修后141编译／291回归通过且native字节未变，未再次重建，见 [交付闭包收据](../../../../evidence/yuwen-yi/delivery-closure-acceptance.json)。左右朝向、侧刃、多剑气、取消残留、首领、出手／飞行／命中／消散、清晰度与性能仍按唯一清单实机；实际结果由 [acceptance.md](../acceptance.md) 持有，来源移植不冒称逐粒子无损或视觉已通过。
