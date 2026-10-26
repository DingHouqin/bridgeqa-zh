---
name: two-hop-necessity
description: Check whether a supplied parent-chain task needs both relation operations, separating genuine target shortcuts from intermediate-edge statements and unresolved scope.
metadata:
  revision: r2-candidate
---

# 两步必要性：R2候选

先固定问句的起点S、桥接者M、目标T和两步角色，按当前材料允许的scope审查。判定对象是“S经过指定两步得到T”这个目标结论，不是任意一句是否已写出某个亲属关系。

**先查真正的省步读法。** 若材料直接把T称为S的目标祖辈，即使另有正确两步链，也存在捷径。检查别名、称号和指示性介绍；“这位就是你爷爷”可在对话对象S与被指人物T均由当前上下文确定时直接给出目标。身份消解是理解同一人的过程，不另算一条父母关系操作。找到后引用实际指称／关系句，核对肯否、对话对象、父系／母系、现实／梦境和触发条件。

**再排除假捷径。** “M的父亲／母亲是T”只提供第二跳；若仍须用第一跳确定S的父亲是谁，它没有直接说明S的目标祖辈。答案名字已出现、整段宽引文、同一句或同段包含两条必要关系，也不自动构成省步。不得把父亲的母亲误读成父亲的妻子，或把外祖父当作父系祖父。

没有合法捷径时，分别确认S→M及M→T受到当前材料支持，再判断组合是否必要。缺一跳而候选正确声明证据不足，two_hop应为not_applicable；这不是一个有缺陷的可答题。引用失配后仍须查重复表达和其他完整路径，不能据旧标注消失认定缺证。

输出necessary／shortcut／not_applicable／undetermined并与实际状态保持一致。shortcut必须有当前材料位置；仅否定关系、无效梦境或无法确定指代时不得硬判捷径。真正身份／scope争议才保留undetermined。必要性说明、支持布尔值、findings和最终裁定不能互相冲突。此为针对上一轮误判的候选技能，仍需新例检验，不保证穷尽自然语言捷径。
