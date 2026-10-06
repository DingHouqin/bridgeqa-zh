# BridgeQA ZH · B 组公开开发共享

此AI-conduct是独立parentless共享快照，保留运行所需代码、公开开发数据/参考、固定出处与转换追溯；不携带本地完整设计/审核历史、个人/课程研究原件、hidden、环境、权重或凭据。A负责数据和评测，B负责模型/优化与实验日志；训练调参范围、预算、联系人、模型和冻结日期仍须确认。

[接入与三轨合同](docs/20-b-group-handoff.md)给出可运行Oracle API、完整字段、合法拒答、分母与B应交回的实验元信息；[来源与AI披露](NOTICE.md)、[文件SHA清单](shared-manifest.json)。公开参考是dev-only评测数据，不作为模型输入。

| 独立轨道 | safe input | 公开参考 / 边界 |
|---|---|---|
| 候选22 / 6种子 / 3来源图簇 | data/pilot/model-inputs.jsonl | data/pilot/samples.jsonl；人审pending、正式0/null；真名语境仍可知识捷径 |
| 受控46 / 6家族 / 3拓扑簇 | data/controlled/inputs.jsonl | reference.json；全合成23可答/23不足，不是46独立种子 |
| Oracle61 / 22父记录 | build生成oracle-inputs.jsonl | 独立oracle-reference；有意给正确上游，只评该条件的单跳 |

PowerShell，Python3.10+标准库即可，无pip/uv或模型安装前提：

```powershell
git clone --branch AI-conduct --single-branch https://github.com/DingHouqin/bridgeqa-zh.git
cd bridgeqa-zh
$env:PYTHONPATH = Join-Path $PWD 'src'
python -S -m bridgeqa.cli export-input data/pilot/samples.jsonl --output artifacts/b-inputs.jsonl
python -S -m bridgeqa.cli baseline artifacts/b-inputs.jsonl --output artifacts/b-rule-predictions.jsonl
python -S -m bridgeqa.cli evaluate data/pilot/samples.jsonl artifacts/b-rule-predictions.jsonl --output artifacts/b-candidate-score.json
python -S -m bridgeqa.cli build --output artifacts/b-run
python -S -m bridgeqa.cli controlled --predictions artifacts/b-run/controlled/predictions.jsonl --output artifacts/b-controlled-score.json
```

模型只接对应input的schema_version/sample_id/question/question_language/instruction/documents，不接sample/reference/ledger的gold/seed/variant/attack/condition/root/hop/mapping。输出是UTF-8 JSONL：schema_version、对应sample_id、nonempty run_id、status、answer、support、submitted_steps；步骤含hop/head/relation/tail/qualifier/evidence。abstain时answer=null；error/缺失/格式坏不能当成功拒答。日志及有限latency_ms可附，原始输出必须保留。完整shape示例和三轨评分区别在接入合同。

build实际运行22+61+46并保存各自raw预测/score/manifest；Oracle必须用独立evaluate_oracle API，普通evaluate不能代替Oracle-CS。0.1旧9条工具夹具可单独evaluate，非0.2 Strict SR。可选Full Schema需jsonschema；标准库检查不冒称Full Schema。此树不包含完整旧package/reproduce脚本，不承诺那些历史命令可用。

模型/B组实验未运行（null），规则只针对公开文法开发，人审pending、正式0。匿名文本干预和可见链不证明LLM内部必要多跳、泛化或消除全部知识/结构捷径。闭源Codex助手参与规划、代码、候选/合成参考和技术审查，教师对辅助范围的解释仍待确认。本版Browser渲染、点击、下载体验未实测。代码许可证由团队决定，没有给全部代码新授权；文学改编与OpenCC许可分别保留。

B请交三轨分别命名预测及实际评分/分母、输入输出SHA、原始模型文本/失败/转换日志，以及model精确revision/许可/总参数严格<30B、prompt版本与SHA、公开dev使用、随机种子、解码、上下文/截断、运行时间、latency/token和依赖环境。预算、B0/B1及正式hidden冻结另确认。
