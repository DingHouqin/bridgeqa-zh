# 现有多智能体详细架构

版本：v0.4开发验证；日期：2026-10-22。FamilyV2共同5成员与适用的3类可选成员保持，质量修订增加[单成员审查与技能迭代](specs/skills-iteration-v0.4.md)；实际运行状态见[验证索引](validation/README.md)，家族规则见[删证与审查规范](specs/deletion-review-v0.2.md)。五角色仍由 Python 编排官方 Harness 的独立根会话，模型别名为 deepseek-flash，不能把角色名称视为独立模型。

## 新增质量层与迭代回路

```mermaid
flowchart TB
    MEMBER[某成员的实际材料与候选声明] --> PROJECTION[程序单成员投影\n不传其他成员及删前文本]
    PROJECTION --> REVIEW[Supervisor独立审查\n必要性技能＋成员证据技能]
    MEMBER --> SUBMIT[该成员的原始作答\n状态／最终答案／步骤与引用]
    SUBMIT --> SCORE[内部语义评分\n评分技能；不替候选补写证明]
    SOURCE[冻结现代文与待核边] --> WINDOWS[程序逐边字面检索窗口\n保留否定与范围；只作待核线索]
    WINDOWS --> INVENTORY[支持登记技能\n共同支持组／重复表达／完整路径]
    REVIEW --> GATES[程序合同与有序证明门禁\n原始模型判断与程序处置分存]
    SCORE --> GATES
    INVENTORY --> AUDIT[独立GPT核验\n未决争议交人工]
    GATES --> AUDIT
    AUDIT --> FAILURES[归纳误放／误拦／未决／协议失败\n区分程序、技能与取材问题]
    FAILURES --> REVISION[有限修订下一轮技能\n保留上轮版本与结果]
    REVISION --> LOCK[加入独立新例与旧例回归\n冻结技能／输入／参考／合同]
    LOCK --> TRIAL[generic与skills相同条件对照\n当前阶段至少三轮]
    TRIAL --> AUDIT
```

上图是正在验证的质量层，非已证明可靠的自动放行系统。运行器只提供一个成员，家族变换不变量另由程序比较。评分角色可看待核参考声明，Blind Solver仍看不到标准答案。技能、检索窗口和结构门禁不能互相代替；前轮新例被用于修订后改称回归。实现入口见[质量模块](../src/quality_v3/README.md)。

## v0.2批次的数据与审核流程

```mermaid
flowchart TB
    SOURCE[120回原著快照及字符定位] --> MODERN[Flash现代化与核验
保留原译文、显式GPT修订与选段范围]
    MODERN --> ORIGIN[Origin抽取初稿
GPT定点纠正scope、指代与不支持边]
    ORIGIN --> DESIGN[程序固定合法两步查询与变换蓝图
Composer提议问法／Difficult分析现有干扰]
    DESIGN --> FAMILY[程序构建FamilyV2
5共同成员＋适用可选成员
逐字删除、名称位置、图重算]
    FAMILY --> REFERENCE[正确／损坏来源快照＋合成正反例
参考裁定与候选声明分开]
    REFERENCE --> PREAUDIT[独立GPT预审
来源、现代化、捷径、删证、参考标签]
    PREAUDIT --> LOCK[按实际哈希冻结案例、参考与提示]
    LOCK --> REVIEWS[Supervisor三条件
A独立核对／B加生成说明／C加批准库提示
每条件3个新会话]
    LOCK --> BLIND[Blind Solver
每成员1个新会话＋另列无材料诊断]
    REVIEWS --> ANALYSIS[程序统计与实际请求隔离核验
失败单列、来源／合成分开]
    BLIND --> ANALYSIS
    ANALYSIS --> POST[独立GPT后审
输入隔离、分母、语义定位与结论]
    POST --> DELIVERY[开发验证交付
正式发布关闭]
    PREAUDIT -.未解决参考争议.-> HUMAN[人工争议审阅包
本批无固定随机抽审]
    POST -.未解决争议.-> HUMAN
    LIB[C01候选比对／C02冲突提示
批准快照及哈希校验] --> REVIEWS
```

本批并非端到端自主生成：程序／根GPT固定来源蓝图并记录修订，Composer与Difficult输出是受约束提案，不能据角色调用次数夸大自治程度。图求解只覆盖登记事实，自然文本的支持消失由独立预审核验。Supervisor与Blind Solver均关闭模型工具；库提示仅进入C条件，生成说明仅进入B/C，隐藏参考不进入任何实验输入。程序打包和独立审核不新增Flash角色。

## v0.1原型流程（保留作实现沿革）

下图描述先前单家族原型和插件验收路径，不代表本批逐阶段实际调用顺序，也不沿用其中旧的固定人工抽审要求。旧记录与人工状态保持原样；本批以[当前执行规范](specs/workflow.md)为准。

图中实线表示数据流与主要执行步骤，虚线表示调度、工具依赖、异常升级或回流。Supervisor 节点表示同一逻辑角色的不同独立审查回合；不是新增角色。所有常规角色共用 DeepSeek Flash，不共享构建上下文。材料现代化是前置准备，打包是程序步骤。

```mermaid
flowchart TB
    subgraph PREP["① 来源与材料准备"]
        SOURCE["《红楼梦》120回原著快照<br/>来源记录、TXT／EPUB 与校验和"]
        MODERN["选段现代化与独立核验<br/>保留叙事、说话者、关系与限定"]
        MATERIAL["冻结现代文材料池<br/>来源映射、组成字符区间及文本哈希"]
        SOURCE --> MODERN --> MATERIAL
    end

    subgraph ENGINE["② Python 编排与 Harness 运行底座"]
        CONTROL["外部 Python 编排器<br/>载入角色 Skill、JSON Schema 及配置<br/>按候选／阶段／变体创建独立根会话<br/>保存输入版本、响应、事件与请求账本"]
        HARNESS["官方 SDK ＋ Runtime 0.2.1rc2<br/>模型别名 deepseek-flash<br/>builder／solver 独立运行配置<br/>关闭 Shell、文件工具及自动日志上传"]
        CONTROL --- HARNESS
    end

    subgraph BUILD["③ 五角色构题主流程"]
        ORIGIN[["Origin｜抽取来源事实<br/>实体、父母关系、父／母角色及陈述范围<br/>直接表达／指代、支持组与替代支持"]]
        FC["程序｜事实合同与来源定位检查<br/>校验身份、引文、关系方向及连通性<br/>枚举合法的两步查询"]
        S1[["Supervisor｜事实审查<br/>核对身份、方向、scope、支持充分性<br/>排查遗漏与错误替代支持"]]
        COMPOSER[["Composer｜基础题设计<br/>选择两次 child→parent 查询<br/>问题、答案状态、证明与材料清单<br/>记录直接答案与单跳捷径风险"]]
        BC["程序｜独立求解与证明检查<br/>枚举已抽取图中的全部合法证明<br/>核对答案唯一、操作顺序与两步依赖"]
        S2[["Supervisor｜基础题审查<br/>问题与查询一致<br/>复核最终文本的直接结论及替代链"]]
        DIFFICULT[["Difficult｜困难设计<br/>从许可配方选择适用机制<br/>当前：贾珍／贾政实体混淆<br/>输出变换方案与预期错误路径"]]
        FAMILY["程序｜执行变换并构建家族<br/>基础题：宁府片段<br/>主干扰：增加荣府世系<br/>无关对照：增加住处商议<br/>必要支持删除：移除第一跳支持句"]
        VC["程序｜逐条件重算与不变量检查<br/>增加材料后答案及基础证明保持<br/>删证切断全部已登记证明<br/>保存修改位置与新旧哈希"]
        S3[["Supervisor｜家族审查<br/>核对实际材料、干扰适用性与删证范围<br/>排查意外支持、歧义及语义捷径"]]
        ORIGIN --> FC --> S1
        S1 -->|通过| COMPOSER
        COMPOSER --> BC --> S2
        S2 -->|通过| DIFFICULT
        DIFFICULT --> FAMILY --> VC --> S3
    end

    MATERIAL --> ORIGIN
    MATERIAL --> DIFFICULT
    CONTROL -.->|调度所有角色及程序步骤| ORIGIN

    subgraph TOOLS["④ 业务校验与 Harness 插件"]
        CORE["Python 业务核心<br/>证据定位、有限图查询、证明枚举<br/>变体实现、投影检查与分项评分"]
        PLUGIN["bridgeqa_check_parent_path<br/>只接收显式事实与查询<br/>不读取隐含 gold、不读来源文件、不联网"]
        GATE["实际工具管线验收<br/>与 Python 结果逐字段核对<br/>新启动检查插件导入失败"]
        EXTERNAL["外部静态关系比对｜程序辅助<br/>C01：相容、遗漏与冲突线索<br/>C02：仅冲突提示；已知库错排除<br/>批准范围、固定提交及SHA-256检查<br/>不改事实或gold，不验证时间与scope"]
        CORE --- GATE --- PLUGIN
    end
    FC -.-> CORE
    FC -.-> EXTERNAL
    EXTERNAL -.->|只提供来源核验线索| S1
    BC -.-> CORE
    VC -.-> CORE

    subgraph BLIND["⑤ 独立盲解与结果检查"]
        INPUT["程序｜输入白名单投影<br/>仅题号、问题、材料、回答政策与输出结构<br/>屏蔽 gold、事实图、证明、条件标签及其他变体"]
        SOLVER[["Blind Solver｜每个变体独立会话<br/>独立 Harness home；所有模型工具关闭<br/>输出可答状态、答案、逐字引文与简短步骤"]]
        DIAG["单列无材料诊断<br/>不混入四成员主任务统计"]
        SCORE["程序｜分项核对<br/>答案／状态、外显路径、引文区间<br/>审计实际收到的输入及材料哈希"]
        S4[["Supervisor｜最终审查<br/>区分题目缺陷与被测模型错误<br/>核对证明及盲解反例<br/>模型答对也可保留有效题目"]]
        INPUT --> SOLVER --> SCORE --> S4
        INPUT --> DIAG --> SCORE
    end
    S3 -->|通过| INPUT

    subgraph EXCEPTION["⑥ 限次修订、GPT 复核与人工入口"]
        ISSUE{"检查未通过／重要分歧"}
        REPAIR["限次修订<br/>格式重试与内容修订各最多两轮<br/>保存原始输出及修改记录"]
        REJECT["拒收并记录原因<br/>来源缺必要事实直接淘汰<br/>不以合成事实补桥救题"]
        GPT["显式 GPT 裁定记录<br/>当前由本对话 GPT 核对来源及争议<br/>保存裁定、父版本与定点修订"]
        RECHECK["重跑受影响的程序检查<br/>独立 Flash Supervisor 复核<br/>回到缺陷对应阶段"]
        HUMAN["人工抽审与争议队列<br/>重要分歧必审<br/>与机器／GPT 状态分开登记"]
        ISSUE -->|可修复且未超限| REPAIR
        ISSUE -->|来源不足／不可修复| REJECT
        ISSUE -.->|重要分歧或需升级| GPT
        REPAIR --> RECHECK
        GPT --> RECHECK
        GPT -.-> HUMAN
    end
    FC -.->|失败| ISSUE
    BC -.->|失败| ISSUE
    VC -.->|失败| ISSUE
    S1 -.->|不通过| ISSUE
    S2 -.->|不通过| ISSUE
    S3 -.->|不通过| ISSUE
    S4 -.->|题目存在缺陷| ISSUE
    RECHECK -.->|按缺陷回流| BUILD

    subgraph OUTPUT["⑦ 程序打包与分级交付"]
        PACK["程序审计与打包<br/>复核来源重建、信息隔离和运行记录<br/>模型错误作为结果保留"]
        MODEL["被测输入包<br/>现代文材料、问题与回答协议"]
        GOLD["内部审计包｜与被测输入分开<br/>gold、事实图、证明、标签、来源哈希<br/>盲解结果、审查、GPT 裁定及人工队列<br/>请求账本、实现清单与验证报告"]
        STATE["分别登记开发交付／人工审查／正式发布状态<br/>当前：1 家族 × 4 条件＋1 个无材料诊断<br/>开发交付完成；人工审阅未完成；未正式发布"]
        PACK --> MODEL
        PACK --> GOLD --> STATE
    end
    S4 -->|题目有效，保留结果| PACK
    PACK -.->|抽审入口与状态记录| HUMAN
    HUMAN -.->|正式发布须满足对应放行规则| STATE
```

## 阅读边界

- 图上证明只覆盖已登记事实与规则；自然文本中的抽取遗漏、直接结论与语义捷径另行审查。
- 插件真实工具执行已验证。首批生成时曾发生插件未激活，不能声称该批模型已自主调用工具；修复后入口用于最终盲解与最终审查，详见[交付记录](validation/2026-10-21_五智能体最小贯通交付.md)。
- 当前三种完整材料条件答对，删证条件错误补出缺失关系。尚未证明实体混淆攻击成功；单例也不能支撑稳定能力结论。
- 时间、比较、集合、反事实生成、大批量调度与完整分层指标仍待实现。架构中的 GPT 为显式复核入口，不代表已部署自动 GPT API；人工队列存在不代表已完成抽审。

## 新增设计边界：外部核验与阶段性关系

用户已批准C01候选比对＋C02冲突提示。[报告与审批状态](resources/relationship-libraries/README.md)记录固定文件及使用范围，比对器在Origin独立抽取之后、Supervisor来源审查时提供线索；GPT修订事实后的来源复核也重算提示。适配器与调用位置已通过程序测试，未用新提示进行Flash实跑，详见[接入验证](validation/2026-10-21_关系库辅助核验接入.md)。不向Blind Solver开放知识库，不修改既有gold。

朋友／仇人及其他可变关系需附时间、事件、条件、方向与陈述者，不能在静态图中跨阶段任意拼接。合同与题型设计见[阶段性关系规范](specs/relationship-validation.md)；当前架构主图仍描述已实现的父母关系原型，不将待实现能力混作实测。
