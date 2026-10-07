# 研究文档

当前入口为 [多跳问答 benchmark 系列调研](benchmark-survey/README.md)。调研覆盖任务结构、干扰构造、歧义与反向推理、评测及中文迁移，资料核验日期为 **2026-10-07**。

本次补回的研究主线见 [多步骤评判与核心创新点回收](benchmark-survey/09_多步骤评判与核心创新点回收.md)：完整成功、路径依赖、正确上游下的部件能力、跨条件一致性和协议有效性审查。

据文学与历史主题构建的 [首轮候选 benchmark](../data/pilot_literature_history_v0/README.md) 已建立组合与题目追溯，人工审题入口为 [题目审阅册](../data/pilot_literature_history_v0/题目审阅册.md)。这批是开发原型，没有模型实跑或独立人工复核。

题目、标签、证明图和潜在干扰可在 [可视化审查系统](../explorer/README.md) 查看；系统的 [实现前规格](../explorer/specs/README.md) 定义了页面、筛选、来源及推定边界。

评分实施现状和最小缺口见 [评分器可执行性评估](../evaluation/评分器可执行性评估.md)。当前尚无完整可执行评分器。

迁移方案见 [在线文档网站可行性评估](在线文档网站可行性评估.md)，实施规则见 [静态发布与文档](../explorer/specs/06_静态发布与文档.md)。[在线文档目录](https://dinghouqin.github.io/bridgeqa-zh/#/docs/index) 复用原生前端、静态导出和章节路由。

既有参考材料归入 [报告归档](report/README.md)。其中 [研究设计参考报告](report/研究设计参考报告.md) 仅供参考，不用于项目决策。

目录使用遵循 [项目工作规范](../AGENTS.md)。正式研究文档放在本目录，临时检查记录放在 [workspace/](../workspace/)，正式实验产物放在 [artifacts/](../artifacts/)。
