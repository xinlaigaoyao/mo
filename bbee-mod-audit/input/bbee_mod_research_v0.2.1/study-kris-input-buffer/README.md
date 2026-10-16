# Kris 第一段地面普攻：输入缓冲示例补丁

状态：仅完成离线表组合验证，未运行《苍翼：混沌效应》，未完成 Zenith 游戏内安装测试。
目标环境：本次上传的 Zenith Terminal 0.3.0-alpha、dr-party 0.6.4、表结构基线 25627491。
`gameBuilds` 表示这个示例的目标基线，不是已经实测兼容的声明。

## 改动

只对 SkillActivate 中 ActorId=200801、Group=1、Order=1 的记录，将 Preinputtime 从 0.20 改为 0.30。
其 Action 在所研究包中为 kris_a1。这里改的是输入预缓冲字段，不是攻速、硬直、动作总时长、伤害、无敌或普攻判定。
依赖 dr-party，所以由组合器先创建角色记录再应用本补丁。修改后是否符合预期手感仍须游戏内验证。

## 文件

mod.json：唯一的功能文件。没有 EXE、DLL、Python、JavaScript 或美术资源。
README.md：本说明。不包含商业游戏素材、字体或原包资源。

## 受控测试方式（尚未在游戏里执行）

仅在你已信任并验证正常运行的原 Zenith 包上测试。先关闭游戏，保留独立存档备份，记录当前游戏 build。
把 study-kris-input-buffer 整个文件夹放入 ZenithTerminal/Launcher/mods/，不要把 mod.json 单独放在 mods 根目录。
通过 Terminal 界面刷新/重新打开后启用本示例，并保留 dr-party，按正常 Apply/Install 流程构建。
不要手工覆盖 m_mod.m 或 merge.json，不要绕过游戏版本/原始备份检查。

先比较安装前后的 decoded/tables/SkillActivate.json：目标行应只有 Preinputtime 改变。
再在测试存档中比较输入较早时第一段攻击的接续表现，确认动画、判定、伤害无意外变化。
还应测试空中输入、菜单、切换角色、退出与重开。记录 build、安装日志、观察结果。

撤回本示例：在 Terminal 中关闭本示例但保持 dr-party 开启，再正常应用变更。
这是按组合器机制推导的回退方式，尚未游戏内验证。若连 dr-party 也关闭，安装器会进入缺失角色清理逻辑。
安装器可能备份或清理存档，所以“本补丁不含存档字段”不等于“安装流程绝不写存档”。

## 已完成的离线检查

采用人工审阅的原包五个表组合函数，在临时目录内使用一条合成原版行及真实 dr-party 补丁：
1. 与 dr-party 单独构建结果比较，只变动指定行的 Preinputtime：0.20→0.30。
2. 无关的合成原版行不变。
3. 从同一 .orig 重复组合，输出一致。
4. 另一个未声明依赖的补丁覆盖同一字段时，组合器产生 CONFLICT 报告。

这些结果不证明真实游戏基线可用、不证明 GUI 可以完成安装、不证明手感改变恰当。
