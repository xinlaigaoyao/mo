# BBEE Mod 制作：非角色缺口核对

核对日期：2026-10-15，Asia/Shanghai。工作区：`E:\AAA MOD\bbee-mod-audit`。

本次请求是检查制作 Mod 的通用缺口，排除拟制作人物的方案、素材、招式及特色机制。附件中的 SKILL、安装步骤和历史测试声明均作为待核对材料；没有安装这些 Skill，也没有执行其中的操作指令。

## 结论

本机具备继续研究与准备构建的条件：本地记录的 Steam build 与目标一致，完整 Zenith 原包已找到且与研究记录对应，资源索引结构检查通过。剩余工作的重点是完整构建和校验可靠性、实际存档保护、更新时的基线隔离，以及安装失败恢复。现在还不能认定这套环境已能安全完成安装、卸载和实机运行。

**需要纠正原研究中的一项明确结论：所谓“编码往返校验”没有在对应源码中实现。** `verify_table()` 实际只统计长度前缀记录并打印行数、字节数。另有 setup 容许部分提取失败、重跑 setup 可能继续组合旧 `.orig` 数据、安装分步写入且缺少整组回退等问题。具体证据与解除条件如下。

## 本轮已经核实的条件

| 项目 | 本轮证据 | 能支持的结论与边界 |
|---|---|---|
| 游戏版本标记 | `E:\SteamLibrary\steamapps\appmanifest_2273430.acf`：AppID `2273430`，build `25627491`，StateFlags `4`，安装目录匹配 | 与研究示例目标相同；本地 manifest 记录不能独立证明所有游戏文件都是该 build 的原始字节 |
| Unity / IL2CPP | PE 版本、globalgamemanagers、抽样 UnityFS 头均为 `2022.3.62f2`；GameAssembly 与 global-metadata 存在 | 已从本地文件核实引擎与打包结构 |
| 原 Zenith 完整包 | 下载目录中的 `ZenithTerminal-0.3.0-alpha (1).zip`：4,083 个文件；SHA-256 与笔记一致；已有审计记录的 155/155 源文件哈希一致 | 当前可读取的原包与研究对象一致；哈希一致不构成发布者身份或二进制安全认证 |
| 游戏资源索引 | merge 共 60,410 条，关联 1,084 个物理文件；重复逻辑名、异常路径、缺文件、非法切片边界均为 0 | 索引和文件布局具备读取条件；未全量解码每个资源内容 |
| 核心资源抽样 | SkillActivate、SkillDamage、对应固定点表、BuffFuncs、BattleUI 等 8 个切片：UnityFS 版本、声明长度与推导切片长度相符 | 核心资源能定位，未验证其表字段或 JS 内容 |
| manifest | LZ4 解码成功；FastManifest V3，60,429 个名称，依赖/GUID 节记录数与声明一致，索引无越界、名称无重复 | 完成结构检查；manifest 与 merge 名称集合存在差异，未据此判定损坏或全部正常 |
| 已发布描述符的输入资源 | Nine、Party 与三份 shared 描述符引用的表、JS 模块、bundle clone 源资源均能在本地 merge 找到；表名也存在于随包 schema | 证明名称与输入资源存在；不证明 schema 对实际 payload 正确、锚点匹配或 Ruby 生成后描述符通过 |
| Zenith 安装痕迹 | 检查范围内未发现 `m_mod.m`、相关 `.orig`、构建标记或常见加载器目录 | 未见这条路线已经装入游戏的迹象；不能据此断言游戏完全无修改 |

本轮重新执行的是哈希、文件/索引、manifest 及描述符输入资源的检查。原来的 75 项 Python、38 项 JSON、21 项 JS、6 棵动作树与四项 composer 测试仍是附件中的既有记录，本轮没有将它们伪记成重新执行通过。

## 需要补齐的核对项

### G01｜运行环境与存档保护：首次安装前

游戏根目录存在 `Juij_Steam.dll`、`version.dll`、`winmm.dll`；三者哈希相同，PE 描述均为“Steam DLC 解锁”。所以当前环境需要作为一个独立兼容组合记录，不能直接套用纯净 Steam 环境的成功结论。本次没有移除这些文件，也没有读取 `Juij_Steam.json`。

原安装入口的 `entry_point.py:170–190` 固定使用 `%USERPROFILE%\AppData\LocalLow\91Act\BlazblueEntropyEffect`，备份 Steam、XBoxPc、Global 分支，实际清理候选只枚举 Steam/XBoxPc 的数字存档文件。该根目录与 Steam 分支在本机存在，但这不能证明它就是当前游戏实际使用的全部存档位置，也不能证明自动备份和还原有效。

**解除条件：**确认当前生效存档、测试档隔离与自动备份覆盖范围；在副本验证备份可还原；记录关闭 Mod 后会移除哪些记录。不能只因显示“已备份”便验收，也不能把删除 Mod 文件夹当成回退。本次未读取原始存档，未执行清理或备份。

### G02｜实际基线解码、JS 锚点与完整构建：首次安装前

现有证据没有完成本机的 `setup → prepare → build`。本轮只确认了表、脚本和资源名称存在。真实表 payload 对 schema 的匹配、JS 替换锚点的出现次数和上下文、全部启用组合的完整构建仍未验证。

原包没有 `dump/dump.cs`、`dump/DummyDll` 或 `tools/typetrees/*`，但有 build `25627491` 的 schema 快照。`bbmod.py:232–255` 在实际资源缺少所需内嵌类型树、又要调用后备生成器时可能因缺材料而退出。**这是条件性缺口，不能直接说整个包一定不能构建。** 需要实际构建确定是否触发。

**解除条件：**在独立、可丢弃的工作目录完成 fresh 解码和 staging 构建；检查全部必需表/模块、锚点匹配次数及上下文；重读生成资源，核对依赖、PPtr、RID、CAB/GUID。对预期多次匹配的锚点提供明确依据，避免只看 warning 后继续。若触发 TypeTree 后备路径，再补对应版本的材料。

原包已带便携 Python 和主要依赖；无需为了这条路线先安装 BepInEx，也不能把当前系统 Python 缺 UnityPy 直接当成原包缺依赖。

### G03｜Setup 的“完成”不保证输出完整：构建前

源码有以下路径：

- `pipeline.py:42–43`：Unity 资源加载异常直接跳过。
- `pipeline.py:58–73`：JS 解密失败仅计数并留下 `.noah`。
- `pipeline.py:181–192`：表解析失败仍可写入部分 rows，最后只打印统计。
- `entry_point.py:130–135`：只判断子进程返回码，随后写 `inspect/game_build.txt` 并显示完成。

因此“setup 返回 0/写了 build 标记”不足以证明基线提取完整。源码行为已核实；本次没有动态制造提取失败。

**解除条件：**输出结构化失败清单；必需模块和表缺失、部分解析、解密失败时阻止后续构建；对可接受的无关失败显式列明范围。使用 fresh 输出，避免旧文件补齐表面上的完整性。

### G04｜表编码校验不足，原研究有误述：安装前

`研究笔记.md:102` 写“做编码往返校验”，但 `bbmod.py:53–59` 导入的 `make_patch.py:189–194 verify_table()` 只有长度前缀遍历和打印；没有 decode→compare、记录数相等、完整消费输入、长度边界检查。

**解除条件：**用真实基线验证 encode→decode 的语义等价；检查新增/删除的预期数量、未改记录、固定点对应表、大整数与默认字段；从生成 bundle 回读 payload。比较时区分浮点容差和必须精确保留的整数，不把“输出非空”“行数打印正常”当成通过。

这是对原研究结论的纠正，不是已完成的修复。上传研究资料保持原样，纠正在本报告中记录。

### G05｜组合器的定位与冲突语义未充分覆盖：扩展通用补丁前

原笔记指出的 SkillDamage 歧义成立：普通定位键是 `ActorId, HitTimes`，不含 Action；同键不同动作不适合直接按 Action 普通覆盖。

原源码还显示：基线重复键可静默覆盖索引中的先前行；`$append` 不更新普通索引；`$new/$copyRows/$replace` 与普通字段的 owner 检查不能视为同一套完整冲突保护。四项现有测试没有覆盖这些组合，更没有覆盖所有资源与引用冲突。

**解除条件：**明确每张表的唯一性合同；对重复键、追加后覆盖、新建后修改、复制、整体替换、删除、依赖排序和独立冲突补可复现用例；核对真实目标行唯一性。资源改名/引用/依赖另做验证，不能用“无 CONFLICT”代替。

### G06｜更新或重新生成时的旧数据残留：首次开发迭代及游戏更新前

本轮确认一个比 build 标记更具体的风险：`pipeline.py` 重写 decoded 的当前 JSON/JS，但不清理其 `.orig`；`bbmod.py:127–128,136,196` 仅首次创建 `.orig`，随后组合始终从它读取。`entry_point.py` 重跑 setup 后可以写新 build，而自动退休旧备份主要处理游戏 ab 中的 merge/manifest 备份。由此可推导出“新 build 标记＋旧 decoded 原始快照”的组合路径；未动态复现。

另一个已有缺口是 GUI prepare 主要看顶层 `.py/.json` 时间；嵌套源码和素材变化不一定触发重新生成。

**解除条件：**按 build 隔离解码、原始快照和生成输出，或明确刷新并校验它们的哈希；嵌套输入使用显式生成步骤或完整输入指纹；测试重复构建、更新后的重建与旧状态恢复。保留原始资源、源码、依赖和构建产物的对应关系。

### G07｜安装失败恢复与完整回退：首次安装前

`make_patch.py:289–292` 先后替换 `m_mod.m`、`merge.json`；`bbmod.py:493–498` 随后处理 manifest 和 installed.json；`bbchar.py:38–51` 直接写 manifest。单文件替换不构成这些文件和存档之间的整组事务，已查路径没有覆盖整组失败回滚。

因此中断、权限/磁盘错误、manifest 写入失败后，可能留下部分新状态。这是静态风险路径，本次没有在用户游戏上触发故障。

**解除条件：**在副本做失败注入、重试、恢复；验证索引、bundle、manifest、installed 标记与存档状态一致；完成启用现成 Mod、仅撤回小补丁、关闭角色、卸载全部、重开游戏的回退检查。卸载清理行为应与 G01 的备份还原共同验收。

### G08｜可复现测试、诊断与依赖固定：第一轮构建记录中补齐

附件 `composer_tests.json` 是结果记录，没有同包提供独立 runner/fixture。原包虽含依赖，但 `entry_point.py:101–108` 在缺包时会使用未锁定版本的 `pip install --upgrade`。此外 `Launcher/README.md` 等部分旧文档仍描述旧 Nine 入口，不宜照其安装额外前置；以根目录 `SETUP_GUIDE.md` 和当前实际入口源码为准。

**解除条件：**保存可重跑测试及对应源码版本、实际依赖版本、构建输入指纹、输出清单、差异与诊断日志；确认 F9/Player.log/Mod 日志能定位一次故障；记录游戏重开、切场景、禁用/恢复、原内容回归和性能/资源异常情况。这里检查的是框架与安装闭环，不代替后续新角色内容验收。

原包 `SETUP_GUIDE.md:36` 将使用范围限定为单人。联机不应默认算已支持，若以后要做，应作为新增兼容目标另行验证。

## 公开来源的核对边界

作者的 [Zenith Update Center](https://github.com/KittySkin/Zenith-Update-Center/blob/main/README.md) 明确该公开库不含 Terminal 源码，完整包获取入口在 BBEE Discord 的 modding 区。[repositories.txt](https://github.com/KittySkin/Zenith-Update-Center/blob/main/repositories.txt) 指向公开 Mod 仓库；[该仓库 README](https://github.com/ramman48/bbee-redux-public) 的角色版本与此包一致，也明确公开目录缺素材，不能代替完整包。

上述页面没有为本地 ZIP 提供已核实的签名/发布哈希，也没有让 loader commit `f6770a6` 得到公开逐文件复核。因此“与研究对象相同”已证实，“最新版/发布者认证/全面安全”未证实。此次未运行未知二进制、安装依赖、关闭防护或调整 DLL。

## 推荐的后续顺序

1. 确认当前运行组合和实际存档保护范围，保存独立基线。
2. 在独立目录完成 fresh 解码，补 G03/G04 的完整性与编码验证。
3. 完成全启用集合的 staging 构建，核对锚点、表差异和资源回读；按实际结果处理 TypeTree 条件缺口。
4. 用测试档完成现成 Mod 的安装、重开、单字段修改、撤回和卸载，并验证失败恢复。
5. 固定这套可重跑流程后，再承接新角色制作。

这些基础工作不依赖先确定人物。本报告只完成核对，没有执行以上构建、安装或修复步骤。

## 本地证据与复查入口

- [本地游戏验证](../evidence/local_game_validation.json)：安全字段、文件哈希、索引边界与资源头抽样。
- [原包一致性验证](../evidence/package_source_validation.json)：原 ZIP、155 份源码哈希、工具材料清点与带原行号摘录。
- [manifest 和描述符输入检查](../evidence/baseline_structure.json)：独立脚本的新结果，包含名称集合差异与未验证项目。
- [关键源码片段](../evidence/framework_source_checks.md)：G03/G04/G07 等路径的原文、原行号与文件哈希。
- [本轮只读结构检查脚本](../scripts/check_baseline_structure.py)：不导入或执行原 ZIP 中的任何代码；仅用本机已有 Python/lz4 读取文件并输出上述 JSON。

原始游戏目录：`E:\SteamLibrary\steamapps\common\BlazblueEntropyEffect`。

原 Zenith ZIP：`C:\Users\MECHREVO\Downloads\ZenithTerminal-0.3.0-alpha (1).zip`。

Zenith ZIP SHA-256：`b5b3c2548ab61259c6f757b0cbf450a1d3490345ae9172915a5d7a303c36e150`。

用户研究 ZIP SHA-256：`fce4af002a8d038288cdcbe8e0688b3bcfe7e7e5c8576b065903189c4c38cd53`。

本轮没有修改游戏、原 ZIP、研究资料内容或存档；没有启动游戏/Terminal、安装依赖或宣称实机通过。审计输出为本地文件，目录不是 Git 仓库。
