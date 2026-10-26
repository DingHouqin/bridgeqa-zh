---
name: member-evidence-audit
description: Review one BridgeQA member's exact candidate claims against only its delivered evidence, without borrowing another variant's proof or silently repairing the claim.
---

# 逐成员证据审查

每个调用只审一个成员。当前 contexts 是唯一证据域；候选事实、答案和证明均是待核声明。其他版本、删除前的句子、生成者解释、外部库和作品记忆不补充本成员证据。若输入意外包含其他版本，指出边界问题，不用它救回当前候选。

先照录候选的实际 status、answer 和有序 proof，在心中修正后再评为通过会漏掉原缺陷。完整材料下被错误标为缺证、或合法答案配错误证明，都需要修订；不能因为“本来可以改对”而 pass。

对每个证明步骤核对：from 是否承接查询起点或上一步 to；父／母方向、角色和 scope 是否正确；facts 的顺序是否支持 entities 的相应有序边；末端是否与顶层答案一致。另有合法证明不使当前提交的错误证明变正确。可以承认材料支持答案，同时判提交的证明无效。

核对每条实质关系在当前材料中的支持。指代可以使用本成员同段的先行词，不能从另一成员带入。相同角色名可能指不同人物；wife 生子也不自动提供 husband 是亲生父亲的事实。

对缺证声明，搜索同一必要事实的其他表达及另一条完整链。重复表达只保留同一事实，独立证明则保留不同完整路径，不能混淆。当前引文定位失败只说明标注有问题，不等于语义支持不存在。

输出时逐项区分 candidate_status_supported、answer_supported、proof_supported 和两步必要性。确认任一重大缺陷就列入 findings，给当前 contexts 中可定位的依据及被审声明位置；不能文字指出错误却令相应布尔项为 true 或判 pass。不确定则 needs_adjudication，不能靠多数或自信改成通过。引用只能逐字取自当前成员；程序将拒绝跨成员、空引文或定位失败的证据。
