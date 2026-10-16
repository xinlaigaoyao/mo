# 本地资源与依赖准备

此说明面向接手源码的协作者。工程源码与依赖声明可共享，游戏安装、私人存档及无再分发许可的素材需在主力机本地准备。

## 固定工具与游戏

- 目标 BBEE build：`25627491`，Unity：`2022.3.62f2`。
- 当前工作台要求便携 Python `3.14.8`；依赖见 `bbee-mod-workbench/dependencies.lock.json`、`requirements.lock.txt`、`requirements.typetree.lock.txt`。不要自动替换为系统 Python 或升级依赖。
- Node 与 .NET SDK 的已用版本也记录在 `dependencies.lock.json`。
- Il2CppDumper `6.7.46` 源码及本地补丁保留在 `bbee-mod-workbench/tools/Il2CppDumper-6.7.46/`，保留上游 LICENSE；下载链接、源码 ZIP 哈希及编译说明见工作台 README。NuGet 配置保留，下载缓存与编译二进制不上传。
- Zenith Terminal、Qt 与字体归属说明见 `ZenithTerminal/NOTICES.md`、`Gui/NOTICES.md` 与 licences。保留声明不代表所有第三方 Mod 美术都获准再分发。

## 排除资源如何处理

`baselines/25627491/game` 与 `ZenithTerminal/Launcher/game` 是本地游戏物理副本，均不入库；需要从合法本地安装按工作台流程重新准备并验证。解码目录、TypeTree/schema 缓存及 `patch_out` 应从准确的本地 build 重新生成，不能凭空拼补对象或 CAB 标识。

`references/wandering-sword/*/raw`、`textures`、角色原作素材、Ruby `bbtag_alpha`、DELTARUNE `pack/audio`、其他第三方美术与声音全部排除。保留导入脚本、合同及来源清单以说明需求；这些文件中的绝对路径和哈希是原主力机记录，不代表其他机器已有资源。请自行合法准备匹配资源，并在独立环境中确认路径配置。

`mods/*/gen` 为生成结果，未入库。生成器与源合同保留，但完整角色构建还需要缺失的素材输入和准确游戏依赖。不要把缺失资源当作软件缺陷修补为跳过验证。

## 自制素材缺口

本次只读访问被拒绝的路径：

- `ZenithTerminal/Launcher/mods/char-yuwen-yi/assets/authored/`
- `ZenithTerminal/Launcher/mods/char-yuwen-yi/assets/authored-sheets/`
- `ZenithTerminal/Launcher/mods/char-yuwen-yi/assets/authored-poses.json`
- `evidence/yuwen-yi/authored-poses-validation.json`

它们未复制，未更改 ACL，未绕过权限。`assets/prepared/` 属于派生准备结果而主动排除；没有实际读取被拒绝的证据，不计入权限阻挡。`assets/original-vfx/` 的生成脚本与来源合同保留，原作及派生纹理不上传。本快照尚无已核实可再分发的自制位图，因此不能宣称已完成整个视觉素材交接。后续需获得这些准确自制输入的正常读取条件、核实许可，再单独导入。

本地脚本含固定 `E:\AAA MOD\bbee-mod-workbench` 路径以及严格目录身份合同。克隆到其他路径不等于可直接运行；先审查路径绑定。不得改正在运行的源目录、权限、进程或私人存档来迁就云端复现。
