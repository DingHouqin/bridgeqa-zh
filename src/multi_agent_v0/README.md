# 五角色构题最小原型

2026-10-21后续接入：[经用户批准的外部比对器](external_relations.py)在Origin通过程序校验后，将C01候选／遗漏／冲突及C02冲突提示交给Supervisor；显式GPT修订后的事实也重新比对。初次抽取、Composer、Difficult与盲解不接收库提示，不修改gold。新批次先核对[审批范围与固定文件哈希](../../QA_Generator/resources/relationship-libraries/approval.json)，越界或损坏立即停止。该调用位置已完成程序测试，未用新提示重跑Flash；[接入验收](../../QA_Generator/validation/2026-10-21_关系库辅助核验接入.md)与原交付范围分别记录，阶段性关系求解尚未实现。

本目录实现[系统方案](../../QA_Generator/design/2026-10-20_多智能体构题系统方案.md)的第一个开发交付点，范围仅为一个两步父母关系查询的四成员家族。不是通用自然语言证明器，尚不实现时间、比较、集合或反事实轨的生成。

## 合同与职责

[contracts.py](contracts.py)生成[schemas.json](schemas.json)，覆盖Origin、Composer、Difficult、Supervisor和Blind Solver输出。事实表示直接父母关系，方向为parent→child，保留父／母角色、陈述scope及替代证据组。一个证据组内的引文共同支持事实，不同组是替代支持。来源中的同名王氏不自动合并。

查询从child向parent查找，连续两次，问句限定与事实相同的转述范围。答案、全部合法证明、证明深度与删证状态由[core.py](core.py)在冻结的事实图范围内重算。自然文本中的抽取遗漏、直接结论和语义捷径另由Supervisor及GPT审查，图上证明不能代替文本核验。

五角色的[运行预设](role-presets.json)载入各自skill，按候选与阶段创建全新会话。它们是本项目的预设合同，不冒称Harness内置preset。模型输入投影只保留题号、问题、材料、回答政策和输出结构，屏蔽gold、事实图、来源标签、配方、家族与其他变体。Blind Solver使用独立Harness home，且不挂载任何模型工具。当前已完成[首个开发交付](../../QA_Generator/validation/2026-10-21_五智能体最小贯通交付.md)，含一次明确GPT裁定，不宣称全自动成功。

主干扰与无关对照分别向基础题添加不同的已取得来源选段，不编事实。宁／荣两段按父级译文的字符区间重建，只复用原有说话者框架；删证只移除精确子串并保留删除位置与新旧文本哈希。四个成员共用问题，答案保持条件、基础证明保持条件和删证后无证明条件均检查。缺少来源事实时拒收；格式错误与内容修订分别有有限次数，不无限循环。

## Harness接入

使用官方[Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md)和其配套运行时，独立环境放在[运行工作区](../../workspace/harness-prototype)。[bootstrap.py](bootstrap.py)不调用模型，只验证配置层能够组合，不把dump成功当作模块已激活。[共享覆盖配置](harness.patch.yml)关闭shell、文件、工作目录工具、自动日志上传及标题生成；[安装器](install_plugin.py)先将[插件bundle](plugin/package.json)装入对应profile，运行入口再检查模块导入失败。Windows上使用任务目录内pnpm `10.34.7`。[盲解覆盖配置](solver.patch.yml)禁用该图工具。

插件的[纯图查询逻辑](plugin/logic.mjs)不读文件、不联网、不持有隐含gold，只检查调用者显式提交的有限图。Composer可自行调用；程序侧用[真实工具管线验证器](verify_plugin.py)校验实际查询，并与Python结果核对，不依赖模型自觉调用。插件的审计出口只写程序通过环境指定的本任务记录，不是模型可调用的文件工具。接入依据[官方bundle安装说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/develop/basic/publish.md)。首批角色运行时本地patch的peer导入曾失败；事后正式安装的工具管线已验证，不声称该批模型曾自行调用插件。

凭证只由隐藏输入或现有进程环境读取并传给子进程环境，不进入合同、文件或模型上下文。记录官方SDK的会话事件与请求输入哈希，模型返回的是别名时不虚构不可变权重版本。机器、GPT、用户确认AI裁定、逐字人工审查分别记录。

## 本地复跑

在项目根目录创建任务内环境并安装[固定依赖](requirements.txt)：

```powershell
uv venv workspace/harness-prototype/runtime/.venv
uv pip install --python workspace/harness-prototype/runtime/.venv/Scripts/python.exe -r src/multi_agent_v0/requirements.txt
npm install --prefix workspace/harness-prototype/runtime/pnpm-tool --ignore-scripts --no-audit --no-fund pnpm@10.34.7
```

运行[行为测试](test_core.py)无需凭证；实际[工作流入口](runner.py)读取隐藏凭证或进程中的DEEPSEEK_API_KEY。新实验使用新run-id，避免修改已冻结输入；可复用完全相同的已完成响应，输入、skill、schema和配置哈希不一致时拒绝复用。

```powershell
workspace/harness-prototype/runtime/.venv/Scripts/python.exe -m unittest discover -s src/multi_agent_v0 -p test_core.py -v
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/multi_agent_v0/runner.py --run-id next-pilot-001
```

常规格式重试和内容修订各最多两轮；当重要分歧升级时，先保留失败候选，再通过显式GPT裁定记录接入[裁定准备器](prepare_adjudication.py)所示格式，传给入口的`--adjudication`。本批裁定脚本针对milestone-007固定，不是可任意补事实的通用自动修复器。没有新的来源事实时仍拒收。

[格式适配器](formatting.py)只插入缺失的闭括号，或将已知说明字段保留并归入顶层warnings；不改父母关系、身份、scope或引文字符串。原始输出、标点插入位置与说明迁移全部留存，语义错误仍须修订或升级。其他不合合同的字段不自动丢弃。

已有实跑的独立审计和打包使用[audit_and_package.py](audit_and_package.py)，不调用模型。它目前针对这一包含GPT裁定的最小交付合同；不是通用大批量发布器。固定包与[完整结果](../../artifacts/multi-agent-v0/milestone-007/README.md)分别保留被测输入与gold，不把整个目录交给被测模型。

最终回答协议为`evidence-quotes-v0.2`，明确要求连续逐字引用。[统一协议复跑器](rerun_blind_protocol.py)先保存不可变输入快照，再把全部条件各运行一次；首版结果保留，不按模型成败挑选。另修复了证据区间相交但不互相包含的程序漏判，[重核脚本](recheck_evidence_intervals.py)仅重算保存响应的分数，不调用模型，并保存旧分数。正式分层指标尚未实现，现有区间重叠检查不等于自然语言蕴含证明。

[修复后profile启动检查](smoke_profiles.py)不读取凭证、不创建模型回合，分别验证安装后的builder与solver启动及工具屏蔽。角色输出采用SDK默认采样设置，未显式固定temperature或seed；不同协议的单次结果不能作因果归因或稳定能力估计。
