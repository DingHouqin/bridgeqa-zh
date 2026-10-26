# Quality v0.4：单成员审查、语义评分与技能迭代

后续[证据合同 v0.5](../../QA_Generator/specs/evidence-contracts-v0.5.md)另版实现评分逐步隔离与支持登记，不改以下三轮冻结合同。[隔离评分](scoring_isolation.py)为每步创建独立模型投影，核引文后再核全文答案与原引文语境；第二阶段只能撤销证据支持。查询固定scope，关系描述不能通过别称表补证。[登记合同](support_contract.py)固定事实ID、非空合取组和完整有向路径，以字符区间追踪实际删文后的原引用位置；结构通过仍须语义审核。

[新运行器](evidence_contract_experiment.py)提供check／prepare／verify／run；[新分析器](evidence_contract_analysis.py)分别检查独立候选、实际模型请求及裁定分母。模型试验对照只改变第一阶段是否额外暴露旧评分载荷，其他阶段合同与提示相同。空步骤拒答没有第一阶段模型调用，两臂第二阶段输入相同，其差异只作重复采样诊断。新例参考EH-S09的父亲角色有争议，保留原件并排除确定分母。实际完成情况以[验证索引](../../QA_Generator/validation/README.md)为准。

```powershell
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/evidence_contract_experiment.py check
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/evidence_contract_experiment.py verify
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/evidence_contract_experiment.py run
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/evidence_contract_analysis.py offline
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/evidence_contract_analysis.py summarize
```

run先校验冻结摘要和独立预审，再从环境或隐藏交互取得凭证，使用deepseek-flash及原有官方Harness。每个单步和答案核验有独立会话，实际派生的第二阶段请求在调用前保存。成功与失败均保留，已有结果不按成败重跑；中途未形成结果的任务复用原请求／响应缓存继续。prepare只用于未使用的新冻结版本，不应改写既有目录。临时冻结前稿、过程验收及独立新例保存在[本轮工作区](../../workspace/quality-v3/evidence-contract-v5/)。

后续[片段目录适配](inventory_catalog.py)让模型只选绑定具体出现位置的span ID，程序精确展开原字符区间再执行v0.5校验；不增补支持组或修复路径。句与分句重叠不代表独立支持。单独[目录运行器](inventory_catalog_experiment.py)提供prepare／verify／run，当前10项均为已公开回归。两批已实跑的效果、失败与独立审核见[本轮报告](../../QA_Generator/validation/2026-10-22_评分证据隔离与支持登记合同修复.md)，结构通过不作为语义成功。

```powershell
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/inventory_catalog_experiment.py verify
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/inventory_catalog_experiment.py run
```

用途与修复边界见[技能试验规范](../../QA_Generator/specs/quality-skills-v0.3.md)。本模块不修改[旧原型](../multi_agent_v0/README.md)、[v0.2实现](../deletion_review_v2/README.md)及其冻结结果。正式发布仍关闭。

用户要求技能至少迭代几轮，执行[三轮开发协议](../../QA_Generator/specs/skills-iteration-v0.4.md)。首轮是诊断，不因文件已经写好而默认启用；三轮后也须根据收益与退化继续选择或修订。

| 文件 | 职责 |
| --- | --- |
| [review.py](review.py) | 单成员允许字段投影、有序证明检查、仅供复核的直答扫描、结构化审查合同与一致性门禁。 |
| [scoring.py](scoring.py) | 唯一实体／组合别称解析，分开答案、路径、定位和span代理；未知与登记外合法路径进入语义复核。 |
| [skill_loader.py](skill_loader.py) | 按角色显式读取技能正文与必要引用，冻结文件哈希；不安装全局技能。 |
| [experiment.py](experiment.py) | 本轮试验准备、真实请求合同冻结、独立预审门禁、generic／skills同输入对照及恢复。 |
| [iterate.py](iterate.py) | 第二、三轮版本化技能试验；前轮新例转回归，各轮加入独立新例，冻结实际请求并逐项恢复。 |
| [retrieval.py](retrieval.py)、[protocol_next.py](protocol_next.py) | 双臂共用的查询／原始证明卡、逐边字面检索窗口及明确0／1索引合同；不是技能效果。 |
| [analyze.py](analyze.py)、[analyze_iterations.py](analyze_iterations.py) | 原始裁定与程序门禁分开统计，技术／协议失败和未决分列；跨轮仅比较参考未变的共有案例。 |
| [多轮制例器](build_iteration_fixtures.py) | 独立制例者不读取技能和模型结果；新例只在当轮修订冻结后开放。 |
| [build_heldout.py](build_heldout.py) | 未读新技能／实现的独立制例者编写的新案例；新参考的修订轨迹保存。 |
| [测试审查](test_review.py)、[测试评分](test_scoring.py)、[测试加载](test_skill_loader.py) | 反例覆盖跨成员借证、父母角色、有序证明、别称冲突、假引用、替代路径及冻结哈希变化。 |

## 可调用的四个技能

[两步必要性](skills/two-hop-necessity/SKILL.md)、[逐成员证据](skills/member-evidence-audit/SKILL.md)、[语义评分](skills/semantic-score-review/SKILL.md)、[支持登记](skills/support-inventory/SKILL.md)。调用方选择review/scoring/inventory角色后，正文实际拼入官方Harness请求的skill字段，所加载文件SHA256在实验前冻结。模型文件、Shell与图工具全部关闭；技能不依赖工具内自行读文件。

上列是首轮正文，后续候选另存[修订目录](skill-revisions/)，不覆盖旧版。各轮是否完成及结论以[验证索引](../../QA_Generator/validation/README.md)为准，目录存在不代表技能已验证有效。

`project_member` 是可复用的输入边界API；运行器每次只送一个候选成员。`ordered_proof_check` 检查提交证明，不穷尽自然语言支持。`assess_structural` 的needs_semantic_review不作失败；`structural_proxy_success`也不是语义通过。评分角色可核对reference_claims，但参考不是独立GPT裁定，必须看当前材料。所有字段含义以代码合同为准。

## 首轮固定试验与后续运行

[run-001](../../artifacts/quality-v3/run-001/)是无模型调用的暂存版本，因锁定前性质测试发现API边界而保留并废止执行；[run-002](../../artifacts/quality-v3/run-002/)冻结修正代码、相同语义案例／标签与逐次真实请求合同。40review×2条件×3次、83scoring×2条件×1次、2inventory×2条件×1次，共410预定调用。旧诊断与独立新例分开，inventory不计准确率。

使用项目专用Python环境；系统Python没有安装Harness SDK，不应用于模型调用：

```powershell
workspace/harness-prototype/runtime/.venv/Scripts/python.exe -m unittest discover -s src/quality_v3 -p "test_*.py" -q
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/experiment.py verify
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/experiment.py run
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/iterate.py verify --round 2
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/quality_v3/iterate.py run --round 2
```

第三轮将round参数改为3，必须先完成本轮技能修订、独立制例开放、准备冻结与独立预审。本阶段三轮已实际完成410／478／546项，总1434逻辑调用、1450真实会话；协议失败93、技术失败0。实际效果与独立审核见[三轮报告](../../QA_Generator/validation/2026-10-22_质量修复与skills三轮迭代.md)，四技能仍是候选。分析器通过`--batch`、`--runtime`、`--out`指定本轮目录，可用`--previous-batch`与`--previous-runtime`比较相同案例，不能把新增案例混入提升分母。

run仅在独立审核签署准确五项摘要后执行，凭证由环境或隐藏输入读取，不写文件。复跑同job只读已有记录；成功、技术失败、协议失败均不覆盖。若改代码／技能／题目或提示，另开版本，不在旧冻结目录上调参。试验脚本的来源选择是本轮公开的回归设计，不是通用自主文集构建器。

过程数据在[工作区](../../workspace/quality-v3/)，旧无误伤语义裁定及新例参考都不进入被测输入。真实输入、schema与解析后的技能正文逐job冻结；分析必须与实际持久化request核对，不仅检查重建对象。新模型裁定和原机器分均保存，不能为减少误拦而省略误放统计。

[来源子集统计](supplementary_stats.py)区分文学来源、合成、无材料诊断、旧22误拦及旧34合法子集；重叠子集不相加。[交付整理器](package_iterations.py)只在三轮后审与精确报告字节审核通过后复制紧凑结果和文件哈希索引，不改变原运行。

## 支持出现位置与旧评分合同继续修订

[v7覆盖](inventory_coverage.py)、[v8出现位置](inventory_occurrences_v8.py)及[v9平坦登记](inventory_occurrences_v9.py)的失败实跑保留。最新[v10登记提示](inventory_occurrences_v10.py)、[评分投影](scoring_review_v10.py)、[窄角色门](scoring_semantics_v10.py)、[运行器](contracts_v10_experiment.py)与[分析器](contracts_v10_analysis.py)已完成54任务deepseek-flash实跑及独立逐原文验收：完整评分严格19/37、登记8/16，仍未整体通过。参见[v10协议](../../QA_Generator/specs/evidence-contracts-v0.10.md)、[冻结结果](../../artifacts/quality-v3/contracts-v10-run-001/README.md)与[持续验证报告](../../QA_Generator/validation/2026-10-22_支持覆盖与旧评分继续修复.md)。未知、协议通过和模型自审均不当作修复成功；旧结果不覆盖，候选未默认启用。
