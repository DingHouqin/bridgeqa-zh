# 从仓库使用多智能体系统

2026-10-26源码公开入口。先阅读[当前机制状态](README.md)与[工作流规范](specs/workflow.md)。网站的[第二版题集](https://dinghouqin.github.io/bridgeqa-zh/#/overview?dataset=multi_agent_hongloumeng_v2)可直接浏览和下载；运行构题系统则使用本页步骤。

## 结构和边界

- [五角色构题器](../src/multi_agent_v0/README.md)：Origin → Composer → Difficult，Supervisor逐阶段审查，Blind Solver独立会话作答。Python编排官方DeepSeek Harness，当前生成范围为受约束的父／母两跳题。
- [FamilyV2及删证审查实验](../src/deletion_review_v2/README.md)：材料变换、证明重算、输入隔离、固定任务和断点恢复。
- [质量模块](../src/quality_v3/README.md)与[新版复核门禁](../src/quality_v3/review_gate_v11.py)：逐步证据评分、支持登记、可信独立复核回执及保守分流。门禁是独立API，未自动接入旧构题运行器；旧运行器完成不等于新版质量通过。
- [角色技能与配置](implementation/README.md)、[架构](architecture.md)和[实际验证索引](validation/README.md)保留已完成、失败与待复核范围。源码上传不代表自然语言语义修复成功或正式benchmark发布。

## 安装与离线验收

在仓库根目录执行，使用Python、Node.js/npm与uv。项目固定版本见[依赖清单](../src/multi_agent_v0/requirements.txt)。命令为Windows PowerShell写法；其他系统调整虚拟环境的可执行文件路径。

```powershell
uv venv workspace/harness-prototype/runtime/.venv
uv pip install --python workspace/harness-prototype/runtime/.venv/Scripts/python.exe -r src/multi_agent_v0/requirements.txt
npm install --prefix workspace/harness-prototype/runtime/pnpm-tool --ignore-scripts --no-audit --no-fund pnpm@10.34.7
workspace/harness-prototype/runtime/.venv/Scripts/python.exe QA_Generator/prepare_runtime.py
workspace/harness-prototype/runtime/.venv/Scripts/python.exe QA_Generator/check_source.py
```

[准备脚本](prepare_runtime.py)只将[带哈希的已审核种子](../data/multi_agent_runtime_v0/README.md)复制到旧运行器要求的工作区，已有不同文件会报错保留。不会调用模型。[源码检查器](check_source.py)运行随源码交付的测试；依赖未发布历史案例、关系库验收记录或运行日志的17项测试显式skip，不计通过。原始历史测试保留不改，直接全量discover仍要求本地旧批次。源码程序通过不等于自然语言质量验收通过。

## 启动五角色生成

旧构题器按已批准范围使用C01/C02静态关系提示，只供Supervisor核验，盲解不可见。[审批与固定哈希](resources/relationship-libraries/approval.json)随源码保留；运行前按原提交从上游取得这两份输入：

```powershell
workspace/harness-prototype/runtime/.venv/Scripts/python.exe QA_Generator/prepare_runtime.py --download-approved-relations
workspace/harness-prototype/runtime/.venv/Scripts/python.exe QA_Generator/check_source.py
workspace/harness-prototype/runtime/.venv/Scripts/python.exe src/multi_agent_v0/runner.py --run-id new-pilot-001
```

最后一条会调用deepseek-flash并产生费用；入口从已有进程环境DEEPSEEK_API_KEY或终端隐藏输入读取凭证。每次新实验使用新run-id；遇到语义分歧会保存候选并停止／转显式复核，不能修改标准答案凑通过。输出位于仓库工作区下的独立批次，路径由[运行器](../src/multi_agent_v0/runner.py)固定。

## 使用第二版题集和新版门禁

评测现成题目直接读取[清洁输入](../data/multi_agent_hongloumeng_v2/inputs.jsonl)，不要将网页、完整标注、原型材料或模型结果放进提示。[题集说明](../data/multi_agent_hongloumeng_v2/README.md)列明57题与10条独立诊断的口径。

[review_gate_v11.py](../src/quality_v3/review_gate_v11.py)的route接口接收合同及原始交付字节，必要时接收经操作者核验的独立回执和可信登记；调用示例和边界由[门禁用例](../src/quality_v3/test_review_gate_v11.py)与[分流规范](specs/review-routing-v0.11.md)固定。未能确定的自然语言结果进入requires_review，不能伪造签署者或将登记结构通过视为语义正确。

历史复核分流的范围由[分流规范](specs/review-routing-v0.11.md)说明；原始实验记录未随本次源码包发布。历史实验脚本中固定的workspace路径用于当时冻结批次，不是一个通用“输入任意文档即可全自动产出正式题集”的命令。完整旧日志不在本次源码包中；可独立运行程序测试、查看第二版数据，并用新run-id开展新实验。
