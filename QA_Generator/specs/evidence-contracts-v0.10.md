# v0.10：恢复单位定义与查询主体约束（实跑未通过整体修复验收）

2026-10-23继续。[v9实跑](../../artifacts/quality-v3/contracts-v9-run-001/README.md)格式错误减少，但评分前沿／身份namespace错误、登记unknown误用和语义漏项仍未通过验收。v10保留全部54公开开发回归及原参考，另版冻结，仍使用用户指定deepseek-flash。不把旧raw重新解析／重算成新模型成功。

## 登记提示与协议边界

[登记v10](../../src/quality_v3/inventory_occurrences_v10.py)保留[v9平坦选择器](../../src/quality_v3/inventory_occurrences_v9.py)的全部输入、schema、原始响应、精确位置材化和验证；底层wire版本仍为v0.9，仅提示修订另标v0.10。恢复unsupported的单位定义：本unit不完成目标支持断言即可，包括背景、别边、前件、未来条件及未确认登记，不要求原文明确否认整条fact。unknown仅用于原文确有指代、角色、范围或冲突歧义，不能代替所有无关单元。

提示增加倒装方向、女工程师先行词、明确生育语义及普通来源类别scope说明。纯姓名与子辈性别仍不证明parent的性别；实际否定、梦境、戏中、条件、未确认或撤销限定仍须入组。独立组审只看原选择组，不补全文或别组。所有旧错误selector仍拒绝，原93个unknown不被程序重标。

## 评分查询与角色门

[评分v10](../../src/quality_v3/scoring_review_v10.py)公开query去除后台start实体ID，仅用已经解析的start_surface表达查询主体。第一hop的frontier和child行由公开查询起点机械绑定；schema约束原hop顺序、已知首hop的context覆盖及空frontier不附带child／边行。后续parent仍由模型根据当前材料提出，程序不预填、补边或默认missing。全部早期格式attempt保留，晚期语义／前沿门继续验证。

[语义门v10](../../src/quality_v3/scoring_semantics_v10.py)是[冻结v7](../../src/quality_v3/scoring_review_v7.py)的可审差异副本，保留旧wire VERSION兼容已有封装，新增明确semantic_policy_version。仅修负面角色词门：实际引用的parent本人称呼（如“政老爹的长女”）不能因为完整别称被去除而连称呼信息一起丢失。例外须原角色锚内真实出现父称呼与子女亲属短语，普通名字含父／母、metadata中出现称呼、child的称呼或纯称呼共现均不因此获得新例外。

这个门只允许继续审查，不直接证明父边。每组的命名child／parent、谓词、角色、scope、模型逐维判词及原引文位置仍须满足原约束。未知与不支持不能升级。机械材化与新policy验证显式位于新源码，不修改或monkeypatch旧冻结模块，不先用旧门拒绝后再替换判词。

## 验收与执行

[运行器](../../src/quality_v3/contracts_v10_experiment.py)和[分析器](../../src/quality_v3/contracts_v10_analysis.py)继承v9的终态／任务身份／split硬校验、失败保留、所有窗口继续、40正组预算、派生请求先保存、缓存恢复与会话计数。四worker、12000最大输出、工具关闭、阶段新session、最多三次应用格式尝试。依赖源码含新角色policy，全部冻结摘要经独立执行门禁签署后才调用模型。

组件作者不自签语义可靠性。新policy先用原1370／164失败raw同输入离线定位问题，再由非作者验源码差异、完整组及负对照；离线重算不改旧交付标签。38评分、16登记的独立真值和等价断言计数边界在输出前绑定。实跑后仍逐原文审查固定主分母37个评分任务（另排旧争议EH-S09，主分母内保留4证据边界）、612登记格和50预存断言类。

统计将最终证明诊断、全文状态／答案、独立合法后跳、完整报告语义、模型正组审、支持出现覆盖、未决与协议失败分开。普通格式完成、原文定位、同组去重或模型自审通过都不代表修复成功。[全54任务实跑](../../artifacts/quality-v3/contracts-v10-run-001/README.md)已完成，14协议失败、技术失败0；登记严格语义合格8/16，仍漏4个真断言类，未通过整体修复验收。所有结论写入[持续验证报告](../validation/2026-10-22_支持覆盖与旧评分继续修复.md)，正式发布保持关闭。
