# 数据协议

`sample.schema.json` 为 A 组完整标签结构；`prediction.schema.json` 为 B 组单个预测结构。JSONL 每行一个对象，UTF-8。Schema 管格式；唯一性、捷径、事实正确性及语义翻译对齐需人工审核。轻量 CLI 只检查核心子集。

普通与攻击配对的 `pair_id` 在每个语言条件下唯一，成员各一条；gold_only 不参加成对评分。私有 gold 的 seed/pair/variant/origin/attack 不传给 B 组隐藏输入。提交步骤代表可观察输出，不能据此断言内部推理。

v0.1 仅支持单答案链式 context_attack。歧义答案集合、反向题、证据不足和非链图仍在设计文档中，须先扩展 Schema 和计分。prediction Schema 是评测端标准化输出；文本到 canonical_id 的审核别名映射尚待实现。模型原始输出与转换日志另外保留。
