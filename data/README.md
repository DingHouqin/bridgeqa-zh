# 数据入口

最新公开入口为[252项任务浏览](https://dinghouqin.github.io/bridgeqa-zh/#/latest)，对应两模型共[504份首次作答与逐题表现](https://dinghouqin.github.io/bridgeqa-zh/#/results)。252项包括现有142主任务、48节点诊断、12状态控制和50条开发扩展，不能统称252道独立主问题。[公开投影说明](../explorer/publication_v18/README.md)、[清洁输入](../explorer/publication_v18/inputs.jsonl)及[题目／资格索引](../explorer/publication_v18/questions.public.json)是本次下载入口；标准答案、参考证明和私有完整标注包本轮未公开，原答及裁决理由保留。[批次与表现说明](../model-testing/luna_sol_v18_publication.md)及[评分说明](../evaluation/SCORING_GUIDE.md)明确分母、资格与未决边界。模型每次只接收一题完整清洁输入，不能含资格索引或已审标签。

新增50条开发扩展已作为[252项公开任务](../explorer/publication_v18/README.md)的阶段子集提供，含16条旧题修订、三组新算子各10题和4条部分信息边界题。题面已独立输入验收并完成双模型首次实测；42题仅局部依赖资格、3题限父题、5题逐跳待复核，全局无捷径认证0。见[公开批次说明](../model-testing/luna_sol_v18_publication.md)与[分层统计](../explorer/publication_v18/summary.json)。本地v16私有参考整包保持原样且未在本轮发布，不改写旧版题目及分数。

新增[三跳／四跳多领域开发题库v14](obstacle_hops_v14/README.md)：6领域24蓝图，144主问题、48独立节点和12状态控制；当前204输入已双模型实跑和独立前后审，66题困难视图附具体错误见证。回答机仅可读取该包blind-inputs.jsonl。当前结果与184原协议／20修订协议边界见[验证报告](../QA_Generator/validation/2026-10-27_双模型实测与三四跳障碍扩充.md)。

当前有 [文学与历史首轮候选集](pilot_literature_history_v0/README.md)：先登记组合，再构题和生成可追溯变体。人工审题从 [题目审阅册](pilot_literature_history_v0/题目审阅册.md) 开始，源文快照见 [来源登记](pilot_literature_history_v0/sources.json)。

所有主任务目前仅作开发与协议审查，不是已验证的独立测试集。模型只能接收说明中指定的清洁输入，不能接收包含答案和映射的完整标注。

数据权限与质量要求见 [项目规范](../AGENTS.md)，场景定义见 [场景总表](../docs/benchmark-survey/07_场景总表与中文构题配方.md)。

[人工审查记录](human-review/README.md)直接保存A/B评价，已获用户同意公开；与原始题目标注分开维护。
