# 调研工作记录（临时）

日期：2026-10-07。正式产物从 [系列报告入口](../../docs/benchmark-survey/README.md) 进入，工作边界见 [AGENTS.md](../../AGENTS.md)。此处保存可重新生成的检查记录，不作为正式数据集或实测结果。

## 检索与核验路径

本轮先检索经典多跳构建与对抗研究，再分组查长上下文、歧义、条件、方向、规则和知识更新。优先核对会议论文全文、作者版本、官方仓库和数据页；逐条资料入口与读取程度记录于 [资料目录](../../docs/benchmark-survey/00_范围与资料目录.md)。

- 基础题型：从 [HotpotQA](https://hotpotqa.github.io/)、[2Wiki](https://aclanthology.org/2020.coling-main.580/)、[MuSiQue](https://aclanthology.org/2022.tacl-1.31/) 的方法段追踪实体与证据连接。
- 对抗路径：核对 [ADDDOC](https://aclanthology.org/P19-1262/)、[Plausible Distractors](https://aclanthology.org/2024.emnlp-main.147/)、[CofCA](https://arxiv.org/html/2402.11924v5)、[CRiT-QA](https://aclanthology.org/2026.lrec-1.410/) 的扰动锚点、实体传播和答案变化规则。
- 长背景：阅读 [BABILong](https://github.com/booydar/babilong)、[LV-Eval](https://github.com/infinigence/LVEval) 和 [RULER 官方配置](https://raw.githubusercontent.com/NVIDIA/RULER/main/scripts/synthetic.yaml)，避免混用长度单位和套件任务数量。
- 歧义与方向：核对 [AmbigQA](https://aclanthology.org/2020.emnlp-main.466/)、[ProofWriter](https://aclanthology.org/2021.findings-acl.317/) 和 [Reversal Curse](https://arxiv.org/html/2309.12288v4)，区分题意多解、信息不足和未获许可的逆推。
- 新版与方法补核：确认 [MINTQA ACL 2026 页面](https://aclanthology.org/2026.acl-long.18/)，补读 [Bamboogle 构题段](https://aclanthology.org/2023.findings-emnlp.378.pdf)。访问失败与版本限制已经写入正式资料目录。

不保留整段工具返回和大篇幅原文抓取；正式报告用归纳、链接与原创示例说明机制。本轮未下载数据集、未运行模型、未查看其他分支。

## 首轮检查记录（补充核心协议前）

交付前核对本地 Markdown 链接目标、资料编号和场景编号的唯一性、九篇报告是否齐全，以及 UTF-8 文本是否出现替换字符。

- 九篇编号报告齐全，目录含 41 个唯一资料编号，汇总含 32 个唯一场景编号。
- 检查范围为工作规范、正式调研文档和本工作记录，共 13 个 Markdown 文件；未读取其他根目录参考材料。
- 已批准的六个一级目录均存在；本地引用均指向存在的文件或目录。
- 未发现 UTF-8 替换字符或脱离 Markdown 链接的裸网页地址。
- 首次检查将规范中的链接语法占位示例识别为路径；已改成文字说明，并重新核对。外部网址已随研究访问关键资料，但没有对全部重复链接逐一执行在线存活检查。

## 核心设计回收补充

用户明确授权读取 [多跳A组 AI构造分析](thread://01a113c1-16a5-77e0-b5dc-75136a5a14ff?hostId=local)，本次使用对话内容恢复设计并核对 [DAComp 方法全文](https://arxiv.org/html/2512.04324v1) 与 [官方 DE 评测说明](https://github.com/ByteDance-Seed/DAComp/blob/main/dacomp-de/evaluation_suite/README.md)。正式补充见 [多步骤评判与核心创新点回收](../../docs/benchmark-survey/09_多步骤评判与核心创新点回收.md)。未访问其他分支文件，未发送跨对话消息，未复跑历史反例。

资料目录扩为 42 项，编号报告扩为十篇；32 个场景单元保留，另增加横跨场景的协议诊断构造。旧检查数字仅表示首轮版本。

补充后检查通过：14 个 Markdown 文件，86 个本地链接、246 个网页链接、8 个对话链接；未发现失效本地目标、裸地址或 UTF-8 替换字符。42 个资料编号和 32 个场景编号均唯一，核心协议主题均已覆盖。对话链接依据本轮实际读取确认；网页链接总数包括重复引用，不代表访问了 246 个独立网页。
