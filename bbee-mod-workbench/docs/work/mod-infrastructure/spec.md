# BBEE 非角色 Mod 基础设施

Status: 实际阶段由 [acceptance.md](acceptance.md) 与本轮 evidence 持有；工程验收和实机验收分别记录。

## 目标和范围

用户于 2026-10-15 授权补齐前次审计列出的全部非角色缺口。以 Zenith Terminal 0.3.0-alpha 的本地副本为基础，交付可复跑的独立基线、严格解码与编码验证、正确组合和生成触发、完整构建、事务安装/恢复、存档保护与诊断记录。本规格只持有基础设施工作；用户后来授权的平台就绪后制作宇文逸，由 [宇文逸规格](../yuwen-yi/spec.md) 持有。已有角色 fixture 作为通用校验诊断输入，已确认的旧角色私有美术 producer 缺陷依照用户排除范围保留失败，不因新宇文逸授权自动扩展为修复全部旧角色。

非角色完整验收以 `profiles/framework-runtime.json` 的全部 enabled/dependencies 为闭包，覆盖共享 SDK、actor 框架、inspector 和中性 validation probe 的所有输出。probe 通过普通/fixed 表、JS、独立 importer、stock 资源克隆、新 CAB 与 manifest 新增路线；不注册新角色、不改原 ActionLogicGroup 内容。默认角色 profile 单列兼容诊断，不能因为选择了非角色 profile 就把原失败改成通过。

原始输入：`C:\Users\MECHREVO\Downloads\ZenithTerminal-0.3.0-alpha (1).zip`，SHA-256 `b5b3c2548ab61259c6f757b0cbf450a1d3490345ae9172915a5d7a303c36e150`。

游戏输入：`E:\SteamLibrary\steamapps\common\BlazblueEntropyEffect`，已核对 build `25627491`。其代理 DLL 状态属于当前兼容组合；本任务不擅自清除它们。基线是该安装的可追溯快照，不宣称经过 Steam depot 字节认证。

审计原文：`E:\AAA MOD\bbee-mod-audit\docs\2026-10-15-non-character-gap-audit.md`。

## 交付行为

- 一个入口建立独立物理构建基线、核验输入哈希、运行 fresh 解码/prepare/staging build 并保存真实日志。
- 解码缺失/部分失败、表编码不等价、歧义定位或未声明多锚点不允许显示成功。
- 同 build 重跑与不同 build 数据隔离；输入嵌套变化会触发生成。
- bundle、索引、manifest、安装记录使用可恢复事务；提供故障、重试、卸载验证。
- 存档备份必须回读校验，可还原；显式绑定目录，空目录不冒充已备份，测试数据与私人数据分开。
- 固定实际依赖，提供回归测试、生成物清单、差异和验收证据，源码修补可以与原包对应。

## 最新执行约束

2026-10-15 用户在工作区 [AGENTS.md](../../../../AGENTS.md) 增加以下原文，优先于早期逐小功能验证的执行方式：

> 全部实现后再统一编译、验证、验收。
> 每次对话结束 清理临时产物

实现阶段先完成并冻结受影响代码，再由统一入口集中编译、验证和验收。统一验收发现缺陷时，记录失败、完成对应修复并再次冻结，再集中执行受影响部分；不让多个 agent 交错改 current 数据、生成和验收。已通过且未受影响的 strict/fresh 基线，可在核对全部不可变文件集合、哈希和 build 绑定后复用，不要求重复无关提取。

每次结束前核对并清理本轮创建且不再需要的临时解码树、失败生成物和试验目录；记录实际清理范围。源码、可追溯证据、交付产物、独立基线及恢复所需私人备份各有用途，不因名称含 cache/backup 就直接删除。没有执行清理时必须保持“待清理”，不能提前写完成。

统一验收入口为 `scripts/final_acceptance.py`，必须记录所选 profile 路径、哈希和 enabled 集合。该范围工程成功需要所有输出完整回读、重复构建、物理副本安装/更新/撤回/卸载和输入还原校验全部满足，不允许只挑 profile 内部分输出通过。实机画面与交互验收另外记录；启动重定向、黑窗或缺少运行探针时保持 runtime blocked。当前实际阶段、计数、跳过项、失败和剩余工作仅由 [acceptance.md](acceptance.md) 持有，不在本规格复制动态计数。最终交付以 [delivery/receipt.json](../../../delivery/receipt.json)、清理以 [cleanup.json](../../../evidence/cleanup.json) 的实际结果为准。

## 验收层次

单元/故障测试、实际游戏数据解码、完整构建、沙盒安装回退、真实游戏画面与交互分开记录。各层只有实际运行才可勾选。模拟存档不证明私人存档绑定；成功进程退出不证明游戏功能或角色表现。需要独立实机验收的项保持待验收，不因代码完成而关闭。

实际存档保护的验收分为备份回读、变动后的恢复和 Unity 保存路径匹配。前两者有实际文件证据时可以独立通过，不能因此推定运行时路径匹配。精确恢复声明限定于文件字节、名称、目录、mode 和 mtime；atime 按 best effort 单独记录。关闭本次创建的游戏进程、复位临时代理隔离和移除本次 AppID 提示后，再复核原游戏与工作副本文件。

严格表合同包括长度前缀完整消费、protobuf 字段类型/边界、大整数精确保留、float32 量化、预期记录数及固定点对应关系。未改 fixed 记录按完整普通行语义与原始 body 的队列对应，重复主键不用于猜测替换目标；输出顺序由当前表确定。

旧 mod 的 repeated/singular 嵌套整数数组及 singular UTF-8 wire body 只在完整已知 scalar schema、明确字段顺序和精确字节往返合同下规范化；singular 必须恰好一条消息。普通已知字段的 JSON null 采用 unset 语义，列表内 null 和 unknown key 不因此被放过。不修改角色方案，不将含糊或未解释字段伪装成语义通过。

在资源导入前对涉及表做只读预检，导入后再次校验输入未漂移；预检与最后的 UnityFS/SerializedFile/payload/引用回读是不同层。TypeTree embedded 完整读取、离线缓存复读、原生 generator 候选分别记录；生成节点不等于兼容，个别类型通过不等于其他类型或未来 build 通过。

资源正向覆盖应按实际对象与依赖计数记录。中性 stock clone 保留其源对象和依赖合同；如果原始依赖或 external PPtr 数为零，不宣称该 clone 提供了外部引用正向样本。默认 fixture 的全对象聚合诊断可以作为外部引用门禁的独立证据，但诊断不产生安装凭证；角色 producer 的 dangling PPtr 仍须拦截和保留失败清单。

## 实施归属

工单 01：独立基线和执行入口（root）。工单 02：严格数据与组合验证（validation/composer agents）。工单 03：事务和存档保护（recovery agent、root集成）。工单 04：完整构建、回归与交付证据（root，独立复审）。执行记录统一写 `acceptance.md`。

## 边界

原压缩包、已有审计资料和原游戏保持作为输入。所有安装/故障实验先在工作副本运行，任何未完成回读的产物不得进入安装阶段。私人存档备份仅放私有本地目录，不进入源码补丁、公共日志或 Basic Memory；fixture 验证不能冒充真实私人数据操作。未授权发布、推送或向作者发送消息；不初始化 Git 仓库。提交说明是草稿，实际提交或发布没有发生。

环境变化不能由游戏文件哈希未变推定为零。首次 dotnet 编译输出过开发 HTTPS 证书创建提示，但缺少证书前态快照；记录该边界，后续环境关闭自动开发证书生成，不删除归属未确认的证书。
