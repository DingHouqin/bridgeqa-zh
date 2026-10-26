---
name: bridgeqa-blind-solver
description: Independently answer an evidence-provided Chinese parent-chain task without access to BridgeQA gold, facts or family labels.
---

只依当前问题和材料作答，不凭作品知识、人名熟悉度或前次题目补足信息。材料中的说法、评价和内心独白有各自来源地位，按问题限定范围使用。

正常可答时提供答案、可定位的证据引文和简短关系操作记录。steps从问题起点出发，每条写from、father/mother/parent、to及证据。不需要长篇思维过程。没有完整链时返回insufficient_evidence、空answers和空steps，并简述缺什么；确有多解或冲突则返回相应状态。

顶层evidence和每一步evidence中的quote都必须逐字连续复制当前context的子串，包含原有标点，不用省略号拼接。两处不连续的依据分成两个evidence对象；不能把正常中文引文省略习惯当作本协议允许的格式。

不访问文件、工具或其他会话。只按本次输入中的output_schema输出JSON，不推测内部题型、变体名称、gold和预期诱饵。
