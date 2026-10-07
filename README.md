# BridgeQA-ZH｜中文多跳问答对抗 benchmark

以文学与历史为取材主题，构建多场景、多步骤的中文问答对抗测试数据，检查模型在角色、关系、条件、时间、噪声及背景知识干扰下的证据依赖与鲁棒性。

当前已完成文献调研、首轮候选集和可视化审查系统。主研究方向是完整合法证明、依赖传播、正确上游节点诊断及跨条件一致性；不是模型训练或优化项目。研究定义见 [核心评判与创新点](docs/benchmark-survey/09_多步骤评判与核心创新点回收.md)。

## 从这里开始

- [文献与场景调研](docs/benchmark-survey/README.md)：相关 benchmark、构题机制与评测口径。
- [场景单元与中文构题配方](docs/benchmark-survey/07_场景总表与中文构题配方.md)：32个非互斥候选单元。
- [当前数据集说明](data/pilot_literature_history_v0/README.md) 与 [题目审阅册](data/pilot_literature_history_v0/题目审阅册.md)。
- [可视化系统](explorer/README.md)：选题、筛选、正确证明和潜在干扰。
- [固定测试指引页](http://127.0.0.1:8765/#guide)：运行服务后查看各数据集文件的使用方法。
- [项目工作规范](AGENTS.md)：目录授权、分支限制、材料引用与质量要求。

## 当前数据集

| 数据集 | 范围 | 状态 |
| --- | --- | --- |
| [pilot_literature_history_v0](data/pilot_literature_history_v0/README.md) | 10个组合、20个家族、128条主任务记录；文学/历史各64条，覆盖27个实际场景单元；58条独立节点诊断另列 | 开发候选集，尚无独立人工复核和模型实跑 |

128条包含同家族配对变体，不是128道独立原始题。来源记载、文学故事、合成设定与反事实世界分别标记。结构校验或可视化验收不代表已经验证攻击有效，也不代表评分器或正式测试集已冻结。

## 目录

| 目录 | 用途与入口 |
| --- | --- |
| [data/](data/README.md) | 版本化数据、引文快照、家族种子、模型输入与评测标注；目前仅首轮候选集。 |
| [docs/](docs/README.md) | 文献调研、研究协议与报告归档。 |
| [docs/benchmark-survey/](docs/benchmark-survey/README.md) | benchmark系列调研、场景目录与评测方案。 |
| [docs/report/](docs/report/README.md) | 既有报告归档；参考报告只作参考，不用于决策。 |
| [src/](src/) | 数据构建和校验代码；当前 [构建器说明](src/pilot_literature_history_v0/README.md)。 |
| [evaluation/](evaluation/README.md) | 评测配置、评分与错误归因位置；当前尚无正式评分器，[可执行性评估](evaluation/评分器可执行性评估.md) 列出实现缺口。 |
| [artifacts/](artifacts/) | 保留的正式实验输出和分析产物；不等同临时检查。 |
| [workspace/](workspace/) | 临时检查、日志和截图；[数据检查](workspace/pilot_literature_history_v0/README.md)、[系统检查](workspace/explorer/README.md)。 |
| [explorer/](explorer/README.md) | 本地只读可视化系统、[设计规格](explorer/specs/README.md)及接口/浏览器测试。 |
| [.github/](.github/) | 已有仓库协作配置，不属于模型题面材料。 |

## 本地运行

在项目根目录启动系统：

~~~powershell
python explorer/server.py --port 8765
~~~

命令对应 [服务器](explorer/server.py)；Windows也可使用 [启动脚本](explorer/start.cmd)。打开 [本地网页](http://127.0.0.1:8765/)，按“01 选题概览”“02 题目与证据”“03 测试指引”导航。系统运行仅需Python标准库和浏览器；测试工具依赖见 [系统说明](explorer/README.md)。

重建候选集：

~~~powershell
python src/pilot_literature_history_v0/build_pilot.py --self-test
~~~

对应 [构建器](src/pilot_literature_history_v0/build_pilot.py)。该命令会重写候选集的可再生成文件；正式模型运行前应先保存数据版本与散列快照，运行期间不重建。

## 资料与工作边界

未经明确授权不查看其他Git分支；新增一级目录仍按 [工作规范](AGENTS.md) 执行。所有具体文件与网页引用应有跳转链接。

[研究设计参考报告](docs/report/研究设计参考报告.md) 已归档，内容不变，仍仅供参考，不参与设计决策。项目选择依据用户要求、可核验资料和实际检查；未复跑的历史陈述不能作为当前模型结果。

