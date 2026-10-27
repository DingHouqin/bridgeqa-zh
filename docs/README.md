# 研究文档

2026-10-27最新资料：[Luna／Sol详细表现及逐题阅读说明](../model-testing/luna_sol_v18_publication.md)、[现有评分器指标与过程评价实现](../evaluation/SCORING_GUIDE.md)、[最新题目网页](https://dinghouqin.github.io/bridgeqa-zh/#/latest)、[逐题表现网页](https://dinghouqin.github.io/bridgeqa-zh/#/results)。[252项任务公开投影](../explorer/publication_v18/README.md)含50条合成开发扩展这一阶段子集，提供清洁输入、审阅索引和504份原答裁决，标准答案与证明包本轮未公开。本轮完成证据绑定聚合，争议保留U；不代表正式测试集或全局无捷径认证完成。下面保留早期安排与历史快照，现状以日期化验证报告为准。

2026-10-21那轮86题审查记录已[归档](../data/human-review/archive/2026-10-21-pilot-v0.5/README.md)，原人工审查页面和写入已停用；题库与研究文档继续保留。该归档不消除最新实验中仍需人工／强智能体复核的U项。归档明确区分既有评价与智能体辅助提交，不把已完成状态等同于独立人工复核。

当前入口为 [多跳问答 benchmark 系列调研](benchmark-survey/README.md)。调研覆盖任务结构、干扰构造、歧义与反向推理、评测及中文迁移，资料核验日期为 **2026-10-07**。

本次补回的研究主线见 [多步骤评判与核心创新点回收](benchmark-survey/09_多步骤评判与核心创新点回收.md)：完整成功、路径依赖、正确上游下的部件能力、跨条件一致性和协议有效性审查。

正式构题机制已集中到[多智能体独立目录](../QA_Generator/README.md)，从[架构图](../QA_Generator/architecture.md)与[执行规范](../QA_Generator/specs/workflow.md)进入。用户选择及总体范围见[设计记录](../QA_Generator/design/2026-10-20_多智能体构题系统方案.md)：五个智能体、双轨题目家族、DeepSeek Flash及重要分歧GPT复核。[2026-10-21最小贯通交付](../QA_Generator/validation/2026-10-21_五智能体最小贯通交付.md)当时完成一个四成员开发家族，含一次GPT定点裁定；其数量与当时抽审方案是历史记录，后续范围和当前边界以[验证索引](../QA_Generator/validation/README.md)及[最新实测](../model-testing/luna_sol_v18_publication.md)为准。设计讨论中的“既有人工审查已结束”不改变各批真实审查记录。

据文学与历史主题构建的 [首轮候选 benchmark](../data/pilot_literature_history_v0/README.md) 已建立组合与题目追溯，人工审题入口为 [题目审阅册](../data/pilot_literature_history_v0/题目审阅册.md)。这批是开发原型，没有模型实跑或独立人工复核。

题目、标签、证明图和潜在干扰可在 [可视化审查系统](../explorer/README.md) 查看；系统的 [实现前规格](../explorer/specs/README.md) 定义了页面、筛选、来源及推定边界。

早期评分实施缺口见 [2026-10-07评分器可执行性评估](report/2026-10-07_评分器可执行性评估.md)，该文是历史快照。当前已有[证据绑定的v15可执行聚合器](../evaluation/pass_metrics_v15/README.md)，以独立语义裁决和资格门为前提；详细实现及边界见[评分器说明](../evaluation/SCORING_GUIDE.md)，不能据此声称自然语言评分已全自动化。

迁移方案见 [在线文档网站可行性评估](report/2026-10-07_在线文档网站可行性评估.md)，实施规则见 [静态发布与文档](../explorer/specs/06_静态发布与文档.md)。[在线文档目录](https://dinghouqin.github.io/bridgeqa-zh/#/docs/index) 复用原生前端、静态导出和章节路由。

既有参考材料归入 [报告归档](report/README.md)。其中 [研究设计参考报告](report/2026-10-07_研究设计参考报告.md) 仅供参考，不用于项目决策。

目录使用遵循 [项目工作规范](../AGENTS.md)。通用研究文档放在本目录，多智能体机制资料维护于[独立目录](../QA_Generator/README.md)，临时检查记录放在 [workspace/](../workspace/)，正式实验产物放在 [artifacts/](../artifacts/)。

项目完成状态见 [项目进展报告](report/2026-10-07_项目进展报告.md)，具体任务分发、依赖和验收标准见 [工作计划](工作计划.md)。进展快照与持续更新的计划分别维护。
