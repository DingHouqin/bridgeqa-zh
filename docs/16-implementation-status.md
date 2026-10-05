# 实施状态

## 当前已有

- 完整方案、课程映射、A/B 协议草案、成员分工与相对周计划。
- JSON Schema、纯虚构二三四跳 control/attack（含三跳中英变体）、手写预测夹具。
- 标准库 CLI：ID/字段/支持句/线性路径/配对不变量的基础结构检查。
- 参考评分：规范答案精确匹配、支持句 F1、提交步骤诊断、seed 宏平均 drop/ASR；没有真实模型结果。

## 待实现

最新 [设计草案](17-benchmark-spec-proposal.md) 新增 Strict SR、Path-CFS、独立 Oracle-CS、有效多证明及反向/歧义评分建议；均未修改当前评分器或 v0.1 Schema。`configs/benchmark-spec.proposal.json` 是建议参数，不是运行配置。

[贡献定位](18-purpose-and-contributions.md)、[验证计划](../experiments/plans/contribution-validation.md) 与报告/证据模板已落入文档；C1–C4 效果状态仍为 planned。文档验收映射不代表真实题库、生成器、独立干预 runner 或新增评分已经完成。

| 模块 | 主责 | 输入/输出 | 依赖与验收 |
|---|---|---|---|
| ingest | A2 | 原语料→稳定句与来源 | 来源许可、分句与 gold 单位核对 |
| generation | A2/A3 | seed+spec→candidate | 保留 gold、修改记录与人工唯一性 |
| annotation | A3 | candidate→review/gold | 独立审核与争议裁决 |
| splits | A1 | seed clusters→manifest | 共享组件/近重复审查 |
| retrieval | A2/A4 | query+corpus→ranked docs | 固定语料与 index version |
| models | A4/B 组 | public input→prediction | 合规模型、本地运行与版本 |
| evaluation | A4 | gold+pred→完整指标 | 文本 F1、多路径、检索、CI/逐题格式错误归类 |
| analysis | A1/A4 | metrics→统计与图表 | 主比较预定义、分层/簇 CI |
| demo | A4 | 公共样例+授权输出→展示 | 显示版本、缓存标识与无网演示 |

目录内 README 是实施约定，不是算法已实现的声明。轻量 CLI 不证明 schema 全符合或语义正确；可选安装 jsonschema 后按 schemas 做完整格式校验，语义仍依靠人工。v0.1 Schema/评分只支持单答案链式 context_attack，其他挑战集需新增协议。

当前预测协议是评测端标准化后的结构；CLI 不实现答案文本到 canonical_id 的映射，不代表要求模型知道私有实体 ID。空 submitted_steps 表示未提交，不自动判定每跳错误。格式损坏的文件/支持句会被拒绝；正式 runner 需先将逐题失败据实归为 status=error，保存原始输出和错误原因，再计入总分母。
