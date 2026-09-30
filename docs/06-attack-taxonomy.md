# 攻击与挑战类型

主集的 context attack 必须保持问题、答案与正确证据。primary_type 只表示主要机制；实体相似、局部正确、语言差异等可作 secondary_tags，避免重复计数。

| 类别 | 操作 | 有效性条件 | track |
|---|---|---|---|
| redundant | 增加主题相似但无用的证据 | 长度是 treatment 时明确记录；有等长度对照 | context_attack |
| false_bridge | 用错误实体构成完整候选路径 | 路径不满足题目关系；不新增合法答案 | context_attack |
| misleading_relation | 正确或相似实体间使用近邻关系 | 如修复者/作者、任职/创办；gold 仍唯一 | context_attack |
| ambiguity | 指代、名称、范围或限定词变化 | 区分可解歧义、真多解、需澄清与信息不足 | query_challenge |
| reverse | 根据关系反方向求实体/集合 | 逆关系唯一性或答案集合有定义 | query_challenge |

`partial_correct_chain` 是辅助标签：假路径前缀正确，后续在关系或实体上偏离。不能把“同一事实被无依据地直接否定”混进普通上下文攻击。

Counterfactual conflict、combined 和 evidence_missing 为扩展 track。直接事实冲突需来源可靠性或可接受的冲突/无法判断标签；证据删除通常改变可回答性，单独评测拒答；反事实世界需明确封闭世界指令与一致事实图。

## 三种上下文

gold_only 验证题目基本可答；clean_control 用普通干扰匹配数量、位置、长度；adversarial 替换该干扰。主比较 control/adv，记录没能完全匹配的因素。禁止把“adv 文本更长”全部解释成关系攻击。

2/3/4 跳均记录 target_hop，三跳主集优先 1/2/3 跳平衡。先做单机制再组合。攻击规则在隐藏评测前冻结，效力不得作为最终 gold 唯一筛选准则。
