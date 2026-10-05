# 评测协议草案

在看到最终隐藏模型结果前锁定输入、输出、抽样、主指标、比较项和失败处理规则。所有建议指标须区分已实现与计划。

2026-09-30 补充建议：参见 [完整设计草案 §5–8](17-benchmark-spec-proposal.md)，对 DAComp 的独立部件、依赖失败和严格成功思路做中文多跳 QA 适配。Strict SR、Path-CFS 与 Oracle-CS 均为待实现指标；现有评分器不因新增文档而支持这些功能。

## 主指标

- 规范答案精确匹配及来源适配的 Answer EM/F1；别名只在审核的等价集合内接受。
- control 与 adversarial 的百分点差 `Drop = score_control - score_adv`。
- `ASR = control_correct_and_adv_wrong / control_correct`。分母为零则不适用，不设成 0。
- 支持句集合 Precision/Recall/F1；提交路径与 gold/审核后的备选路径一致性。

歧义多解用答案集合或澄清/拒答指标；反向题按新任务 gold 评分；证据不足和反事实世界单列。答案碰巧正确与证据一致成功分别报告，不使用 pair-consistency（两边都错也一致）作为主鲁棒性分数。

## 系统条件

1. gold_only：检查 reader 能否完成基本链。
2. supplied_candidates：正确证据加匹配的普通/目标干扰，测选择和组合。
3. fixed_corpus_retrieval：固定语料检索后回答，报 doc/sentence Recall@k 和端到端结果。

候选给定不叫开放检索；“直接给 gold 证据”不代表端到端模型成功。缺预测计错误，重复/未知 ID 拒绝；格式错误单列且不得从分母悄悄删除。结构化输出要求和主答题要求有差异时，分别运行并披露。

## 聚合与统计

主宏平均先在同一 seed 的同类条件内平均，再按 seed 平均；各攻击和各跳数单列。ASR 也需注明一题多变体的权重。置信区间按 seed 簇重采样，保留全部相关变体，建议配对 bootstrap；少量四跳样本作描述性压力测试，不强称普遍规律。

每次比较匹配 origin、domain、hop、target_hop、语言和预算，或清楚报告组成差异。原生/翻译、二三四跳、两领域、不同检索条件不只给一个总分。多个探索性切片标为探索性，必要时控制多重比较。

## 冻结与重现

记录 dataset hash、split manifest、模型 ID/revision/许可/总参数、prompt version、rng seed、解码、token budget、retrieval index hash、硬件和运行时间。相同版本结果用于报告和演示；缓存展示注明缓存与生成时间。

当前参考工具只实现规范答案匹配、支持句 F1、提交路径诊断和简单 seed 宏平均；没有文本 F1、完整检索指标、bootstrap 或正式因果检验。
