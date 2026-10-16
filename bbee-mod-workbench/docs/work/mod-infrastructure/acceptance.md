# 实施与验收记录

开始与核对日期：2026-10-15。状态：**`engineering-passed / runtime-passed`**，范围为当前 build／profile 的非角色平台 readiness。15 个工程阶段全部通过，Inspector 0.4.1 实机 F9 和 effect hook、同构建重开及退出恢复已完成。新增宇文逸角色的资源、玩法和专属分支不包含在平台通过中。早期失败保留历史；默认角色 fixture 全构建仍失败、不可安装。

本页记录主 agent 统一执行产生的实际证据，以及文档 agent 对文件的只读核对。自动回归、资源、构建与人工画面分别记录，文档同步没有重跑测试。[final-acceptance.json](../../../evidence/final-acceptance.json) 的 `status=passed` 覆盖全部 15 个非角色工程阶段；实机证据由 [inspector-fixed-runtime.json](../../../evidence/inspector-fixed-runtime.json) 持有。[runtime-acceptance.json](../../../evidence/runtime-acceptance.json) 为 `restored_with_runtime_acceptance`；[runtime-final-restoration.json](../../../evidence/runtime-final-restoration.json) 已核对本轮无 guard／launcher／快捷方式／AppID／安装记录、源和工作副本各 2,397 项哈希一致。[runtime-progress.json](../../../evidence/runtime-progress.json) 已置 passed。交付包装和整轮临时产物清理仍分别以实际 delivery／cleanup 收据为准，不能由运行还原代替。

用户新增的宇文逸制作授权及就绪门槛见 [宇文逸规格](../yuwen-yi/spec.md)，取代上一阶段只做非角色的范围限制。参考与设计可并行，角色整合依赖运行门槛完成；旧角色样例的私有 producer 缺陷仍排除，不因新增宇文逸范围而自动扩展。

## Profile 与范围矩阵

| 范围 | 实际输入与结果 | 结论边界 |
|---|---|---|
| 非角色完整 profile | [framework-runtime.json](../../../profiles/framework-runtime.json)：`bbee-sdk`、`bbee-actors`、`bbee-inspector`、`framework-validation-probe`；profile SHA-256 `c180102ec16616930c50370e1ead64cb3b351369032a19f17cef5fcaaa046391`。全部 29 个输出通过严格完整回读，重复构建 29 个资源哈希完全一致 | 本范围机械验收通过；不是默认角色全集合通过，也不等于实机通过 |
| 撤回 profile | 非角色完整 profile 安装/更新后，切换到仅保留 framework-validation-probe 的 4 个 bundle，再卸载 | 两次 29-bundle 安装、4-bundle 撤回、卸载事务均 committed；目标原始文件字节恢复、安装记录清除 |
| 默认角色 fixture 全 profile | 1,154 个 bundle、17,857 个对象均完成 strict read；聚合得到 710 个 external PPtr 错误，涉及 126 个 Ruby effect 包 | `status=failed`、`installable=false`；没有 verification receipt。角色私有 producer 缺陷按用户范围排除，角色源码未改；失败不能写成通过或安装 |

默认 fixture 失败已归档为 [fixture-full-build.log](../../../evidence/fixture-full-build.log)、[fixture-full-build-metadata.json](../../../evidence/fixture-full-build-metadata.json) 和 [resource-reference-diagnostic.json](../../../evidence/resource-reference-diagnostic.json)。完整构建要求保留：对选定的非角色 profile 和全部依赖、全部输出进行验收，没有从同一 profile 中跳过坏 bundle。

## 当前证据

| 层次 | 已观察结果 | 证据与边界 |
|---|---|---|
| 实际游戏数据基线 | build `25627491`；从 1,297 个 data bundle 提取 1,259 个 TextAsset，严格解码 192 张普通表、20 张固定点表、1,034 个 JS；失败、豁免、跳过与 opaque 段均为 0 | [decode_report.json](../../../ZenithTerminal/Launcher/inspect/decode_report.json)、[final-setup.log](../../../evidence/final-setup.log)。fresh `.orig` 包含普通表、固定点表与 JS，成功基线绑定文件集合和哈希 |
| 统一编译 | 最新完整平台批次编译 120 份 Python 源码；禁用游戏 DLL 原生加载 fallback 的静态元数据工具编译通过。先前 116／118 为历史批次 | [final-compile.log](../../../evidence/final-compile.log)、[source-compilation.json](../../../evidence/source-compilation.json)、[final-static-tool-compile.json](../../../evidence/final-static-tool-compile.json)。身体参考两工具属于后续独立批，不能由此收据推定新工具或角色实现通过 |
| prepare | 统一恢复已验证 `.orig`，按递归输入指纹重新生成构建输入；本轮退出码 0 | [final-prepare.json](../../../evidence/final-prepare.json)、[final-prepare.log](../../../evidence/final-prepare.log)。不据此认定后续构建有效 |
| 自动回归 | 最新完整平台批次运行 265 项，其中 263 项通过、2 项跳过，0 失败、0 错误；整体 runner 成功。先前 252／250 是历史结果 | [regression-summary.json](../../../evidence/regression-summary.json)、[final-regression.log](../../../evidence/final-regression.log)。两个跳过项均因宿主不能创建 symlink；Windows junction 拒绝路径覆盖已通过。身体参考另批验证，生成存档 fixture 不冒充实际备份恢复 |
| 表预检与 payload | 非角色 profile 涉及的 1 张普通表及 1 张固定点表通过预检和最终 bundle payload 回读。默认 fixture 聚合诊断另有 21 张普通表、10 张 fixed payload 和 28 个 JS payload 读取覆盖 | [preflight.json](../../../ZenithTerminal/Launcher/inspect/table_verification/25627491/preflight.json)、[框架 verification](../../../ZenithTerminal/Launcher/patch_out/_verification.json)、[聚合诊断](../../../evidence/resource-reference-diagnostic.json)。历史角色预检不冒充当前 profile 计数 |
| TypeTree | `GamePlay.ActionLogicGroup` 的 1 个真实对象通过 embedded layout 与离线缓存完整读取；`check_read=True` | [typetree-probe.json](../../../evidence/typetree-probe.json)、[final-typetree.log](../../../evidence/final-typetree.log)。原生 generator 候选虽生成节点，但完整读取失败；未把候选升级为兼容证据。其他类型和版本未由此 probe 证明 |
| 中性资源 importer/clone | 将 stock `actor/logicdata/rg` 克隆到 `infra/validation/stock_logic_rg`；2 个非 AssetBundle 对象字节不变，新 CAB `CAB-a07bab71039efa1a5ae637ed668bad97` 稳定；新增 manifest 名称/记录 1 项 | [final-build.log](../../../evidence/final-build.log)、[import_stock_probe.py](../../../ZenithTerminal/Launcher/mods/framework-validation-probe/import_stock_probe.py)。原始 stock dependencies 实际为 0，未制作角色、未修改原 ActionLogicGroup 内容、未新增随机 GUID |
| 非角色完整产物回读 | 全部 29 个 bundle 的 UnityFS、对象、local PPtr、managed RID 与表/JS payload 回读通过，已生成 verification receipt | [框架 verification](../../../ZenithTerminal/Launcher/patch_out/_verification.json)、[final-build.json](../../../evidence/final-build.json)。本 profile 的 external checked **实际为 0**，不能据此声称有 external PPtr 正向实例 |
| 外部 PPtr 门禁的独立证据 | 默认 fixture 聚合实际执行 13,762 个 external PPtr 检查，发现 710 个错误；错误全部落在 126 个 Ruby 私有 producer 产物 | [resource-reference-diagnostic.json](../../../evidence/resource-reference-diagnostic.json)。同时保留正常与拒绝路径回归。诊断不产生 receipt，也不把失败角色 profile 升级为通过 |
| 重复构建与事务链 | 两次非角色全构建的 29 个资源哈希完全相同；安装 29 → 更新 29 → 撤回 4 → 卸载全部 committed | [reproducibility.json](../../../evidence/reproducibility.json)、[final-install.log](../../../evidence/final-install.log)、[final-update.log](../../../evidence/final-update.log)、[final-withdrawal-update.log](../../../evidence/final-withdrawal-update.log)、[final-uninstall.log](../../../evidence/final-uninstall.log)。资源比较排除执行时间等元数据，不宣称所有元数据逐字节相同 |
| 最新工程和实机后的输入复核 | 15 个工程阶段完成；实机后再次确认工作副本和原输入各 2,397 项哈希通过，guard／launcher 均非 active，owned 快捷方式、AppID、安装记录均不存在 | [baseline-final.json](../../../evidence/baseline-final.json)、[source-game-final.json](../../../evidence/source-game-final.json)、[final-acceptance.json](../../../evidence/final-acceptance.json)、[runtime-final-restoration.json](../../../evidence/runtime-final-restoration.json)。敏感配置排除规则不变，不声称 Steam depot 或系统零副作用认证 |
| 历史三轮实际存档备份与还原 | 三轮运行保护各备份 44 个实际文件，均 `backup_verified=true`；每轮 finish 均 `original_save_root_restored_exactly=true`。后两轮实际检测到变动并完成还原 | [runtime-begin.log](../../../evidence/runtime-begin.log)、[runtime-native-begin.log](../../../evidence/runtime-native-begin.log)、[runtime-cwd-begin.log](../../../evidence/runtime-cwd-begin.log) 及三份 finish 日志。精确范围为文件字节、名称、目录、mode 和 mtime，atime 仅 best effort；不替代当前 guard 的 finish |
| 历史实机尝试与恢复 | 早先三轮均未达到运行验收，当时未触发 F9、探针 missing；那些进程已关闭并恢复 | [runtime-proxy-finish.log](../../../evidence/runtime-proxy-finish.log)、[runtime-redirect-finish.log](../../../evidence/runtime-redirect-finish.log)、[runtime-cwd-finish-retry.log](../../../evidence/runtime-cwd-finish-retry.log)。旧工作目录及黑图归因在下文纠正 |
| 历史三轮后的输入恢复 | 当时工作副本和原输入各 2,397 项通过，三个代理及两个 AppID 提示复位 | [runtime-environment-restoration.json](../../../evidence/runtime-environment-restoration.json)。保留为当时快照，本轮另有最终恢复收据 |
| 初次进入试用与操作 | run `502113b3109a421e96504b4edacdd3a2` 的独立进程进入原生试用，观察移动、跳跃、普通攻击、冲刺；同构建第二进程进入试用并取得 fresh probe | [runtime-reopen-observation.json](../../../evidence/runtime-reopen-observation.json)。第二次 F9 被人工 Escape 中断，未写成通过；当时 inspector effect hook 尚有初始化缺口，后由下一批补齐。原记录的 remaining gap 属历史，不代表最新版本 |
| Inspector 0.4.1 实机 | run `9a95cfaa547b4837868243de38886267` 的新 F9 报告记录订阅成功 1 次、fx+ 118 次、warnings 0；探针 loaded／save_root／cwd／is_playing 均满足。同构建第二进程重开进入主菜单，并观察 fresh probe | [inspector-fixed-runtime.json](../../../evidence/inspector-fixed-runtime.json)。原始报告私下归档，公开收据仅保留摘要／哈希。通过范围是非角色框架 readiness，不是新角色技能、强度或完整关卡 |
| 本轮存档与启动恢复 | guard.finish 为 restored_with_runtime_acceptance，四项 marks 与 probe 全真；文件字节、名称、目录、mode／mtime 精确恢复；三个 DLL、AppID 与 owned shortcut 复位，事务卸载 committed | [runtime-acceptance.json](../../../evidence/runtime-acceptance.json)、[runtime-launcher-restore.json](../../../evidence/runtime-launcher-restore.json)、[fixed-runtime-uninstall.log](../../../evidence/fixed-runtime-uninstall.log)、[runtime-final-restoration.json](../../../evidence/runtime-final-restoration.json)。atime 仍仅 best effort |
| 解释器身份合同 | 系统 Python 3.11.9 的 st_dev 与前态不同，拒绝后改用同一固定便携 Python 3.14.8，未跳过身份门禁 | [runtime-interpreter-identity.json](../../../evidence/runtime-interpreter-identity.json)。begin／launcher prepare／restore／finish 全部使用同一便携解释器，规范命令见工作台 README |
| 宇文逸参考工具的集中验证 | 两份工具源码内存编译，28 项检查通过；9 个 raw 共 10,050,762 字节、5 个输出、2 张 145px 头像像素及 manifest／源码哈希绑定通过；重复成员、父路径、同长度字节漂移三个负例均拒绝 | [reference-validation.json](../../../evidence/yuwen-yi/reference-validation.json)。未重开源 PAK、未重导出或读取存档；合成 fixture 已清理。视觉仅登记 root 观察的同一黑发青年金／蓝衣，人物身份仍 pending |
| 身体参考独立批 | 两份新工具首批编译通过；正式收集因 APNG preview has no frame duration 失败即停，输出清理，无成功身体验收 | [body-reference-compilation.json](../../../evidence/yuwen-yi/body-reference-compilation.json)、[body-reference-collection.json](../../../evidence/yuwen-yi/body-reference-collection.json)。修复冻结后另批集中重验，不计入平台通过或新角色制作完成 |

统一入口 [scripts/final_acceptance.py](../../../scripts/final_acceptance.py) 已完成所记录非角色 profile 的全部机械阶段，包括最后的独立基线与原游戏复核。默认角色 fixture 的旧失败保留在独立归档中，不覆盖或混入本次成功记录。

历史三轮的观察保留：含原三个同源代理的副本出现黑色窗口且未见 Unity 日志；临时隔离后两轮被 Steam 重定向到原目录。需纠正两处旧推断：所谓“观察到的进程工作目录”实际只是 Node 工具的 cwd，未核对游戏 cwd；旧黑图也缺少锁屏前态，不能归因代理。后来本轮明确查到 WTS 当前会话锁定，连 Explorer 也截图全黑，因此先停止 UI，用户解锁后再继续。该结论不反向证明历史三轮的锁定状态。

正确 WorkingDirectory 启动先取得画面及 managed 探针；初次 F9 实际暴露 inspector 过早捕获 Util_1.U 的加载环和 effect 订阅无法恢复的问题。0.4.1 改为调用时读取依赖、订阅成功后才标记、失败有界重试；源码冻结后完成最新全工程批次及实机报告验证。状态现更新为 `runtime-passed`，范围严格限非角色平台；新角色 auto-grant、图标／HUD、自定义身体、资源扣除、技能／潜能、强度与新角色存档分支必须另验收。

环境副作用另记：首次 dotnet 编译曾输出创建开发 HTTPS 证书的提示。由于缺少证书前态快照，不能宣称系统零副作用；后续编译环境关闭自动开发证书生成，未删除来源不明或归属未确认的证书。

## 审计项状态

| 审计项 | 当前实施与实际证据 | 未完成验收 |
|---|---|---|
| G01 环境/存档 | 独立副本、绑定、实际 probe 路径、验证备份及本轮精确恢复均通过；同一便携解释器身份合同已验证 | atime 仅 best effort；新角色存档生命周期另验收 |
| G02 完整构建 | 非角色完整 profile 的 29-bundle 全回读与中性 stock clone 通过；default fixture 的全部对象可读，但坏引用被正确拒绝 | 默认角色 profile 仍失败，不在用户本轮修复范围；非角色实机另外验收 |
| G03 setup 完整性 | 当前真实 strict/fresh 基线通过，必需输入失败会阻止发布，失败报告与有效基线分离 | 本层已通过；后续若修改解码/快照合同，重新验证受影响部分 |
| G04 编码验证 | 普通/固定点语义、边界、大整数、未改 fixed 字节保留及旧表示兼容回归通过；所选 profile 的实际 bundle payload 回读通过 | 不能将本 profile 的数量扩展到未启用角色；未来表/schema 变更仍须重新验收 |
| G05 组合语义 | 歧义定位、重复键、追加/复制/替换/删除、依赖、JS 锚点合同与 null/旧表示回归通过，非角色组合完成机械集成 | 不包含角色设计和角色私有 producer 修复；实机行为另外记录 |
| G06 重建/更新 | fresh 普通/fixed/JS `.orig`、递归指纹、输入绑定时间/GUID、两次 29-bundle 字节一致及实际更新/撤回链通过 | 只验证当前 build 和输入，不声称未来 Steam build 兼容 |
| G07 恢复 | 工程事务、漂移／崩溃恢复及本轮真实存档、三个代理、AppID、shortcut、卸载和两组 2,397 项复核通过 | atime 不在精确声明内；新角色清理分支另验收 |
| G08 复现/诊断 | 最新全工程批、真实 F9、单次 effect 订阅、118 次 fx+／0warn、同构建重开及 fresh probe 通过 | 单人平台 readiness；新角色与完整关卡性能未由此证明，包装和清理依实际收据 |

## 当前运行与交付边界

1. 非角色实机 readiness 已通过并恢复；当前没有 active guard／launcher 或已安装框架记录。新角色 ActorId 200901、skin 200901020 已全查重正式分配并开始玩法实现，尚无新角色构建或实机结果；角色分支见 [角色工作记录](../yuwen-yi/acceptance.md)。
2. 最终交付的实际文件、哈希和状态由 [delivery/receipt.json](../../../delivery/receipt.json) 记录，保持默认角色 fixture 的失败与本次非角色工程成功分开。
3. 启动临时文件已在 owned restore 中移除，参考验收 fixture 和失败身体输出已分别清理；每轮结束仍须按 [AGENTS.md](../../../../AGENTS.md) 清理其他临时产物，以当轮 [cleanup.json](../../../evidence/cleanup.json) 为准。源码、证据、基线及恢复所需私人备份保留，运行还原不冒充整轮清理收据。

最新用户约束及授权边界由 [spec.md](spec.md) 持有；本页不以生成数量、进程退出码或历史测试通过替代尚缺的验收。
