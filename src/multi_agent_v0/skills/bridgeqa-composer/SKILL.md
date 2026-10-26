---
name: bridgeqa-composer
description: Compose one evidence-dependent two-step parent-chain question from reviewed BridgeQA facts, with a checkable query and proof.
---

从已审事实选择一个唯一可答、实际依赖两次查找的问题。query从child依次查parent，steps长度为2；father和mother要求事实明确相应身份，parent不限性别。限定同一scope，冷子兴转述范围的问题在问句中明确“根据冷子兴的说法”。

query、proposed_answer_ids和proof_fact_ids必须原样选自输入的validated_query_options之一。选项由程序枚举已有事实得到，不允许把母亲边解释成父亲边，不允许用夫妻关系补入未抽取的边，也不允许改变问题来掩饰query不成立。证明边按从问题起点出发的查找顺序排列。

问题起点和目标清楚，不直接提示中间人物或答案；基础材料选完整来源单元，不改成关系清单。来源缺事实就报告失败，不靠生成补齐。列出自然文本中可能存在的直接结论、替代证明与常识捷径；两条图边不自动证明文本多跳有效。

可调用`bridgeqa_check_parent_path`自查；无论是否自行调用，程序都会通过Harness插件和Python分别核验查询。该工具只接受显式提交的facts和query，不核验引文语义；不得把工具通过当成来源审查。输出Composer schema，不输出额外解释段落。

字段见[schemas.json](../../schemas.json)，可执行合同见[core.py](../../core.py)。
