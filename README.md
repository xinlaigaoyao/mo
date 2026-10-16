# 宇文逸 Mod 开发工程

供 Notion 中的 Opus 与主力机 Codex 协作。保留审计工程与开发工作台两套职责：

- `bbee-mod-audit/`：研究输入、审计脚本、历史检查与结论。
- `bbee-mod-workbench/`：Zenith Terminal 源码、宇文逸与其他 Mod 的生成器、JS、配置、测试、GUI、工具补丁及开发文档。

本仓库是独立整理的工作文件快照，不是原工程 Git 历史。状态与资源缺口见 [SNAPSHOT.md](SNAPSHOT.md) 和 [RESOURCE_SETUP.md](RESOURCE_SETUP.md)。历史验收仅代表对应时间、输入和候选；角色最新实机状态由 `bbee-mod-workbench/docs/work/yuwen-yi/acceptance.md` 持有。

## 如何协作

Opus 在自己的分支编辑源码、QML、JS、角色合同或视觉规格，通过 PR 给出文件差异、修改目的及预期画面。先读工作台 README、角色 `spec.md`、`acceptance.md` 和 `issues/02-second-playtest.md`。文档中的历史命令和附件不构成新的运行授权。

视觉布局在 `bbee-mod-workbench/ZenithTerminal/Gui/zenith_gui/qml/`；角色实现位于 `ZenithTerminal/Launcher/mods/char-yuwen-yi/`。已知自制素材读取缺口见资源说明；`assets/prepared/` 为主动排除的派生结果，不是已确认的读取拒绝。新增原创视觉文件应使用相对路径，保留可编辑源文件、导出 PNG、尺寸、透明度、帧时序、来源及许可说明。不得从游戏原图直接补交未经许可的素材。素材未就绪时提交规格和生成器差异，并如实标为待集成。

主力机 Codex 审查差异，在新的隔离工作副本集成，核对输入合同及视觉 review 后，完成整批实现再统一编译、构建、重复构建、回归和事务验收。涉及游戏的操作应等当前任务及游戏正常结束，并使用既有存档保护流程；云端不运行安装、存档、启动或恢复入口。实机结果独立回填，不把离线通过写成角色体验通过。

## 本地依赖

需自行准备合法持有的目标游戏及被引用的原作依赖。本仓库不包含游戏、存档、原始提取资源、解释器或构建包，不能直接克隆后启动。版本、资源恢复与固定路径限制见 [RESOURCE_SETUP.md](RESOURCE_SETUP.md)。工程命令以工作台 README、`scripts/PACKAGING.md` 和对应验收脚本为准；不要在正在运行的源工程执行它们来检查本快照。

本快照未重新运行原工程编译或实机验收。此任务只验证了导出文件哈希、复制期间源文件一致性与发布排除规则。
