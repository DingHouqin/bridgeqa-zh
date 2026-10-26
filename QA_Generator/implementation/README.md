# 实现与运行索引

返回[机制入口](../README.md)。当前实现维持既有源码位置，便于保留已冻结运行与实现清单的可追溯关系。完整环境、安装步骤和凭证处理见[可执行原型说明](../../src/multi_agent_v0/README.md)。

## v0.2批次验证入口

新增[删证与审查模块](../../src/deletion_review_v2/README.md)，执行[首批规范](../specs/deletion-review-v0.2.md)，旧原型与旧数据保持可读。FamilyV2由[合同](../../src/deletion_review_v2/contracts.py)与[变换器](../../src/deletion_review_v2/family.py)维护；[审查投影](../../src/deletion_review_v2/review_cases.py)隔离A/B/C输入和隐藏参考；[实验运行器](../../src/deletion_review_v2/experiment.py)提供固定次序、3次独立重复、断点复用、有限格式修复与分项计数。引用失配仅表示登记支持变化，文本语义须独立审核。

[来源构建器](../../src/deletion_review_v2/source_packets.py)明确保存Flash初稿、程序蓝图与根GPT修订；[受约束角色任务](../../src/deletion_review_v2/construction_jobs.py)不等于自主端到端构题。[案例构建器](../../src/deletion_review_v2/build_locked_batch.py)输出正确／损坏副本及实际批准库提示，不签独立审核门禁。当前[冻结包](../../artifacts/deletion-review-v2/batch-001/)为10家族、57成员、44案例，396次审查和67次盲解已完成，见[实际报告](../validation/2026-10-22_删证与审查首批验证.md)；运行与审核状态见[验证索引](../validation/README.md)。

本批采用机器→独立GPT前后审核→未解决争议人工，不进行固定随机人工抽审。实验前门禁绑定案例与参考哈希；实验后审核实际输入、统计分母和报告。正式发布保持关闭。

## 质量修复与技能迭代入口

后续[证据合同v0.5](../specs/evidence-contracts-v0.5.md)以[评分逐步隔离](../../src/quality_v3/scoring_isolation.py)和[支持登记](../../src/quality_v3/support_contract.py)修复三轮留下的程序边界；[冻结运行器](../../src/quality_v3/evidence_contract_experiment.py)与[分项分析器](../../src/quality_v3/evidence_contract_analysis.py)分别维护本轮实际请求和指标。每步引用独立会话，最终答案与原引文语境另核；登记结构通过不代表语义或穷尽。旧三轮合同与结果保留，验收状态见[验证索引](../validation/README.md)。

[片段目录适配v0.6](../../src/quality_v3/inventory_catalog.py)在原合同之外提供精确原文ID选择，解决模型自行数字符的定位失败；[后续运行器](../../src/quality_v3/inventory_catalog_experiment.py)独立冻结10项公开回归，不覆盖失败批次。315项程序测试、164个返回会话及语义限制见[本轮报告](../validation/2026-10-22_评分证据隔离与支持登记合同修复.md)。

[质量模块](../../src/quality_v3/README.md)保留旧实现，新增单成员投影、有序证明核对、保守实体归一与逐维语义评分。新技能是Harness项目资源，由[加载器](../../src/quality_v3/skill_loader.py)显式拼入请求，未安装全局Codex技能。首轮[技能正文](../../src/quality_v3/skills/)和后续[候选修订](../../src/quality_v3/skill-revisions/)分别保存，不因存在文件就认定有效。

[首轮运行器](../../src/quality_v3/experiment.py)与[后续迭代器](../../src/quality_v3/iterate.py)冻结每项实际输入、Schema、技能正文和任务顺序；独立GPT门禁绑定五项摘要。generic／skills同轮共享[查询卡与字面窗口](../../src/quality_v3/retrieval.py)、[0／1步骤合同](../../src/quality_v3/protocol_next.py)及程序门禁，不能将共享程序效果记为技能效果。

执行[至少三轮的开发协议](../specs/skills-iteration-v0.4.md)：回归旧例、独立新增例、修订冻结、预审、实跑、后审；真实失败和未决均保留。[原分析器](../../src/quality_v3/analyze.py)保留不动，[多轮分析器](../../src/quality_v3/analyze_iterations.py)仅在参考未变的共有案例上比较跨轮变化，新例单列。实际进度与完成结论见[验证索引](../validation/README.md)，预定调用数不表示已完成。

## 模块索引

| 模块 | 权威文件与职责 |
| --- | --- |
| 编排 | [runner.py](../../src/multi_agent_v0/runner.py)：会话创建、阶段检查、有限修订、裁定接入及请求记录。 |
| 输出合同 | [contracts.py](../../src/multi_agent_v0/contracts.py)、[schemas.json](../../src/multi_agent_v0/schemas.json)：五角色结构与字段校验。 |
| 业务核心 | [core.py](../../src/multi_agent_v0/core.py)：证明枚举、查询、删证、家族检查、输入投影及结果核对。 |
| 外部关系提示 | [external_relations.py](../../src/multi_agent_v0/external_relations.py)：仅读取经批准且哈希匹配的C01/C02快照，输出静态辅助线索；[审批范围](../resources/relationship-libraries/approval.json)。 |
| 格式适配 | [formatting.py](../../src/multi_agent_v0/formatting.py)：保守括号修复与说明字段保留。 |
| 角色预设 | [role-presets.json](../../src/multi_agent_v0/role-presets.json)：角色、Skill 与运行权限映射。 |
| 构建配置 | [harness.patch.yml](../../src/multi_agent_v0/harness.patch.yml)：隔离运行、工具及上传权限。 |
| 盲解配置 | [solver.patch.yml](../../src/multi_agent_v0/solver.patch.yml)：禁用图工具，配合共享配置关闭其他模型工具。 |
| 插件 | [bundle 定义](../../src/multi_agent_v0/plugin/package.json)、[注册入口](../../src/multi_agent_v0/plugin/index.js)、[纯查询逻辑](../../src/multi_agent_v0/plugin/logic.mjs)：检查显式提交的有限图。 |
| 插件接入 | [安装器](../../src/multi_agent_v0/install_plugin.py)、[真实执行验收](../../src/multi_agent_v0/verify_plugin.py)、[运行配置启动检查](../../src/multi_agent_v0/smoke_profiles.py)。 |
| 裁定示例 | [prepare_adjudication.py](../../src/multi_agent_v0/prepare_adjudication.py)：已披露的单次 GPT 裁定整理器，针对既有批次，不是通用补事实服务。 |
| 协议与评分核验 | [协议统一复跑器](../../src/multi_agent_v0/rerun_blind_protocol.py)、[证据区间重核](../../src/multi_agent_v0/recheck_evidence_intervals.py)：保留旧版响应与分数。 |
| 打包 | [audit_and_package.py](../../src/multi_agent_v0/audit_and_package.py)：审计并导出当前最小交付合同，不是通用批量发布器。 |
| 依赖与行为测试 | [requirements.txt](../../src/multi_agent_v0/requirements.txt)、[test_core.py](../../src/multi_agent_v0/test_core.py)。 |
| 外部比对回归测试 | [test_external_relations.py](../../src/multi_agent_v0/test_external_relations.py)：审批、文件损坏、角色投递、时间与别名边界、已知库错和删证隔离。 |

## 五份角色 Skill

| 角色 | 指令入口 |
| --- | --- |
| Origin | [事实抽取 Skill](../../src/multi_agent_v0/skills/bridgeqa-origin/SKILL.md) |
| Composer | [基础题设计 Skill](../../src/multi_agent_v0/skills/bridgeqa-composer/SKILL.md) |
| Difficult | [困难设计 Skill](../../src/multi_agent_v0/skills/bridgeqa-difficult/SKILL.md) |
| Supervisor | [阶段审查 Skill](../../src/multi_agent_v0/skills/bridgeqa-supervisor/SKILL.md) |
| Blind Solver | [隔离盲解 Skill](../../src/multi_agent_v0/skills/bridgeqa-blind-solver/SKILL.md) |

Skill 随角色任务显式加载；权限、输出字段和程序放行不能仅依赖提示词保证。当前采用 Python 外部编排与隔离根会话，不将其表述为 Harness 原生多智能体工作流。

## 运行入口

以下命令在项目根目录执行，前提是已按[安装说明](../../src/multi_agent_v0/README.md)配置任务内环境。测试无需 API 凭证；构题命令会调用模型并生成新批次，不属于查阅资料时自动执行的步骤。

```powershell
workspace/harness-prototype/runtime/.venv/Scripts/python.exe -m unittest discover -s src/multi_agent_v0 -p test_core.py -v
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/multi_agent_v0/runner.py --run-id next-pilot-001
```

上例每次实际新运行应使用未使用的批次标识。运行记录与依赖维护于[Harness 工作区](../../workspace/harness-prototype/README.md)，固定家族见[验证索引](../validation/README.md)。原始模型响应、提示和输出包不得随文档整理而重写。

## 支持登记与评分合同继续修复

[v10协议](../specs/evidence-contracts-v0.10.md)在逐位置平坦选择与独立正组审核上恢复单位定义，评分约束显示姓名起点并窄修父称呼角色门。[本轮验证](../validation/2026-10-22_支持覆盖与旧评分继续修复.md)保留v7—v9失败及独立打回证据；[v10全54任务实跑](../../artifacts/quality-v3/contracts-v10-run-001/README.md)与独立语义后审已完成，完整评分严格19/37、登记8/16，未通过整体修复验收。未决与结构通过不等于修复成功，实现入口见[质量模块](../../src/quality_v3/README.md)，候选未默认启用。
