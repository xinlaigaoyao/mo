# 《逸剑风云决》本地参考素材可行性

核对日期：2026-10-15。来源目录：`E:\SteamLibrary\steamapps\common\Wandering Sword`。本轮仅进行目录清点、文件哈希、EXE 内引擎分支字符串和 PAK 元数据读取；没有启动游戏、UE4SS 或第三方工具，没有安装工具，没有提取资源，也没有读写存档。

**后续进展更新：**上述首轮只读调查之后，根 agent 已统一验证参考工具并实际选取九个成员，再统一验证解码工具；当前正式输出见文末“已完成的限定解码”。历史冻结段落记录当时本 agent 没有运行工具，不代表当前仍未导出/解码。仍未启动《逸剑风云决》、安装新解析器或修改源游戏/存档。

## 已确认的来源边界

目录共 51 个文件、6,202,659,534 字节。全部文件的相对路径、大小与 SHA256 已记录于 `E:\AAA MOD\bbee-mod-workbench\evidence\yuwen-yi\local-source-inventory.json`。该清单是本机核对快照，不是 Steam 原版认证。

现有目录含 UE4SS、`CompareDropAll`，以及两个覆盖 PAK：`Wandering_Sword-WindowsNoEditor_XunYaoYao_P.pak`、`Wandering_Sword-WindowsNoEditor_ZiYongLiHui_P.pak`。第二个覆盖包挂载于 `JH/Characters/Image/`，会影响立绘参考。因此后续素材研究应显式选择主 PAK，第三方覆盖内容另列来源，不能把修改后的游戏画面默认当原作。

主程序 `Wandering_Sword\Binaries\Win64\JH-Win64-Shipping.exe` 的只读字符串包含 `++UE4+Release-4.26`；文件版本资源为空，尚未确认具体 4.26.x 补丁号。未发现 `.utoc` / `.ucas`；当前安装使用传统 PAK 路线。

## PAK 库存与加密状态

| 包 | 字节 | 索引项数 | 用途 |
| --- | ---: | ---: | --- |
| `Wandering_Sword-WindowsNoEditor.pak` | 5,954,388,501 | 289,441 | 主游戏 |
| `Wandering_Sword-WindowsNoEditor_XunYaoYao_P.pak` | 106,658 | 28 | 第三方覆盖，挂载荀杳杳纹理目录 |
| `Wandering_Sword-WindowsNoEditor_ZiYongLiHui_P.pak` | 41,918,080 | 274 | 第三方立绘覆盖 |
| `CrashReportClient.pak` | 11,530,697 | 2,285 | 崩溃报告工具，不用于角色参考 |

四包均为 PAK v11。主索引、路径哈希索引及完整目录索引均与包内 SHA1 一致；索引未加密，GUID 为零。逐项读取压缩编码索引的加密位，四包均为零；声明的压缩槽仅有 Zlib。这个结论来自元数据，尚未验证所有 payload 解压或资源反序列化，不需要寻找 AES 密钥。

主 PAK SHA256：`5e049dc376c36dacadf6edb6fab133942679b54b1809d7f483728deec35beaff`。主包包含 141,812 个 `.uasset`、142,563 个 `.uexp`、2,732 个 `.ubulk`、751 个 `.umap`、35 个 `.locres`。目录中没有独立松散的角色 PNG、音频或技能 CSV；包内 283 个 PNG 的存在不代表角色动画已经是可直接使用的图片。

PAK 布局依据开源解析器的[尾部读取](https://github.com/trumank/repak/blob/master/repak/src/footer.rs)、[二级目录索引读取](https://github.com/trumank/repak/blob/master/repak/src/pak.rs)与[编码项加密位读取](https://github.com/trumank/repak/blob/master/repak/src/entry.rs)核对。本轮没有下载或运行该解析器。

## 已定位的参考入口

以下均为主 PAK 内路径，省略共同前缀 `Wandering_Sword/Content/`。路径仅证明资源存在，不能单凭文件名确认视觉身份、技能数值或运行效果。精确候选清单由 `E:\AAA MOD\bbee-mod-workbench\evidence\yuwen-yi\local-targeted-reference-index.json` 持有。

| 研究目标 | 路径入口 | 当前证据 |
| --- | --- | --- |
| 主角本体候选 | `JH/Characters/TongYong/Hero/` | 4,634 个 `.uasset`；有 Char、Sword、Fist 等候选动画/纹理命名，待导出后认图 |
| 武当服装候选 | `JH/Characters/TongYong/Hero_WuDang/` | 4,411 个 `.uasset`；有 `Sword/taijijian`、`Fist/taijiquan` 命名 |
| 其他主角形态 | `Hero_MengZhu/`、`Hero_ZongShi/`、`Hero_Boy/`、`Hero_GongZhu/` | 目录名存在，尚未确认各形态在原作中的身份/用途 |
| 立绘 | `JH/Characters/Image/T_Hero_HeadImage*.uasset`、`T_Hero_WuDang_HeadImage*.uasset` | 主包候选；不要被本机立绘覆盖 PAK 替换 |
| 流云太极 | `JH/Skills/WD_N_LiuYunTaiJi/` | `GA_WD_N_LiuYunTaiJi`、`GE_QiXueHuDun_LYTJ`、`GE_YuanZhuanTaiJi`、`GE_LiuYunTJQ-J` 等名存在 |
| 流云太极剑 | `JH/Skills/WD_J_LiuYunTaiJian/` | `GA_WD_J_LiuYunTaiJian`、对应 `GE` 存在 |
| 流云太极拳 | `JH/Skills/WD_Z_LiuYunTaiQuan/` | `GA_WD_Z_LiuYunTaiQuan`、`GE_YiJingZhiDong` 等名存在 |
| 太极剑法 | `JH/Skills/WD_J_TaiJiJianFa/`、`22_TaiJiJianFa/`、`N_WD_J_TaiJiJianFa/` | 多套实现/版本候选，不能未经引用解析任选一套数值 |
| 真武剑气 | `JH/Skills/WD_J_ZhenWuJianQi/`、`56_ZhenWuJianQi/` | GA/GE、Damage、Cost、CD 等名存在 |
| 梯云纵 | `JH/Skills/WD_Q_TiYunZong/`、`JH/Characters/TongYong/Hero/Char/tiyunzong*` | 技能、动作点/闪避命名与主角图像候选存在 |
| 技能/心法效果 | `JH/Tables/Skills.uasset`、`Buffs.uasset`、`JingMais.uasset` | 表资源存在，尚未反序列化 |
| 主角映射/皮肤 | `JH/Tables/NPCs.uasset`、`NPCResources.uasset`、`Skin.uasset` | 可用于确认 Hero 与宇文逸的实际绑定 |
| 中文技能文本 | `Localization/Skills技能表/zh-Hans/Skills技能表.locres` | 本地简体文本入口存在 |
| 原作音效 | `JH/Audio/Skill/JianFa/103_真武剑气*.uasset`、`105_太极剑法*.uasset`、`QingGong/702_梯云纵.uasset`、`XinFa/802_太极神功-大招版.uasset` | 中文命名存在；未导出、解码或试听 |
| 太极视觉候选 | `JH/ParticleSystem/DZ_Effects/TaiJi/` 等 | 本次精确筛选 31 个相关 FX `.uasset`，待解析依赖确认 |

宽泛名称搜索会误中 `DiaoYuWen`、`taijie` 等无关资源。`local-asset-candidates.json` 仅作搜索记录；后续使用上述 focused index，不能把“包含 YuWen”当成宇文逸身份确认。

## 后续最小提取路线

1. 基础设施真实加载验收通过后，先从已锁定 SHA256 的主 PAK 按白名单读取 `NPCs/NPCResources/Skin/Skills/Buffs/JingMais` 与简体技能本地化，确认主角映射、技能引用和文本。保留包路径、条目路径、原始字节哈希、解析器版本和失败记录。
2. 先导出 `T_Hero_HeadImage` 与 `T_Hero_WuDang_HeadImage` 两个可视样本，认图后决定主角服装。再按实际引用取对应纹理、Sprite/PaperFlipbook 候选及其 `.uexp/.ubulk` 伴随文件，不整包解压。`PFB`、`SPR`、`_Sprite_` 命名强烈提示序列帧路线，但实际类、帧序、帧时长、切片和锚点仍需读取确认；[Epic 的 Flipbook 文档](https://dev.epicgames.com/documentation/en-us/unreal-engine/paper-2d-flipbooks?application_version=4.27)说明这些是动画的重要组成，不能只取得纹理就算动作完成。
3. Unreal 资源转入 BBEE 的 Unity 管线，需要明确透明通道、角色朝向、像素密度、脚底/受击锚点、帧序与时长、攻击判定、位移和 FX 触发点。原作图像可作来源，Unity 动作状态与资源引用必须重新绑定；原作技能数值也不能直接等同 BBEE 强度。
4. 当前限定的 `E:\AAA MOD\tools`、工作台 tools 及工作台 downloads 中未发现 UnrealPak、repak、FModel、UModel、CUE4Parse 或 QuickBMS 可用工具。已按后续授权实现 `E:\AAA MOD\bbee-mod-workbench\scripts\wandering_reference.py` 的无依赖、无执行入口 PAK v11 读取工具；见下文冻结状态。UE 资源解析可再评估 [CUE4Parse](https://github.com/FabianFG/CUE4Parse) 的 `UTexture2D`、对象 JSON 与 `USoundWave` 转换路线，或 [FModel](https://github.com/4sval/FModel) 的预览界面。上游功能存在不代表本机《逸剑风云决》已兼容，任何新增依赖应先核对来源、锁版本/哈希和实际价值，再置于工作台。
5. 将所有所需素材处理及角色实现完成后，统一执行帧动画/引用、完整构建、安装回退与实机强度验收。本轮没有逐个候选运行测试，也没有留下提取临时产物。

## 尚未满足的条件

当前已完成精确索引、九成员选取、两张 BGRA8 小头像解码、835行 NPCResources 读取与1,506项中文技能文本解码；还不能扩展为所有资源格式兼容。完整身体/立绘、Paper2D 实际对象布局、帧数/锚点、人物外部身份对照、Skills/Buffs 实际字段/值、GA/CDO 机制和音效试听均未验收。当前成果属于可追溯参考库存及限定解码，不应称为宇文逸完整素材完成或角色已制作。

## 参考读取工具的实现冻结状态

`scripts/wandering_reference.py` 已实现，**本 agent 未编译、未运行新工具、未做真实 selected extract**，留待本轮所有实现冻结后统一验证。上文库存来自此前只读调查，不能拿来代替新工具通过验收。

CLI 固定主 PAK 路径和上述 SHA256；`inventory` 只输出统计，`find` 只做文字子串检索。`extract` 必须逐项给出精确 `--member`，没有批量全部提取选项、AES 参数、来源替换参数或覆盖开关。仅在工作台 `references/wandering-sword/` 中建立独占的新目录，不自动增加 `.uexp/.ubulk` 伴随文件。

实现门禁包括源完整哈希与读取期文件身份、三组索引 SHA1、路径穿越/Windows 保留名/链接与 junction 拒绝、成员数与字节限制、未知格式/压缩/加密拒绝、索引与 payload header 一致、连续压缩块、存储 payload SHA1、逐块 Zlib 长度/结束/尾部检查、导出后字节数与 SHA256 回读。失败时只清理本次独占输出目录。默认最多 64 个明确成员，每成员 16 MiB、总解压 64 MiB，可显式提高到每成员 256 MiB、总计 512 MiB 的硬上限；整个目录清点有独立元数据限制。

该工具只导出 Unreal 原始成员和来源 manifest，尚不解析 `.uasset` 对象，不输出可直接导入 BBEE 的图片/动作/音频。payload SHA1 根据 PAK 压缩后存储字节计算；参考[上游数据写入实现](https://github.com/trumank/repak/blob/master/repak/src/data.rs)，不把压缩前 SHA1 与存储 SHA1 混淆。

## 九成员选取后的结构研究

根 agent 在集中验证阶段实际运行了上面的读取工具，九个明确成员已导出至 `E:\AAA MOD\bbee-mod-workbench\references\wandering-sword\20261015T122045Z-a69abc003aec\`，共 10,050,762 字节。来源与字节哈希由该目录 `manifest.json` 持有。本 agent 随后只读检查这九个 raw 文件，形成 `E:\AAA MOD\bbee-mod-workbench\evidence\yuwen-yi\selected-member-structure.json`。

两张 `T_Hero(_WuDang)_HeadImage` 经 Import/ExportMap 确认是真 `Texture2D`；native 结构为 145×145、单 mip、`PF_B8G8R8A8`、内联未压缩 84,100 字节。这是小头像，不能当完整立绘或身体动作。尚未在本 agent 中解码为 PNG 或认图。

四份 `.uasset` 存储的 UE4 package version 都为 0，但 flags 为 `0x80000000`，没有 `UnversionedProperties` 标志；实际字节带 FName/type/size/property-guid 等属性标签。因而不能把“package version 未存储”误写为“属性无版本、必须找 usmap”。本次支持仍明确限定到 UE4.26 的实际结构与已锁定成员 SHA256。[Package summary](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Objects/UObject/FPackageFileSummary.cs)、[属性标签](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Assets/Objects/FPropertyTag.cs)与[标签附加类型](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Assets/Objects/FPropertyTagData.cs)是布局对照来源。

`NPCResources` 的实际 class 为 `DataTable`，`RowStruct` 指向 `/Script/JH.NPCResourceSetting`。835 行属性标签走读与 export 结尾精确吻合。类型只有 Int、Bool、SoftObject 和 Array，71,810 个数组的 inner type 全是 SoftObject；因此可以用确定布局读取主角两行的动作引用，不必先安装大型解析器。`Hero`、`Hero_WuDang` 行已经有明确 `HeadSprite`、Idle/Run/FightIdle 与轻功起始/循环/结束 Flipbook 的 soft reference；这是表字段关系，仍未读取 referenced flipbook 的帧与图像。[DataTable 上游读取](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Assets/Exports/Engine/UDataTable.cs)与实际边界一致。

中文技能 `.locres` 为标准 version 3，声明 1,506 个项、1 个 `Skills` namespace、1,435 条去重字符串，字符串数组位于 50,152。完整文本解码仍待新工具统一验证；读取路线按照[本地化资源](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Localization/FTextLocalizationResource.cs)、[文本键](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Objects/Core/i18N/FTextKey.cs)、[去重字符串](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Objects/Core/i18N/FTextLocalizationResourceString.cs)布局。

新实现 `E:\AAA MOD\bbee-mod-workbench\scripts\wandering_decode_reference.py` 绑定这九个成员的实际 SHA256，只用现有 stdlib/Pillow，输出两张原始分辨率 RGBA 头像、两个主角 mapping 行、原作中文技能文本及 focused 文本索引。结构不匹配、余字节、不同格式、外部 bulk、无标签属性、未知 NPC 字段类型等都停止，不猜 offset 或扫描图片头。输出仅到新建 reference 目录并带来源 manifest。**本 agent 已冻结源码，未编译、未运行新 decoder 或测试**；此处结构研究不代替新 decoder 验收，也不代替导出后实际认图。

头像布局参考 [UTexture](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Assets/Exports/Texture/UTexture.cs)、[TexturePlatformData](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Assets/Exports/Texture/FTexturePlatformData.cs)、[Mip](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Assets/Exports/Texture/FTexture2DMipMap.cs)与 [BulkDataHeader](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/UE4/Assets/Objects/FByteBulkDataHeader.cs)。未来处理通用纹理、外部 bulk 或 Paper2D 时，再评估专门解析器；本次不新增依赖，也不把小头像解码能力扩写成完整角色资产能力。

## 已完成的限定解码

根 agent 随后实际运行新解码工具成功，输出 `E:\AAA MOD\bbee-mod-workbench\references\wandering-sword\20261015T124534Z-a62a5e5c879d`，其中 `manifest.json` 绑定九个 raw 成员的 SHA256、源码与输出哈希。`hero-resource-mapping.json` 完整读取835行，只保存 `Hero`、`Hero_WuDang` 两行；`skill-text.json` 有1,506项，`skill-text-focus.json` 包含流云太极、拳剑、云相太极、太极神功、梯云纵和真武剑气原文。本文已读取这些正式 JSON，具体技能原文与移植条件归入 [combat-references.md](combat-references.md)，避免在两个研究文档重复维护效果正文。

`T_Hero_HeadImage.png`、`T_Hero_WuDang_HeadImage.png` 都保留145×145原始分辨率与RGBA像素。根 agent 已通过 `view_image` 观察到同一黑发青年在金色/蓝色衣装下的透明小头像；这属于已观察的图片内容。两图分别对应 NPCResources 的 `Hero.HeadImage` 与 `Hero_WuDang.HeadImage` 字段，但尚未与外部官方人物图像或身份表交叉，故不单靠资产命名把图像人物身份宣布为已完成独立确认。

资源映射仍有明显空槽：两行的剑左右数组各62槽，Hero各15个、Hero_WuDang各14个有效引用；拳左数组各62槽、22个有效引用。左右剑战斗待机3槽只有1个有效，上下剑战斗待机全空；轻功起跳/落地3槽有2个有效、1个空。槽数不等于动画数量或帧数，也不证明被引用的 PaperFlipbook 对象已经导出、识别或适合横版操作。

这次进展将“中文原文只知道路径”升级为“已确定结构解码”，将“Hero目录候选”升级为“真实表字段引用与两张小头像”；技能实现数值、原作实际效果、完整身体动作、技能FX、音效和 BBEE 角色运行仍是另外的验证范围。本次文档同步没有新增实现、提取、编译或测试。
