---
name: bridgeqa-difficult
description: Design source-grounded entity-confusion and matched controls for one reviewed BridgeQA parent-chain family.
---

本版只选entity_confusion配方，主干扰是另加已取得的完整现代文来源单元，突出另一人物、同姓或可消歧的相似实体分支。说明诱饵答案及首次错接处；诱饵必须是已有实体且不是正确答案。不得制造新人物关系、假引文或未标记反事实。

另选与目标证明无关、与主干扰不同的来源单元作为无关变化对照。两种添加相对于基础题分别实施，保持基础问句、答案和全部基础证明；合理作答不能因添加而产生冲突或歧义。说明为什么主干扰比无关对照更接近错误分支，但不保证模型会答错。

提出必要支持删除的精确原文片段（这里“原文”指冻结现代文）。只能删除基础材料里的子串；允许多个子串共同切断所有证明。覆盖同事实的重复表达、先行词和替代支持，不留下仍能回答的捷径。不要补缺失标记、改写剩余材料或添回桥接。程序删证后，最终题面仍需语义审查。

字段见[schemas.json](../../schemas.json)。
