# 宇文逸候选身体动作：引用链与读取实现

核对日期：2026-10-15。来源仍为主 PAK `E:\SteamLibrary\steamapps\common\Wandering Sword\Wandering_Sword\Content\Paks\Wandering_Sword-WindowsNoEditor.pak`，SHA256 `5e049dc376c36dacadf6edb6fab133942679b54b1809d7f483728deec35beaff`。本批只在内存读取明确引用的资源进行结构调查，再实现读取工具；没有生成新的提取文件、身体 PNG 或动作预览，没有运行新脚本、编译或测试。源游戏、既有 Mod、存档及旧九成员严格解码器未修改。

当前基础设施由根 agent 继续做统一实机/恢复验收。本文是身体参考工具的实现冻结与来源研究，不代表宇文逸已制作、动作已可用或人物图像身份已独立确认。

## 权威输入与选取规则

输入是此前明确选取的九成员 manifest：`E:\AAA MOD\bbee-mod-workbench\references\wandering-sword\20261015T122045Z-a69abc003aec\manifest.json`。其中 `NPCResources.uasset/.uexp` 由旧工具的固定成员 SHA256 合同重新核验；835行 DataTable 的 `Hero`、`Hero_WuDang` 各有146字段，选择范围由真实字段与槽号确定。

新工具必须显式选择 `--row Hero` / `--row Hero_WuDang`，可同时选择。每行默认读取左右 Idle、Run、FightIdle，轻功 SSStart/Loop/End，左右 Sword/Fist 第0槽，以及左右基础 Attack 的第一个非空槽。其他 Sword/Fist 槽只在重复指定 `--sword-slot` / `--fist-slot` 时加入；每类最多8个明确槽，不能“一次取所有动作”。语义标签始终是字段/槽号，不把剑第0槽自动叫真武剑气、太极剑，也不把 `QT` 某槽凭名字叫受击。

每个根必须经真实对象链闭合：NPC字段 soft reference → 具体 `PaperFlipbook` export → `KeyFrames` 中实际 Sprite ObjectProperty → 具体 `PaperSprite` export → 实际 `BakedSourceTexture` → `Texture2D` native 像素。引用的 Sprite/Texture 路径必须处于显式选定 Hero 行目录；未知外部依赖停止。只读取这些包的 `.uasset/.uexp`，不遍历素材目录，也不整 PAK 解压。

## 已直接读到的真实结构

以下来自已核验现有 PAK reader 的内存读取，不是新采集脚本的执行结果。

| 对象 | 实际 class/结构 | 当前可确认的内容 |
|---|---|---|
| `Hero/PFB_TY_Hero_I_L` | `PaperFlipbook` | 4个 KeyFrame，FPS=2；Sprite实际指向 `Hero/Sprite/role01_Sprite_0..3`，不是按图片名扫描得来。 |
| `Hero/PFB_TY_Hero_Sword_L` | `PaperFlipbook` | 8个 KeyFrame，FPS=12；实际 Sprite 引用为 `Hero/Sword/atk_Sprite_18..25`。 |
| `Hero/PFB_TY_Hero_Fist_L` | `PaperFlipbook` | 7个 KeyFrame，FPS=10；实际 Sprite 引用为 `Hero/Fist/atk_Sprite_7..13`，末 key 的 FrameRun=2。必须使用 FrameRun/FPS，不能只按7张图片均分。 |
| `Hero_WuDang/PFB_TY_Hero_WD_I_L` | `PaperFlipbook` | 4个 KeyFrame，FPS=2；引用 `Hero_WuDang/Textures/Hero_WuDang_Sprite_0..3`。 |
| `Hero/Sprite/role01_Sprite_0` | `PaperSprite` 为 export1；export0 是 BodySetup | BakedSourceDimension=26×38，PPU=1，6个 BakedRenderData 顶点；BakedSourceTexture 实际指向 `Hero/Sprite/role01`。读取目标必须按 class/name 解析，不能默认 export0 是图像。 |
| `Hero/Sword/atk_Sprite_18` | `PaperSprite` 为 export1 | SourceUV=(0,100)，Dimension=142×50，PPU=1，6个渲染顶点；实际纹理 `Hero/Sword/atk`。 |
| `Hero_WuDang/Textures/Hero_WuDang_Sprite_0` | `PaperSprite` 为 export1 | Dimension=26×38、PPU=1、6个顶点；实际纹理 `Hero_WuDang/Textures/Hero_WuDang`。 |
| 三个实际引用的纹理 | `Texture2D` | 都是 `PF_B8G8R8A8`、单 cooked mip、bulk flags=0x48、内联未压缩 BGRA8，无 `.ubulk` 伴随项。`role01` 与武当站立 atlas 为156×304，基础剑 `atk` 为1278×600。 |

可回查的部分原始成员 SHA256：

- `Hero/PFB_TY_Hero_I_L.uasset`：`43eed3308e5dccfedb0f8fe60c691e8c7e519b64aa40c41ac3c8d202ffab2c1f`；`.uexp`：`c1f2056aedf2c824bbecd3bd95fc45f67f85b0bf3511a35e153a4eff826a0a01`。
- `Hero/PFB_TY_Hero_Sword_L.uasset`：`7f38beca8fe57c2b671c37f7943ce213ffb5cbd1cc3a160042f7669688711683`；`.uexp`：`625e87d75d9ea0e79ff54f31bc1e47d339ad67c6162aeabf5e386310910c3f24`。
- `Hero/Sprite/role01.uasset`：`9f9f7a127f7b4e5c5f4eedda1fe677216eaaa4a745a5803bd695563a87553203`；`.uexp`：`115a01952eac39f50b1afb298df69aec050ba568b2b7840eb16ccb8ffb63d857`。
- `Hero/Sword/atk.uasset`：`18687df261e710818254b834e9c252b884eccf2c92c5a3d7b00722919e9956cd`；`.uexp`：`e2b43d90207c6b543944bd245fd2caa7a3f9c0885787f2b06aa967b54cbb26bc`。

## 帧时长、锚点和图片范围

[Epic 的 KeyFrame 定义](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/Paper2D/FPaperFlipbookKeyFrame)包含 Sprite 与 FrameRun；[Epic 源码镜像的 Flipbook 实现](https://github.com/folgerwang/UnrealEngine/blob/release/Engine/Plugins/2D/Paper2D/Source/Paper2D/Private/PaperFlipbook.cpp)按所有 FrameRun 之和除 FPS 计算时长。镜像为2019年的较早 UE4 源码，不能当作当前4.26全部代码一致的证明；本次每个对象仍以实际序列化结构为准。仅对省略的已知 native 默认值采用 FPS=15、FrameRun=1，并在输出中明确标记，不从技能名猜时长。

[Epic 的 Sprite API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/Paper2D/UPaperSprite)明确 BakedRenderData 是相对 pivot 的世界 XZ 与归一化 UV 四元组。解析器保留全部实际顶点，并对每个顶点同时解：

```text
texture_x = world_x * PixelsPerUnrealUnit + absolute_pivot_x
texture_y = absolute_pivot_y - world_z * PixelsPerUnrealUnit
crop_pivot = absolute_pivot - BakedSourceUV
```

所有顶点必须得到一致 pivot；旋转/skew UV、越界或不一致停止。这样能恢复真实锚点，不把中心或脚底作为默认猜测。裁片保留完整 BakedSourceUV/Dimension 声明区域及透明像素，不重新裁紧或自动补帧。若 BakedSourceUV 标签省略，按该 native UObject 的零值使用(0,0)并标记；[Epic 对 UObject 初始化/省略默认属性的说明](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-object-handling-in-unreal-engine)和上述源码镜像是默认值来源。仍要在集中执行时核对所有实际顶点与 atlas 边界。

输出帧 JSON 保存 float32 FPS、FrameRun、精确分数时长、PPU、原始顶点和浮点 pivot。APNG 只作预览，按毫秒舍入，不能替代精确动作时序。只有 pivot 差值可整像素对齐、PPU一致时才建立统一预览画布；不做模糊缩放来掩盖半像素问题。无法对齐则保留原始 PNG/元数据并明确预览未完成。预览重新解码检查像素与总时长，但所有视觉验收仍待根 agent 统一执行后观察。

首轮集中采集实际遇到 `APNG preview has no frame duration` 后停止，并已清理该次独占输出。根因从本机已安装的 Pillow `PngImagePlugin.py:1239–1252` 确认：连续相同帧会合并，最终只剩一个视觉状态时写成普通 PNG，不包含动画控制与 duration。新修复显式保留源 key/FrameRun 原序列，按像素相同的连续状态形成预览段；仅一个视觉状态输出 `representation=static_png`，真实总时长、精确分数与原 FrameRun 放在 `body-reference.json` sidecar，PNG 本身不假装存了动画时长。多个视觉状态仍必须是真 APNG，并严格回读帧数、逐帧像素、每帧毫秒及总时长。没有插入假帧、标记像素或放弃多帧时序检查；静态与动画预览分别计数。修复源码再次冻结，留待根 agent 统一编译、采集和回读，本 agent 未运行新实现或测试。

原始材质可能为 Masked/MI_JHMaskLitSprite；工具只输出原 texel 与几何参考，不复制原游戏 shader、灯光、网格裁切、物理或碰撞逻辑。因此不能把这些透明源裁片称为完全复现原游戏渲染。

## 明确缺口

1. NPCResourceSetting 的146字段没有 Hurt/HitReaction/Damage/Injury 对应字段；两行四向 `Died*Flipbook` 都为 `None`。本批没有可靠的受击/倒地素材入口，不用名字相近的 QT 动作冒充。BBEE 未来可以复用原生物理状态逻辑，但角色受击/倒地美术缺帧仍须补齐。
2. 身体、左右朝向、攻击/轻功连贯性尚未看图。现有头像的黑发青年与金/蓝衣装已由根 agent 观察，但 NPC 身份主表与官方图像对照尚未闭合；本批不无限扩大身份研究。
3. 来源字段能证明剑/拳类别，不能证明某个槽就是太极剑、真武剑气或流云太极拳；对应技能到动作的运行时映射仍待研究。
4. 跳跃轨迹、空连、受击硬直、命中帧、FX、声音、翻面、取消与 BBEE 资源绑定都属于后续角色实现，本参考工具不创建这些行为。
5. 只支持本次实际观察的版本/属性、inline BGRA8 和轴对齐 Sprite。外部 bulk、其他压缩纹理、多个材质区、Sockets/附加纹理、未知属性或本地视觉 cross-export 引用停止，不能关闭检查绕过。

## 冻结实现与集中执行入口

新文件为 `scripts/wandering_character_parser.py`、`scripts/wandering_character_reference.py`。未修改原 `wandering_reference.py`、`wandering_decode_reference.py`，九成员固定输入合同保持不变。新工具重新读取固定主 PAK 全哈希、三索引哈希与每个所选成员存储 SHA1，通过原有路径/链接/加密/未知压缩边界，结果只写入工作台 `references/wandering-sword/` 的独占新目录，失败只清理本次输出。

硬限制：最多64动作根、512 Sprite、32 atlas、1,024 raw成员、256 MiB raw、128 MiB atlas像素、128 MiB裁片像素；每个 APNG 预览内存64 MiB。没有覆盖或批量全解压参数，无新依赖安装。输出包含 raw成员、原分辨率atlas、逐Sprite透明PNG、真实引用链/时长/pivot JSON、APNG和离线preview.html、完整来源manifest；`visual_acceptance=pending`、`bbmod_ready=false` 是固定真实边界。

全部源码完成后由根 agent 集中编译、执行和验收，例如使用工作台的已核验便携 Python：

```powershell
& 'E:\AAA MOD\bbee-mod-workbench\ZenithTerminal\Interpreter\pythoncore-3.14-64\python.exe' -E -s 'E:\AAA MOD\bbee-mod-workbench\scripts\wandering_character_reference.py' --raw-manifest 'E:\AAA MOD\bbee-mod-workbench\references\wandering-sword\20261015T122045Z-a69abc003aec\manifest.json' --row Hero --row Hero_WuDang
```

集中验收应核查引用闭合/字节与PNG回读、实际FrameRun时序、左右方向、裁片/pivot稳定、受击/倒地缺口，以及重新打开离线预览后的动画表现。结构成功不自动改为视觉通过；若工具遇到未研究的实际布局，保留具体失败证据，修复后再冻结整批，不逐个小功能跑遍工程。

## 2026-10-15 正式采集与角色资产适配批

根 agent 的集中执行已生成 `E:\AAA MOD\bbee-mod-workbench\references\wandering-sword\20261015T133053Z-487eeab89890\manifest.json`（SHA256 `c53f67f143e03b8cbb598671368de13f241e2dcfb60870bc8c9a054c46f253dc`）。独立执行 agent 回报21组校验通过：378 raw成员6,784,626字节、11 atlas、142 sprites、36 flipbooks、146 keyframes、30 APNG及6 staticPNG；569个输出回读哈希、逐像素/时长/pivot校验通过。正式结果记录 `evidence/yuwen-yi/body-reference-validation.json`。本记录引用集中执行汇报；不把工具结构通过替代根 agent 的身体连贯性视觉验收。原作受击/死亡六项来源缺口仍保持，后续补制不改称原作已有动作。

角色主形象已由根 agent 选择 `Hero_WuDang` 蓝衣，正式 contract 的47个 semantic clips和16个过场alias由 gameplay agent 持有。新增 `mods/char-yuwen-yi/body_source.py`、`body_clips.py`、`import_yuwen.py`、`portraits.py` 仅承担参考/作者素材到原生网格、纹理、动画和UI的适配。准备阶段一次覆盖全部动作并按合同60 Hz精确重定时；剑攻击分段、轻功对应jump/drop/dash以及拳式对应太极/绝式均明列为BBEE改编，不声称原作槽位就是某一具名武学。

原生受击、空中受击、翻落、横卧、起身、死亡以及crouch/guard_charge/meditate/salute十个补制序列由根 agent 生成、独立执行 agent受控拆分，仍待完整视觉审阅。适配映射保留来源：squat用crouch前两帧（合同2 ticks），squat_loop用最终蹲姿，squat_to_stand逆序；charge用guard_charge，heal用meditate，pose/summon用salute。补制帧必须有逐文件SHA256、锚点、非空RGBA和来源说明；未完成时硬失败，不允许透明帧或donor外观兜底。身体统一整数放大8倍，按原作站立真实alpha高度标定1.8 native world units，全部动作同一尺度；原始Sprite pivot恢复值保留并拒绝真实非整像素锚点的静默取整。

`ywy_sword_echo`、`ywy_wuxiang`、`ywy_taiji_counter`三项是原生弹体特效，分别由独立几何剑气刃、旋转八剑范围阵、化劲拳劲冲击环组成，均不包含人物像素。角色拳攻击由taiji_fist/body动作承担，counter弹体不能使用完整角色身体飞出。三类特效均标记D改编与生成源码来源，合同tick不变。

`import_yuwen.py --prepare --portrait-manifest <正式画像manifest> --authored-manifest <assets/authored-poses.json> --visual-review <根agent视觉审阅JSON>` 只准备 `assets/prepared/`，要求该独占目录尚不存在，失败只清理该目录。准备结果冻结输入、代码、所有像素与锚点、UI排版、动作计划的哈希。构建模式 `all --out <BBMOD_OUT> --adds <private-temp-json>` 只消费冻结输入，预先逐帧回读共享rig cache；不触碰source game、mod.json、contract、全局manifest或角色generator。构建后必须读回全部bundle及动作真实Indeces/TotalFrameCount，再交父构建的完整引用闭合验证；这些实现源码本 agent 未逐项运行测试，统一交根 agent 编译、构建、验收。

画像新批 `scripts/wandering_character_portrait_reference.py` 仍使用原九成员fixture的实际NPCResources根，只选择Hero/Hero_WuDang的TeamImage（900×835）、DlgImage（500×534）、FightImage（173×173）及其uasset/uexp、简体Npc.locres、NPCs主表raw成员共15项。只读原文研究已见Npc.locres namespace `NPCs` 的`0_Name`和`1_Name`均为“宇文逸”，与Hero.Id=0/Hero_WuDang.Id=1形成明确ID对照；主表资源关系尚未解码，不能省略这个范围。NPCs主表flags `0x80040000`比旧profile多本地化采集位，旧decoder继续严格拒绝；[Epic EPackageFlags官方定义](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/CoreUObject/EPackageFlags)说明该位为PKG_RequiresLocalizationGather。新工具保留主表raw但不放宽旧profile。

画像适配使用真实Team/Dialog/Fight图并保持比例；900×835 Team构图不得宣称完整身体立绘。UI原生尺寸必要时只补透明边到4像素块倍数，不能把145头像放大伪称大图。根 agent 需要看原图并测量face_x/top/floor，绑定正式画像、身体和补制manifest后才可批准准备。潜能209001～209012、天赋209080以及Qi/Taiji/Guard共16图标为独立几何绘制，每图96×96，原生atlas由gameplay descriptor的atlasSprites明确使用这些PNG；总atlas只用于预览，避免重复生成一套纹理资源。所有UI slots、Head/EvoHead/Off/PDA/banner/skill aliases、metrics及12个portrait offset keys必须齐全，缺图停止。

画像采集正式目录为 `references/wandering-sword/20261015T134637Z-890830ca3a1f/`，manifest SHA256 `aae6004559b0fa63b16e2ecfa7ffe1f24d5e25cf02561bc191012234ddb43df5`。根 agent 授权后的集中验证收据为 `evidence/yuwen-yi/portrait-reference-validation.json`：12组检查通过，包括15raw成员30,293,659字节、22输出完整集合与哈希、6PNG从原包BGRA重新逐像素解码对照、4,586 locres条目和两行身份ID对照、全部reader源码SHA；当前源PAK重新核对footer/三索引SHA1与15个所选压缩payload SHA1/解压raw一致，文件identity前后未变。整PAK SHA256明确继承本次冻结采集，不声称验证阶段又重读了6GB。NPCs主表raw已核对但未越界解码其属性。

蓝衣Team透明通道原文检查：Alpha=0有543,057像素，其中542,972个存在非零RGB；这是原图隐藏颜色，不是背景未抠除。BGRA转换保留第四字节alpha，PNG回读包含隐藏RGB的全部RGBA字节；不能用RGB smear判断不透明。原生900×835半身图带下缘渐隐，padding到900×836时metrics和offset计算同步用新高度。Pillow现有RGBA LANCZOS实现先转换RGBa预乘再重采样，之后转回RGBA并alpha_composite，不让全透明RGB污染缩放边缘。可见发顶以alpha≥128为65像素；渐隐底用alpha≥8为784、alpha≥4为793，完整非零alpha到801。面部中线由根agent视图量测为458，不能把渐隐底误称脚底。

根 agent 另获授权的原生视觉接触表为 `evidence/yuwen-yi/body-native-wudang-contact-sheet.png`（64唯一sprites）和 `body-native-wudang-flipbooks.png`（18个真实来源动作，保留key顺序/FrameRun标注）。仅对已验证原图进行NEAREST×2、checker合成和来源/pivot标签，不制作新姿势、不宣称原生动作具备补制的受击/死亡内容。新补制40帧的批准和角色prepare/build属于另一整批。
