# 证据绑定的 pass 评分器 v15

本目录实现同题重复采样的 pass@1、pass@5、pass^5，分别判断最终答案、逻辑证明和输出合同。程序负责采样账本、来源核验及精确聚合；自然语言证明先经独立审查，再由 Root 验收。不能判清的内容保留 `needs_review`，不能把格式通过、结构通过或未决当成功。实现为[评分器](scorer.py)、[首次采样准备](prepare_trial.py)、[首次采样执行](run_initial.py)和[测试](test_scorer.py)。

完整逐跳／捷径结论和本轮真实验证见[日期化报告](../../QA_Generator/validation/2026-10-27_逐跳捷径审查与pass指标评分器.md)。本版适配[当前 v14 合成开发题库](../../data/obstacle_hops_v14/README.md)，不是所有历史版本的通用自动语义裁判。

## 三种指标

同一道题，在相同有效协议下预先登记 n 个首次独立作答槽，c 个成功，n≥5：

| 指标 | 精确估计式 | 含义 |
|---|---|---|
| pass@1 | c/n | 单次作答成功率的估计；另保留序号0那次的实际成败。 |
| pass@5 | 1−C(n−c,5)/C(n,5) | 随机抽取五次，至少一次成功。 |
| pass^5 | C(c,5)/C(n,5) | 随机抽取五次，五次全成功。 |

pass@k 的组合式见 [HumanEval 论文 §2、附录A](https://arxiv.org/pdf/2107.03374)及[官方实现](https://raw.githubusercontent.com/openai/human-eval/master/human_eval/evaluation.py)；pass^k 的组合式见 [τ-bench 论文 §3](https://arxiv.org/html/2406.12045v1)及[官方实现](https://raw.githubusercontent.com/sierra-research/tau-bench/main/tau_bench/run.py)。代码使用整数二项式和有理数，输出分子、分母和小数。

例如 n=5、c=4 时，三者是0.8、1、0；不能把最后一项算成0.8的五次方。n=10、c=5时，后二者分别是251/252、1/252。n<5时五次指标为空，不靠幂次公式外推。先逐题计算，再按题宏平均；另列家族宏平均及每家族分母。不能把全库平均准确率代入五次公式。

## 判定单位与边界

| 维度 | 成功要求 | 不应混淆的情况 |
|---|---|---|
| `answer` | 外层状态正确，最终目标集合完整且语义等价，数值、单位、全部并列方案正确。 | 后面的正确解释不能覆盖明确错误的最终答案。 |
| `logical_proof` | 答案正确，并有充分、真实且一致的可核对推导。 | 接受短证明、上下界、剪枝及合法替代证明；不强迫照抄参考路径。冻结规则不接受仍留在作答中的错误操作，具体见每次计划的 rubric。 |
| `output_contract` | 前两维通过，原始直接 JSON、Schema、要求的事实ID、候选路径全集、连续逐字引用和一致性均符合合同。 | 引文拼接、ID误写、无关路径漏枚举可以只造成合同失败；不能自动判成错误推理。 |

每维为 `pass / fail / needs_review`。输入或 gold 待复核时，该题隔离、单列计划数及隔离数，不进入合格题宏平均，也不算模型错或模型对。合格预注册题内的槽分母固定：缺执行槽、技术失败和未决语义均留在该题原计划分母；不补采成功答案替换它们。已提交的裁决与实际计分状态分别保存。

未决有 u 个时，分别用 c 和 c+u 代入公式形成可识别上下界。这是未知标签的可能范围，**不是置信区间**；尚有未决时，即便上下界碰巧相同，正式点估计仍为空。主报告固定全部合格计划题；完整案例补充分析明确列自己的分母。

主问题、正确上游独立节点、控制题分别汇总。缺证题的完整母题跳数不当成该缺证成员的实际跳数。局部功能依赖、声明跳数和已限定合同下认证的跳数分开；当前语料没有全局“无捷径”认证，不能把答对或路径列全当成认证。

## 评分前的两个资格门

1. **题材资格**：[204项逐输入资格](../../workspace/hop-audit-v15/input-qualification-root-r1.json)绑定公开输入和 gold 哈希。两道原题因实际材料的类型／竞争链问题保留复核；另外202项仅在报告声明的局部语义范围内合格，未获全局抗捷径保证。
2. **采样资格**：相同请求 JSON 还不足以证明完整有效提示相同；运行时可能注入额外上下文。评分器需要独立审查并由 Root 批准的采样资格侧表。未提供侧表，或已验收侧表的决定为 `needs_review`／`fixed_cohort_only` 时，正式点估计关闭，描述统计独立保留。若提交的侧表自身仍是pending、未获Root批准、哈希不符或不符合合同，程序直接拒绝生成报告。只有已验收的 `protocol_qualified_under_iid_assumption` 可以开放正式点估计；这仍依赖声明的 provider 稳定性与独立采样假设，不能声称数学上证明了远端随机流独立。

侧表、语义裁决均是可信的本地审查输入。哈希可以发现陈旧、混用或文件改变，不能证明审查者的语义判断必然正确，也不是远端模型签名。

## 复算已完成的本轮结果

从项目根目录运行，使用当前环境中已有的 Python 与 jsonschema：

```powershell
workspace/harness-prototype/runtime/.venv/Scripts/python.exe evaluation/pass_metrics_v15/scorer.py `
  --plan workspace/hop-audit-v15/initial-trials/four_structures_r2-deepseek-flash/plan.json `
  --records workspace/hop-audit-v15/initial-trials/four_structures_r2-deepseek-flash/records-adjudicated-r1.json `
  --sampling-qualification workspace/hop-audit-v15/initial-trials/four_structures_r2-deepseek-flash/sampling-qualification-root-r1.json `
  --output workspace/hop-audit-v15/initial-trials/four_structures_r2-deepseek-flash/metrics-reproduced-r1.json
```

另一个模型把四个参数中的目录名统一换为 `four_structures_r2-gpt-6-luna`。原始40份首次回答、原始账本及预注册计划不改；[DeepSeek 运行目录](../../workspace/hop-audit-v15/initial-trials/four_structures_r2-deepseek-flash/)和[Luna 运行目录](../../workspace/hop-audit-v15/initial-trials/four_structures_r2-gpt-6-luna/)保留证据与裁决。四题是事先选定的集成用例，不能外推为全库准确率或独立测试集成绩。

本轮[DeepSeek正式报告](../../workspace/hop-audit-v15/initial-trials/four_structures_r2-deepseek-flash/metrics-r1.json)按已观察到的worker上下文差异保持正式点为空，结果见其中 `descriptive_cohort`。这正是门禁预期行为。[Luna正式报告](../../workspace/hop-audit-v15/initial-trials/four_structures_r2-gpt-6-luna/metrics-r1.json)经[限定采样资格](../../workspace/hop-audit-v15/initial-trials/four_structures_r2-gpt-6-luna/sampling-qualification-root-r1.json)放行：答案三指标为0.75／1／0.5，证明为0.6／1／0.25，合同为0.45／0.75／0.25，顺序均为@1／@5／^5。它们只在明确的本地入口、环境／CLI／provider稳定及条件iid假设下适用。

采样资格侧表的可运行完整例子就是上述文件。必填版本 `bridgeqa-sampling-qualification-v15`、`status=accepted`、三选一的 `decision`、`configuration_sha256`、实际 `plan`／`records` 的path+sha256引用、非空结构化审计 `evidence` 引用、两个注册 `reviewers`、Root的 `approved_by`、`independent_review=true`、非空 `rationale`、`independence_scope=conditional_iid_assumption_not_proven` 和 `provider_independence_proven=false`。资格声明须有实际独立审查，不能复制例子替其他批次放行。

每份语义裁决必须绑定实际计划文件、输入、gold、配置、rubric、raw 输出哈希，明确 `status=accepted`、两个不同的注册 reviewer、Root 的 `approved_by`、独立审查标记及具体理由。最终目标错不能获得整条证明成功；合同成功还必须通过对原始直接 JSON 的程序校验。不能直接把未核对的模型自评填成裁决。

## 新采样与恢复

```powershell
# 只冻结计划与输入，0次模型调用；每次用未使用的新label。
workspace/harness-prototype/runtime/.venv/Scripts/python.exe evaluation/pass_metrics_v15/prepare_trial.py `
  --label my_frozen_trial --model deepseek-flash --trials 5 `
  --cases LIT-3A-base HIS-3B-key_rewire SCI-4A-base LOG-4B-base

# 此命令产生真实调用；凭证只从用户授权的本地文件读取，不写入实验文件。
workspace/harness-prototype/runtime/.venv/Scripts/python.exe evaluation/pass_metrics_v15/run_initial.py `
  --plan workspace/hop-audit-v15/initial-trials/my_frozen_trial-deepseek-flash/plan.json `
  --credential-file E:/Template.txt

workspace/harness-prototype/runtime/.venv/Scripts/python.exe -m unittest discover `
  -s evaluation/pass_metrics_v15 -p 'test_*.py' -q
```

准备程序目前依赖完整当前 checkout 中的 v14 输入、资格侧表及旧运行的环境快照；执行时重新核对实际 SDK／CLI／配置，不是仅拷贝三份代码就可复跑的独立软件包。SDK 的 worker 目录上下文差异是本次已发现的限制，未经新的运行时修订及资格审查，不能由新 label 自动升级为同完整提示的正式评估。

执行器对每槽只运行一次，先落开始回执，保留无效 JSON 和超时的原文／进程证据；恢复有回执但无回答的槽时保持技术未决，不重新生成。OS 排他锁防止同计划并发重跑。格式修复、换提示、改材料、独立节点和历史响应均不能凑成五次同题首次采样。相同文本若来自五个独立会话可合法重复；复制 raw、复用 session 或另一个槽的输出会被拒绝。

这是保守的可验收评分流程，不是无须人工／强智能体裁决的自动放行器。后续更改 rubric、题材、实际提示或采样协议时须冻结新计划，保留原始失败与争议。
