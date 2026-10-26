---
name: bridgeqa-origin
description: Extract source-grounded parent facts and entity identities from frozen modern Chinese passages for the BridgeQA parent-chain prototype.
---

只提取给定现代文里的父母—子女事实，不使用《红楼梦》常识、关系百科或原著记忆。每个人使用独立稳定ID；同为“王氏”不表示同一人。别名归并须能从给定材料核验。

本次只选4—8条最明确的父母事实，足够为一个基础家族提供候选链即可，不要求穷尽全书或材料里的所有关系。优先选择双方在材料中具名、父母身份直接陈述或先行词清楚的关系。不要仅凭“某人的妻子生了孩子”增添其丈夫的父亲边；不要为未具名人物补出熟知的姓名。ID也使用来源可核验的称呼，不编码未出现的人名。

`parent`指父母，`child`指子女；`parent_role`为father、mother或未定性别的parent。不能把祖父等派生关系写成直接父母边。父亲身份只靠指代得到时标coreference，引用要包含足够的先行词。每个evidence_set内的引文共同支持事实，不同set是替代支持；尽量登记重复表达和别名支持。

quote必须从输入逐字复制，不能用省略号拼接或自行改标点。若两处引文共同支持一条关系，在同一个evidence_set放两个quote对象。fact只能使用schema列出的字段；解释和疑问放顶层warnings，不加note字段。

区分“冷子兴转述”与“叙述者”两个scope；人物转述不能自动当作叙述者事实。警告歧义和缺失，不补桥。只抽明确父母事实，继官、同姓、同谱和同住本身不产生父母关系。

严格按输入提供的origin JSON schema输出，不加Markdown。合同源见[schemas.json](../../schemas.json)，抽取结果还会经程序与Supervisor检查。
