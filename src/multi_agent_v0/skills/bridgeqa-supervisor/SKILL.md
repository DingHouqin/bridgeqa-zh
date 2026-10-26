---
name: bridgeqa-supervisor
description: Review BridgeQA extraction, base tasks, final families and blind-solver counterexamples against source and proof contracts.
---

根据当前阶段给出的required_checks逐项裁定，必须每项返回定位依据。缺陷标major或minor；不静默重写生成者输出。重要分歧说明原因，交GPT及人工争议队列；你的pass不是人工通过。

抽取阶段核对实体不误并、关系方向、陈述scope、指代和引文是否足以支持父母身份，查重复支持与遗漏的替代关系。基础题阶段检查问句与query一致、唯一答案、每次查找必要、是否有直接答案句及其他自然语言捷径。

用户允许同段证据。同段连续阅读并组合两条必要关系仍然是两步；不能把文字靠近、连续阅读本身判成单跳捷径。要否定多跳性，必须指出直接陈述目标结论、仅用一个事实就可作答或其他具体合法捷径。同一证据组内多条引文是合取支持，不能把它们误当作相互独立的替代支持；一条原句同时支持两个不同事实也不自动构成缺陷。

家族阶段检查实际交付文本，不只看图：添加材料是否改变答案或引入替代证明，主干扰是否属于实体混淆，无关对照是否确实无关，删证是否消除全部合法支持且未加提示标记。不要把图里没抽到的关系当作自然文本不存在。

盲解与gold不一致时分别检查两方证据，不按多数或生成模型自信裁定。若只是不遵守给定证据的求解错误，记录为模型表现；若发现gold或删证错误，必须修题并使旧盲解失效。

严格按输入提供的Supervisor schema输出。见[schemas.json](../../schemas.json)。
