---
name: two-hop-necessity
description: Judge two-operation necessity from the supplied query and text, distinguishing direct target answers from legitimate composition and local identity resolution.
metadata:
  revision: r3-candidate
---

# 两步必要性：R3候选

固定query的起点S、两步角色及各步scope，按文本分别找出桥接者M与目标T。若有scope_by_step，逐步使用相应范围；不要另要求两步处于同一句或同一范围。

先尝试正常组合：文本支持S→M与M→T，就可据指定操作推出目标。材料无需再直接写出“S的目标祖辈是T”；要求这句才承认两跳，会拒绝多跳任务本身。关系可由叙述、对话、身份先行词与亲属谓词共同表达，不限“X的父亲是Y”句式。身份消解用于确定同一人，不另算父母查找操作。

再找能省掉操作的目标读法：材料直接把T称为S所问的祖辈，或上下文明确的指示介绍直接给出这层关系，则即使另有合法两跳链也存在shortcut。核对别名、指示对象、肯否、父系／母系及现实／梦境条件，并引用使目标关系成立的位置。

“M的父母是T”只表达第二跳；若仍须第一跳确定M，它不是直接回答S的目标。名字出现、同段两关系或一条宽引文都不自动省步。不同祖辈角色不可混用。

文本完整支持且无合法省步读法，判necessary。确实缺一跳且候选正确声明缺证，判not_applicable；旧引文消失后仍须查剩余支持。只有实际身份、范围或解释未决才undetermined。shortcut须定位，最终裁定须与必要性、支持项和findings一致。本技能仍是待检验的修订，不保证穷尽捷径。
