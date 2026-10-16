建立 BBEE Mod 的独立基线、严格数据校验与可恢复安装流程

原包的 setup 可能带失败退出为成功，表校验只统计记录，重跑生成可能继续使用旧数据；安装把资源、索引、manifest 与存档分开写，异常时不能保证整组一致。

本次使用物理输入快照与可写工作副本，显式绑定 build、依赖和存档根目录；fresh 输出完成校验后发布，每次刷新普通表、固定点表与 JS 的原始快照。prepare 统一递归依赖并在生成前恢复已验证输入。表编码检查完整边界、记录数、默认字段、大整数及语义往返，固定点按完整普通行语义保留未改记录原字节，避免重复主键造成误替换。组合器拒绝歧义覆盖，对明确重复的 JS 锚点绑定精确版本合同。

旧嵌套整数数组及 singular UTF-8 protobuf body 在严格完整字段和字节往返合同下进行内存规范化，普通已知字段 null 采用 unset 语义；模糊边界、多消息 singular、列表内 null 仍拒绝。资源阶段前预检所有涉及的普通/固定点表，耗时导入后复核输入未漂移；最后的构建验收还要求回读 UnityFS、SerializedFile、payload 和引用。构建记录绑定源文件、描述符、基线与递归素材指纹，资源内时间及新 GUID 由输入确定，供重复构建逐束比较。TypeTree 候选与真实完整读取缓存分开，不将原生生成节点直接当作兼容证据。

安装和卸载实现带目标白名单、前态/目标哈希及持久日志的整组事务，旧入口统一路由或禁用；备份先回读验证，恢复先留恢复前备份。资源在实际组装复制时再次绑定已验证哈希，卸载恢复对 pristine 内容核验，拒绝外部漂移后静默覆盖。统一回归覆盖失败、外部改动、进程硬终止与重试恢复。新增中性 stock clone importer，保留原业务对象字节，以独立逻辑路径/CAB 和 manifest 记录验证通用生成路线，没有新增角色或修改角色美术。

当前验证快照：真实 strict/fresh 基线通过；Inspector 0.4.1 修复冻结后最新完整工程批次编译 120 份 Python，回归运行 265 项、263 通过、2 个 symlink 用例因宿主限制跳过，junction 覆盖通过。全部 15 个工程阶段通过；身体参考属于另批，不由此推定通过。真实 ActionLogicGroup 的 embedded／离线 TypeTree 完整读取通过，原生 generator 候选完整读取失败，未声称普遍兼容。

非角色完整 `framework-runtime` profile 的全部 29 个 bundle 严格回读通过，两次完整构建的 29 个资源哈希一致；安装 29、更新 29、撤回到 4、卸载事务均 committed，原始目标字节恢复；独立基线与原游戏各 2,397 项文件集合/哈希最终复核通过，沿用敏感配置排除规则。中性 clone 的 2 个非 AssetBundle 对象字节不变，新 CAB 稳定，新增 manifest 1 项；源 stock dependencies 和本 profile external checked 均为 0，不能据此声称有外部引用正向样本。

默认角色 fixture 另行聚合：1,154 个 bundle、17,857 个对象均可严格读取，13,762 个 external PPtr 检查发现 710 个错误，集中于 126 个 Ruby 私有 producer 产物。该范围保持 failed、installable=false，未修改角色源码或给予验证豁免；它提供门禁实际拒绝坏引用的独立证据，不属于本次非角色机械成功。

为修复独立启动的证据缺口，新增只读桌面会话预检和带 ownership 日志的 launcher prepare/restore。预检只读取本进程 WTS 信息前 20 字节，锁屏、未知或 API 失败均在文件变更前阻止 prepare，恢复入口仍可用。prepare 绑定已验证存档 guard、baseline SHA 和三个同源代理原哈希，只临时隔离副本文件、写副本 AppID，生成精确 WorkingDirectory 的快捷方式；不自动启动、不改 Steam 或原安装。真实 managed 探针增加 `working_directory_matches`，缺失或 false 均不能通过运行验收。

首次有效试用暴露 inspector 在模块加载环中过早捕获 Util_1.U，effect 订阅失败后又被误标已安装。0.4.1 采用调用时读取依赖、成功后标记、失败有界重试；同构建实机 F9 报告已记录订阅成功 1 次、fx+ 118 次、warnings 0，重新打开后主菜单与 fresh 管理探针再次观察通过。

当前状态为 `engineering-passed / runtime-passed`，只覆盖非角色平台 readiness。最新 run `9a95cfaa547b4837868243de38886267` 的 guard.finish 为 restored_with_runtime_acceptance，四项 marks 和路径／加载／is_playing 全部通过；游戏已关闭、三个代理／AppID／owned shortcut 复位、事务卸载 committed，工作和源输入各 2,397 项哈希复核通过，无 active guard／launcher／安装记录。权威证据为 [inspector-fixed-runtime.json](../../../evidence/inspector-fixed-runtime.json)、[runtime-acceptance.json](../../../evidence/runtime-acceptance.json)、[runtime-final-restoration.json](../../../evidence/runtime-final-restoration.json)。原始诊断私下归档，公开保留摘要与哈希。新增角色的选择、身体、资源、技能、潜能和强度需单独验收。

早先三轮失败保留为历史：记录到黑色窗口、无 Unity 日志或 Steam 重定向，并完成那些进程的关闭和恢复。旧“工作目录”仅来自 Node 工具，未证明目标游戏 cwd；旧黑图也缺少锁屏前态，不能归因代理 DLL。后来本轮实际确认锁屏时 Explorer 同样全黑，停止 UI 并由用户解锁后，使用正确 WorkingDirectory 的启动路径取得当前真实运行证据。该纠正不反向证明旧三轮处于锁屏。

历史三轮备份和还原通过，精确范围为文件字节、名称、目录、mode 与 mtime，atime 仅 best effort，保留 [runtime-environment-restoration.json](../../../evidence/runtime-environment-restoration.json) 及三轮 finish 日志。本轮实际恢复另有上述最终收据，不使用旧快照代替。系统 Python 3.11.9 曾因 st_dev 不同被身份门禁拒绝；所有运行保护、launcher prepare／restore 和 finish 必须使用同一固定便携 Python 3.14.8，未绕过检查，见 [runtime-interpreter-identity.json](../../../evidence/runtime-interpreter-identity.json) 及 README 规范命令。

用户新增宇文逸授权，范围见 [宇文逸规格](../yuwen-yi/spec.md)。平台门槛满足后 ActorId 200901／skin Id 200901020 已全查重正式分配，玩法 agent 已开始制作；尚无新增角色完整构建或实机结果。先前九成员参考和 28 项检查已通过，见 [reference-validation.json](../../../evidence/yuwen-yi/reference-validation.json)；两张头像身份仍 pending，文本不证明实际武学机制或 BBEE 数值。身体 Paper2D 新批次两工具首次编译通过，但收集因 APNG preview has no frame duration 失败即停、输出清理；[body-reference-collection.json](../../../evidence/yuwen-yi/body-reference-collection.json) 保留失败，修复冻结后另批重验，不改写成首次成功。

首次 dotnet 编译曾输出创建开发 HTTPS 证书的提示；缺前态快照，不宣称系统零副作用。后续编译环境关闭自动开发证书生成，未删除归属未确认的证书。最终交付与临时产物清理分别以 [delivery/receipt.json](../../../delivery/receipt.json) 和 [cleanup.json](../../../evidence/cleanup.json) 的实际结果为准，不由工程通过推定。

遵守最新 AGENTS：全部实现后集中编译、验证、验收；每次对话结束清理临时产物。平台运行和 owned 启动文件恢复已完成，其他临时产物以当轮 cleanup 收据为准。实际证据和后续状态由 [acceptance.md](acceptance.md)、[角色工作记录](../yuwen-yi/acceptance.md) 与对应收据持有。此文件仅为提交说明草稿，未初始化 Git、未提交或发布；宇文逸实现进行中，不将平台通过写成角色可玩。
