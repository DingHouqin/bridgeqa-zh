# 首轮候选集构建器

[构建器](build_pilot.py) 的输入、输出、变换及复现命令统一记在 [数据说明](../../data/pilot_literature_history_v0/README.md)，避免重复维护规格。只依赖 Python 标准库，不读取其他分支、不调用模型。

构建顺序为先读 [组合登记](../../data/pilot_literature_history_v0/combinations.json) 与 [引文快照](../../data/pilot_literature_history_v0/sources.json)，形成家族，按条件变换，重算证明与答案，通过校验后导出。新组合必须先登记和审查，不因代码可以扩增就视为批准冻结。

检查记录见 [本轮验证说明](../../workspace/pilot_literature_history_v0/README.md)。

古籍文字由 [原文渲染器](original_materials.py) 读取 [片段登记](../../data/pilot_literature_history_v0/material_units.json) 后逐字恢复，再按记录做换名与反事实替换；不生成仿古文。原有白话文合成题继续保留，分组规则见 [恢复说明](../../data/pilot_literature_history_v0/原文恢复说明.md)。
