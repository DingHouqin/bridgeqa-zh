# 多智能体构题机制

自2026-10-21起，本目录作为 BridgeQA-ZH 正式构题机制的维护入口。机制采用 Origin、Composer、Difficult、Supervisor、Blind Solver 五个角色，由 Python 编排 DeepSeek Harness 隔离会话，程序承担校验、变换与打包。重要分歧交 GPT 显式复核，并登记人工争议队列。

**纳入正式机制不等于完成正式测试集发布。** 旧版已验收一个四成员开发家族，含一次 GPT 定点裁定。当前新增 FamilyV2 与“删证有效性＋审查可靠性”验证流程：10个来源家族、57成员和44个审查案例已冻结，396次审查与67次盲解全部完成，独立GPT前后审核记录已形成；12家族目标缺2个。审查误放与评分误伤仍明显，正式发布和扩大自动放行保持关闭。来源事实和蓝图含根GPT代理显式修订，本批不能据此声称端到端自主生成。详见[实际交付报告](validation/2026-10-22_删证与审查首批验证.md)、[本批规范](specs/deletion-review-v0.2.md)与[验证状态](validation/README.md)。

## 阅读入口

2026-10-27最新：[Luna／Sol逐题表现说明](../model-testing/luna_sol_v18_publication.md)、[评分器详细指南](../evaluation/SCORING_GUIDE.md)及[公开分层统计](../explorer/publication_v18/summary.json)。新增[在线252项任务](https://dinghouqin.github.io/bridgeqa-zh/#/latest)、[504份原答与裁决](https://dinghouqin.github.io/bridgeqa-zh/#/results)和[过程评分实现说明](https://dinghouqin.github.io/bridgeqa-zh/#/scoring)。本轮为主智能体调度、脚本构造与独立审查的合成开发扩展，不代表五角色已端到端自治覆盖全部新领域。此次只公开题面、模型表现与评分实现，独立标准答案与证明包留在本地。

2026-10-27新增[双模型实测与三／四跳障碍扩充](validation/2026-10-27_双模型实测与三四跳障碍扩充.md)：旧108主题本轮DeepSeek81/108、Luna79/108；新增204个当前QA，含120可答主题、24缺证主题、48独立节点、12状态控制。可答主题最终39/120、51/120；经独立挑战和Root验收的困难视图66题，三跳31、四跳35，覆盖6领域24蓝图。三跳单独覆盖有限16轴。20项公共规则／名称修订已另版前审和双模型复跑；当前汇总为184原输入＋20修订输入，协议差异明确记录。[数据](../data/obstacle_hops_v14/README.md)和[新实验用法](../src/obstacle_v14/README.md)保留四轴评分与复核分流，不能把答对或结构通过当完整证明。

2026-10-26新增[多领域多结构开发交付](validation/2026-10-26_多领域多结构扩充与独立节点实测.md)：6领域18家族、108主题及36独立节点均完成deepseek-flash实测与独立前后审。主题最终81/108、证明完整79/108；节点32/36、31/36，未决0。保留主代理介入、退回及误拦纠正，属于合成开发集，不改变旧版状态或证明强模型困难。[数据与用法](../data/multidomain_synthetic_v13/README.md)。

2026-10-23用户将本轮验收明确为“确定结论不能有错，允许人工／强智能体复核”。新增[分流规范](specs/review-routing-v0.11.md)与[实际验证记录](validation/2026-10-23_零错误优先与复核分流.md)：非空自然语言结果默认独立复核，原始模型状态、复核状态和已确认核心分别记录，不能用转复核冒充语义修复；旧冻结运行器和失败记录保留。

质量修订已按[技能多轮协议](specs/skills-iteration-v0.4.md)完成三轮开发验证，未将技能视为定型。[三轮报告](validation/2026-10-22_质量修复与skills三轮迭代.md)保留1434项调用中的收益与退化；[质量实现](../src/quality_v3/README.md)增加单成员证据边界、有序证明门禁和语义评分。旧22条误拦修复后仍出现其他误伤和漏检，四技能继续作为候选，自动放行与正式发布仍关闭。原始评分和历史交付保持原样。

| 资料 | 用途 |
| --- | --- |
| [详细架构图](architecture.md) | 五角色、运行底座、信息边界、检查与异常回流。 |
| [执行与质量规范](specs/workflow.md) | 正式机制的职责、合同、变体、修订及放行规则。 |
| [删证与审查首批验证](specs/deletion-review-v0.2.md) | FamilyV2、A/B/C实验、独立GPT前后审核及本批交付边界。 |
| [质量修复与技能试验](specs/quality-skills-v0.3.md)、[多轮迭代协议](specs/skills-iteration-v0.4.md) | 两步必要性、成员边界、评分误伤的修复分工与逐轮验证，保留退化和失败。 |
| [外部关系库](resources/relationship-libraries/README.md) | 已批准C01候选比对＋C02冲突提示，含优缺点、固定版本与接入验证。 |
| [外部核验与阶段性关系](specs/relationship-validation.md) | 来源优先、外部比对边界，朋友／仇人等关系的时间、事件与视角建模；实现待扩展。 |
| [材料现代化规范](specs/2026-10-21_红楼梦选段现代化规范.md) | 来源冻结、现代化、对照核验及材料准备边界。 |
| [实现与运行索引](implementation/README.md) | 源码、skills、插件、配置和复跑入口。 |
| [验证与交付索引](validation/README.md) | 已完成检查、实际实验记录、局限及后续验收缺口。 |
| [需求与设计记录](design/2026-10-20_多智能体构题系统方案.md) | 用户选择、总体设计和尚待实现的范围；不作为全部已实现能力的清单。 |

## 文件结构与归属

```text
QA_Generator/
├── README.md                  机制入口、状态与维护约定
├── architecture.md            当前详细架构图
├── specs/
│   ├── workflow.md            执行与质量规范
│   ├── relationship-validation.md  外部核验与阶段性关系规范
│   └── 2026-10-21_红楼梦选段现代化规范.md
├── implementation/
│   └── README.md              实现、配置、skills 与工具索引
├── validation/
│   ├── README.md              验证索引、验收范围与局限
│   └── 2026-10-21_五智能体最小贯通交付.md
├── design/
│   └── 2026-10-20_多智能体构题系统方案.md
└── resources/
    └── relationship-libraries/  候选报告、资料入口与审批状态
```

上树条目的可跳转入口见前表。运行实现继续由[源码目录](../src/multi_agent_v0/README.md)维护，原始来源位于[来源资料](../data/source-candidates/hongloumeng_archive_org/20210205_20210205_1123/README.md)，冻结实验位于[开发家族包](../artifacts/multi-agent-v0/milestone-007/README.md)，过程日志与依赖位于[Harness 工作区](../workspace/harness-prototype/README.md)。本目录集中维护机制及资料入口，不复制同一份源码、凭证、依赖或实验包。

## 维护约定

1. 本目录的[执行规范](specs/workflow.md)维护当前机制约束；[架构图](architecture.md)与[实现索引](implementation/README.md)同步更新。日期化设计与交付记录保留当时状态。
2. 扩展操作类型、困难配方、输出合同或工具权限时，同时更新规范、实现和相应验证；没有实跑的能力标为待实现。
3. 来源、问题、证明或协议变化须记录版本并重新检查受影响的下游；冻结实验不原地改写。
4. 机器检查、GPT独立审核、用户确认AI结论、逐项人工裁定分别登记。本轮按用户最新决定采用机器交付→独立GPT实验前／后审核→未解决争议交人工，不进行固定随机抽审；其他批次另定。旧记录的人工状态保持原样，计划实施不能写成已执行。
5. 历史文档在[研究文档目录](../docs/README.md)保留迁移入口，新增链接直接指向本目录。项目权限与研究约束继续遵循[工作规范](../AGENTS.md)。
6. 外部关系库先核验并向用户呈交优缺点，明确确认后才在批准范围内使用。C01/C02已按范围完成静态适配与事实审查调用位置的程序验收，见[接入记录](validation/2026-10-21_关系库辅助核验接入.md)；本批已完成三条件审查实跑，结果见[首批报告](validation/2026-10-22_删证与审查首批验证.md)，不支持扩大自动放行；阶段性关系求解尚未实现。
