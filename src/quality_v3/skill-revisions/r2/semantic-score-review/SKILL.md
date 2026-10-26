---
name: semantic-score-review
description: Grade submitted answers and citations under provided-only evidence policy, accepting justified empty refusals while preserving wrong-final-answer and unsupported-citation errors.
metadata:
  revision: r2-candidate
---

# 提交作答语义评分：R2候选

分别评状态、顶层答案、提交证明与引用。reference_claims是待核参照，当前contexts才是证据；身份绑定或部分剩余事实不能补回已删关系。先判断本题在所给材料中是否有合法完整链，再评价candidate_response，不能把“任务缺证”与“无法评价拒答”混为一谈。

**当前文本无完整链：** provided-only政策下，insufficient_evidence、空answers、空steps本身是正确作答形式，包括contexts为空的情况。无需证明现实关系不存在；没有证据作答，足以评价这个拒答是否遵守合同。将状态与空答案评为correct，证明维度按共同合同肯定其合规空形式，或在区分无证明任务时标not_applicable。拒答理由中另有不准确陈述应单列，不能把该陈述当新增事实恢复缺边。真正身份／scope歧义才使用undetermined。

**当前文本完整可答：** 顶层答案单独计分；即使steps正确到达目标，answers误填中间人物仍是错误。步骤应从问题起点按指定角色走向目标；不要多走或少走一代。只在本成员已确立同一身份时接受别名组合，不按正确名字的子串、参考偏好或作品知识合并人物。

**引用评价提交原件：** 每步所提交的evidence必须实际存在且承载该关系；同一上下文中的明确先行词可帮助理解短引文。引用另一处同义关系句可合法，不必与旧span相交。但空引用、只列姓名或日期、无关景物、不适用梦境、否定关系，不能由评分员另外选一条好引文替换后判支持。即使全文能答对，也可能“答案正确、提交证明不支持”。

保持reason、各维度与verdict一致；只有各项成立才supported，确有错误才incorrect，实际未决才needs_adjudication。保留旧分与新判断，不静默改答案、补引文或冒称人工真值。此为需用新例继续检验的R2候选。
