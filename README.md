# BridgeQA ZH

面向原生中文与中英混合证据的多跳问答对抗评测项目，服务于《认知智能前沿技术与实践》任务 5 的 A 组。A 组负责数据、构建算法、标注和评测协议；B 组负责模型与优化，双方共同完成普通与对抗条件的比较。

当前版本是**设计文档与可运行的最小工具骨架**。真实数据、攻击生成器、检索器、模型调用和正式实验尚未实现。`data/examples/` 中的事实与预测均为人工编写的虚构演示夹具，不代表模型实验结果。

## 从这里开始

1. 阅读 [项目范围](docs/01-scope.md) 和 [课程要求对应表](docs/14-course-requirements.md)。
2. 四名成员认领 [协作分工](docs/11-collaboration.md)，与 B 组讨论 [接口协议](docs/10-ab-contract.md)。
3. 按 [领域与数据策略](docs/03-data-strategy.md) 制作试题，参照 [标注手册](docs/05-annotation-guide.md) 交叉审核。
4. 阅读 [贡献流程](CONTRIBUTING.md)。使用 AI 助手或修改代码前，阅读 [AGENTS.md](AGENTS.md)。

## 核心设计

- 中文原生题承担主要结论；英文 benchmark 翻译题用于启动、开发和参照。
- 覆盖 2、3、4 跳，三跳为主体；25% / 60% / 15% 是待试运行确认的比例。
- 采用 `gold_only → clean_control → adversarial` 三种上下文，攻击只改变一个主要因素。
- 中英子集复用同一事实图，区分英文证据所在跳、语言边界位置、切换次数。
- 同时报答案、证据、逐跳结果；模型提交的路径不等同于内部推理过程。
- 歧义与反向问题单列题型集，不能自动并入答案保持不变的上下文攻击。

所有建议、待定事项与后续变更见 [决策记录](docs/02-decisions.md)。

已有 benchmark 的构造、可复用部分与创新边界见 [文献与 benchmark 索引](docs/references/benchmark-review.md)；原报告与课程文件保存在 [参考资料](docs/references/README.md)。

## 文件导航

```text
bridgeqa-zh/
├── AGENTS.md / README.md / CONTRIBUTING.md
├── pyproject.toml                 Python 包与命令入口
├── configs/                       数据目标、协议、模型配置草案
├── schemas/                       样本与预测 JSON Schema
├── docs/                          设计、流程、标注、评测、协作和交付规范
│   └── references/                课程原件、原研究报告、文献索引
├── data/                          原始、标准化、候选、公开和隐藏数据
│   └── examples/                  可公开的纯虚构演示夹具
├── src/bridgeqa/                   CLI、结构校验、参考评分器、待实现模块
├── scripts/                       不依赖网络的 PowerShell 示例检查
├── annotation/                    审核与裁决表模板
├── experiments/                   实验计划、运行清单模板
├── reports/                       期中、期末报告与演示大纲
├── artifacts/                     本地结果与缓存，默认不进入 Git
└── tests/                         后续验证计划
```

## 运行示例

要求 Python 3.10 或以上。在仓库根目录执行；仅使用标准库，不需要下载模型或访问网络：

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m bridgeqa.cli validate data/examples/samples.jsonl
python -m bridgeqa.cli evaluate data/examples/samples.jsonl data/examples/predictions.jsonl
```

也可以运行 `scripts/check_examples.ps1 -PythonExe <python可执行文件路径>`。安装为本地包后，入口为 `bridgeqa`。参考评分器目前实现规范答案精确匹配、支持句集合 F1、提交路径的首次不一致位置，以及按种子题聚合的成对下降和 ASR。答案文本 F1、置信区间、检索评测和完整语义验证仍待实现，见 [工具状态](docs/16-implementation-status.md)。

初始检查结果及未验证范围见 [仓库检查记录](reports/repository-check.md)。

## 数据和成果边界

公开开发集可包含公开 gold；隐藏题、标签、路径、攻击位置和模型输出仅放入 `data/private/`、`experiments/private/` 或 `artifacts/`。这些目录默认忽略。交付课程材料时仍须通过单独的私有打包流程向教师提交完整数据，不能把 Git 忽略理解为不交付。

真实数据发布前核查逐项许可与归属。课程要求正式项目中不能使用闭源大模型；本仓库将模型、翻译、生成和自动裁判限定为人工、规则或符合参数限制的开源模型。所有 AI 工具辅助均据实记录于 [AI 使用表](reports/ai-usage.md)。

## 当前下一步

完成分工与 A/B 协议；各跳数先做约 20 道试题，统计审核耗时、合法率、捷径与可回答性；依据结果冻结领域和取样比例。尚未选择主领域、锁定硬件或完成真实模型实验。
