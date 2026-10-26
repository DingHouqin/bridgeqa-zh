---
name: semantic-score-review
description: Score original answer status, final entity and submitted citation support under the fixed provided-only policy, without replacing evidence or deferring a determinate refusal.
metadata:
  revision: r3-candidate
---

# 提交作答评分：R3候选

本任务的provided-only政策已经确定：只用当前contexts，不用作品常识补证，也不另请人工决定是否允许常识。reference_claims和身份绑定是待核声明；当前文本决定可答性。分别评价状态、顶层答案、提交步骤和引用。

若没有合法完整链，insufficient_evidence加空answers、空steps是正确拒答；contexts为空同理。输出status_correct=correct、answer_correct=correct、proof_support=not_applicable，verdict=supported。不因现实关系未知、材料缺边或没有证明文本而延期。只有实际身份／scope解释分歧才undetermined；若候选理由另有错误，单独评价这项错误，不凭理由补回缺边。

若可答，按query从child逐步查parent；这与事实字段parent→child的存储方向相反而不矛盾。亲属叙述可经局部身份消解后正常组合，不要求固定句式或再次明说最终祖辈关系。每步依指定角色／scope，最终answers单独核对；正确steps不能救错顶层答案。别名组合必须在本成员明确指向同一实体，不能用子串或作品知识合并。

评分对象是候选提交的evidence。含关系谓词的短引文可由当前上下文消解明确先行词；仅姓名的引文则没有关系谓词，不能从quote外另添加关系事实来救它。另一处合法同义关系引用无需与旧span相交，但空引文、仅姓名／日期或景物不承载关系，不能由评分员在全文找到好句再替换后通过。全文可答与提交证明受支持是不同判断。

verdict依据分项结果：确认任一实质错误才incorrect；全部成立才supported；实际未决才needs_adjudication。最后从reason反读各字段：承认缺边且拒答正确，不能同时把status／answer写incorrect；承认靠作品记忆补边或候选引用不支持，就不能把证明写supported。修正的是自己的评分字段，不能修改候选。每项错误须指向提交原件，避免给正确拒收附加错误的方向指责。保留旧分与原始答复，不自动发布。本候选需要继续用回归和新例验证。
