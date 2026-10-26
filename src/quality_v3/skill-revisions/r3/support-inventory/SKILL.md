---
name: support-inventory
description: Inventory complete support groups for each requested edge by checking every retrieved occurrence and full text, distinguishing repeated expression from alternative complete paths.
metadata:
  revision: r3-candidate
---

# 逐边支持登记：R3候选

requested_edges是待核声明，focus_windows只是字面位置，不是真值或穷尽保证。按每条请求边分别检查全部窗口和完整contexts，包含前后两次提及同一人物的段落；不能找到第一组后停止。为每个实际出现位置判定：关系支持、仅身份辅助、否定／梦境／异scope或无关；最后在reason简述各边检查范围与未决处，而非声称“已穷尽”却漏后段。

每个support_group共同确定具体两人、父／母角色和scope。代词、排行或称号需先行词时，把必要身份句与关系句共同列入该组；非连续引文可以合取，但不能把各自不完整的引文拆成多个独立组。用“只保留该组仍能确定请求边吗”核验完整性。姓名、出生日期、在场或改名句本身不证明父母关系。

不同位置各自完整表达同一边才是重复支持；同一处重叠宽窄引用不是两处。同段、同篇或同一转述者仍可有两处可分离的关系表达，不要求独立文献：删除另一组的非共享关系句后，本组仍支持该边才算保留支持，必要的共享身份依据应明列。识别局部语法中的关系表达，不限固定句式：叙述主体明确的父亲有／生若干儿子、继而列出姓名，可支持相关父子边；只有妻子生子不自动支持丈夫亲生父边。别名可消解身份，不能补缺失关系。

完整proof_paths按query角色与每步scope组合child→parent；parent允许材料明确的父或母，不能擅自收窄成father。另一个完整路径须有不同的合法实体／关系组合；只替换同一边的引用是重复支持，不是独立路径。所有必要边均须受支持。

先逐边输出支持组或未解决原因，再判断重复和替代链。最后把requested_edges与facts逐条对照：reason声称存在的边、支持组和完整路径必须实际登记；若不支持或未决，就在reason对应说明，不能用概括解释代替漏项。尚未执行可选变体则coverage_status=not_constructed，不能因为完成登记就写constructed。程序负责精确删除与定位，支持提案仍需独立核验，不自动放行。
