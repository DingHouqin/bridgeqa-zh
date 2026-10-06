# B 组接入：公开开发数据与三轨评分

2026-10-07。A负责来源、候选、匹配干扰与评分，B负责模型调研、推理/优化及实验日志；联系人、资源、训练/调参范围、预算、模型与最终冻结日期仍须双方确认。此材料提供公开开发调试，不包含hidden，不代表双方已确认所有研究设计。

## 输入与公开参考

| 轨道 | 模型可读 | 仅供公开开发评测 / 构造审计 |
|---|---|---|
| 真名候选 | data/pilot/model-inputs.jsonl，22条 | data/pilot/samples.jsonl、review-ledger/pair-audit及来源派生元数据 |
| 受控合成 | data/controlled/inputs.jsonl，46条 | data/controlled/reference.json、construction-manifest.json |
| 正确上游Oracle | build生成的artifacts/b-run/oracle-inputs.jsonl，61条 | 同run的oracle-reference.json，供独立Oracle-CS评分 |

普通与受控input严格只有schema_version、sample_id、question、question_language、instruction、documents。documents只有中性doc_id/title/language/sentences，句子只有sent_id/text。不得把sample/reference/ledger/construction-manifest、seed/variant/attack/gold、condition/root/hop或实体映射拼入模型输入。参考可用于公开dev调试，是否训练/调参须登记并先确认；不能把此模式用于隐藏题。

22候选是《三国演义》毛本小说叙事的6种子/3来源图簇，全部candidate、人审pending，正式0/指标null；真名及语境仍可能知识捷径。原HTML/TXT/span与简体派生分开，固定字形转换不做语义校订。46受控条件属于6家族/3来源拓扑簇，23可答/23不足；两平行链、桥替换、逐hop缺证、顺序干预和无资料均合成，不是原著引文、人审gold或46独立种子。Oracle有意提供正确上游/关系/限定，只描述该额外条件下的单跳，不反推模型内部因果传播。可观察证明不等于内部多跳，匿名化也不保证消除记忆/结构捷径。

## 标准库启动与三轨命令

Python3.10+即可；`-S`不依赖pip/uv、模型或网络。PowerShell在共享仓库根目录执行：

```powershell
git clone --branch AI-conduct --single-branch https://github.com/DingHouqin/bridgeqa-zh.git
cd bridgeqa-zh
$env:PYTHONPATH = Join-Path $PWD 'src'
python -S -m bridgeqa.cli export-input data/pilot/samples.jsonl --output artifacts/b-inputs.jsonl
python -S -m bridgeqa.cli baseline artifacts/b-inputs.jsonl --output artifacts/b-rule-predictions.jsonl
python -S -m bridgeqa.cli evaluate data/pilot/samples.jsonl artifacts/b-rule-predictions.jsonl --output artifacts/b-candidate-score.json
python -S -m bridgeqa.cli build --output artifacts/b-run
python -S -m bridgeqa.cli controlled --predictions artifacts/b-run/controlled/predictions.jsonl --output artifacts/b-controlled-score.json
# 独立0.1旧工具夹具（非0.2 Strict SR或真实成绩）
python -S -m bridgeqa.cli evaluate data/examples/samples.jsonl data/examples/predictions.jsonl --output artifacts/b-legacy-fixture-score.json
```

build真实运行22正常规则、61Oracle与46受控，生成各自inputs/reference/predictions/score/manifest。这里baseline是针对公开文法开发的规则，不是LLM/B组实验，也不应使用它模拟真实模型输出。已有normal run可重建，但不能指向source/private/runtime目录；输出写入artifacts。完整本地历史的package/reproduce脚本不在共享树，不向B承诺其可用。可选Full JSON Schema需另安装jsonschema，标准库合同不冒称Full Schema。

本地HTTP可用`./scripts/start_demo.ps1 -PythonExe python`，或者`python -S -m bridgeqa.cli serve --output artifacts/b-demo --port 8768`。本版浏览器渲染、点击、下载体验仍未实测；页面实现和本地HTTP/API检查不等于浏览器PASS。代码/数据变动须重启服务。

Oracle评分须用独立API；普通evaluate不等于Oracle-CS。保存下面程序为artifacts/score_oracle.py，再`python -S artifacts/score_oracle.py`：

```python
import json
from pathlib import Path
from bridgeqa.io import read_jsonl
from bridgeqa.pipeline import evaluate_oracle
from bridgeqa.controlled import read_submission, write_strict_json
run = Path('artifacts/b-run')
reference = json.loads((run / 'oracle-reference.json').read_text(encoding='utf-8'))
predictions = read_submission(run / 'oracle-predictions.jsonl')
samples = read_jsonl('data/pilot/samples.jsonl')
score = evaluate_oracle(reference, predictions, samples)
write_strict_json(run / 'b-oracle-score.json', score)
print(score['counts'])
```

换成B的oracle预测文件即可评估。Oracle输出core为schema_version/sample_id/run_id/status/answer/support，submitted_steps可选且只作diagnostic。Oracle-CS要求目标EM及显式支持精确匹配同一个备选；步骤错或额外步骤不自动改CS。缺/未知/重复支持与非法core会失败，unknown/duplicate ID拒整批，61节点依赖22父记录及6种子。

## 0.2模型输出示例与评分

先从对应input取得真实sample_id，不能自造或沿用另轨ID。普通/受控每行一个UTF-8 JSON对象，完整字段示例（ID、实体、引用应替换为该题真实提交）：

```json
{"schema_version":"0.2","sample_id":"q_000000000000000000000000","run_id":"b-model-v1","status":"ok","answer":{"text":"答案文本"},"support":[{"doc_id":"d1","sent_id":0}],"submitted_steps":[{"hop":1,"head":"起点","relation":"父亲","tail":"终点","qualifier":"","evidence":[{"doc_id":"d1","sent_id":0}]}],"raw_output":"模型原始输出","error_message":null,"latency_ms":1000}
```

这个shape示例不是任何题的有效预测或参考证明；实际多跳须完整h步、连续hop/head-tail、规范relation与精确qualifier，不能只填一跳求通过。规范通用词表在input.instruction；不要填自由CoT。全局support是逐步evidence精确并集，引用来自当前材料句槽。answer.text使用正文实体，别名只由冻结评测端处理，不给模型规范ID映射。

资料不足的受控题可合法拒答：

```json
{"schema_version":"0.2","sample_id":"q_000000000000000000000000","run_id":"b-model-v1","status":"abstain","answer":null,"support":[],"submitted_steps":[],"raw_output":"模型原始拒答","error_message":null,"latency_ms":1000}
```

可提交已走通的连续前缀0..h−1步，known唯一事实引用且support为精确并集；名册/缺信息marker不是证据。合法拒答只证明输出合同成立，不认证识别缺边的语义过程。error、缺失、格式错、满h步或非法partial不算正确拒答。candidate拒答不算答对。

Candidate：Answer EM独立看答案，支持F1在同一完整参考内比较，Strict SR须答案/完整步骤/限定/精确支持匹配同一个证明，Path-CFS看正确前缀/h×100。答案不变而证据坏可EM1/SR0。known缺预测/拒答/error保留分母；unknown/duplicate ID拒批。正常成对先题内再seed宏、逐机制Drop/ASR，正式分区为0/null。

Controlled：可答沿用EM/F1/SR/CFS，不足用correct_refusal；条件内先root的逐hop均值，再6root宏。总contract每root五类等权再root宏，bridge全部11对保留。和candidate/fixture/Oracle分开，不称模型accuracy或捷径消除率。

保留原JSONL、run_id、raw_output/error_message、实际latency和输入/输出SHA；不得静默修补格式。controlled严格parser拒duplicate keys、NaN/Infinity及任意nested正负1e999，坏JSON不猜身份，独立parseerror保存原文本/bytes SHA。finite数值仍须通过字段合同。模型原始文本与任何格式转换日志另存，不能把转换结果冒称原始合法输出。

## B应交回什么

每次run提供三轨分别命名的预测JSONL、输入文件SHA和实际评分JSON/分母；原始模型输出、失败/拒答及转换日志不得删除。登记model名称、精确revision/commit、许可证、总参数计数（严格<30B；MoE保守计总参数）、prompt版本/全文SHA、公开dev训练调参使用、随机种子、temperature/top_p/最大token等解码配置、上下文预算/截断、依赖环境、每题latency/token用量和实际运行时间。B0/B1优化前后版本与冻结日期另确认；没有实跑时写未运行/null。

本轮闭源Codex助手参与规划、代码、候选/合成参考整理和技术审查；不冒充真人审核或合规开源模型实验。辅助范围仍待教师解释。文学/OpenCC来源和改动见各NOTICE/资源LICENSE，代码发布许可由团队决定，未给全部代码新授权。共享树不含个人/课程研究原件、hidden、环境、权重、凭据或完整历史；本地完整成果保留。
