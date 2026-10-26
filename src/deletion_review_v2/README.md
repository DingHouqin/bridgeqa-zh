# 删证与审查验证 v0.2

本模块执行[首批规范](../../QA_Generator/specs/deletion-review-v0.2.md)，使用官方DeepSeek Harness隔离会话。旧版[五角色原型](../multi_agent_v0/README.md)及冻结结果保留。当前是开发验证，正式发布关闭。

## 模块与数据

| 入口 | 职责 |
| --- | --- |
| [contracts.py](contracts.py)、[family.py](family.py) | FamilyV2合同、逐字删除、名称位置、支持登记、逐步scope及重新求解；程序图不代替文本语义审核。 |
| [prepare_batch.py](prepare_batch.py)、[source_packets.py](source_packets.py) | 来源现代化任务、明确标记合成挑战、版本化来源包及显式GPT修订。 |
| [construction_jobs.py](construction_jobs.py) | 固定蓝图约束下的Composer／Difficult提议，以及旧家族＋4个独立合成调试任务。 |
| [build_locked_batch.py](build_locked_batch.py) | 正确／损坏案例分支、实际批准库提示、隐藏参考草稿、共享来源与证明边清单；不签审核门禁。 |
| [review_cases.py](review_cases.py) | A/B/C允许字段投影、冻结哈希与独立GPT参考门禁。 |
| [experiment.py](experiment.py) | 官方Harness调用、固定次序、有限格式修复、断点复用、审查与隔离盲解、分项计数。 |
| [queue_worker.py](queue_worker.py) | 任务内运行队列及单例锁；凭证由隐藏输入／进程环境传递。 |
| [analyze_batch.py](analyze_batch.py)、[package_delivery.py](package_delivery.py) | 实际输入审计、分项／聚类统计、库提示相关性分层及可恢复冻结交付；不代签GPT审核。 |
| [test_family.py](test_family.py)、[test_experiment.py](test_experiment.py) | 合同、变换、替代支持、投影、失败与恢复逻辑离线测试。 |

过程材料位于[本批工作区](../../workspace/deletion-review-v2/)，Harness实际调用记录位于[本批运行目录](../../workspace/harness-prototype/runs/deletion-review-v2-20261022/)。[冻结批次](../../artifacts/deletion-review-v2/batch-001/)有10来源家族、57成员、44审查案例，396次审查与67次盲解已完成；[实际报告](../../QA_Generator/validation/2026-10-22_删证与审查首批验证.md)分开保留机器评分与独立GPT语义复核。12家族目标缺2；来源损坏分布4／4／2而非4／4／4。来源构建含根GPT代理修订及程序约束，不宣称自主端到端生成。

## 运行与恢复

在项目根目录、已配置[任务内依赖](../multi_agent_v0/README.md)的Python环境运行（本项目环境为任务内venv，系统Python未安装Harness SDK，不要用于模型调用）：

```powershell
python -m unittest discover -s src/deletion_review_v2 -p "test_*.py" -v
python src/deletion_review_v2/build_locked_batch.py
```

构建器输出待审核草稿，不执行网络调用。当前读取来源draft-v4及合成draft-v3，已有不同内容的输出会拒绝覆盖；修改输入后应选新输出目录。签门禁前须独立GPT核对最终内容，不把构建者记录写成独立审核。

独立审核后，实验批次目录须包含冻结案例、冻结参考、清单、独立GPT审核门禁，以及盲解使用的冻结家族。相关合同与命名由[冻结器](review_cases.py)和[实验入口](experiment.py)定义。下列变量由操作者填入该次真实冻结目录和新结果目录，不可指向未审核草稿：

```powershell
python src/deletion_review_v2/experiment.py reviews --batch $batchDirectory --out $reviewOutput --workers 3
python src/deletion_review_v2/experiment.py blind --batch $batchDirectory --out $blindOutput --workers 3
python src/deletion_review_v2/experiment.py summarize --batch $batchDirectory --out $reviewOutput
```

调用优先从运行环境读取凭证，否则隐藏输入；不要把凭证写入命令或配置。队列可使用隐藏启动或前台入口，现有单例锁拒绝重复worker。未关闭的STOP标记使队列不运行；恢复前先核对实际运行状态与待处理任务，不能为重跑成功结果而更改任务标识。

结果缓存绑定输入、提示、合同和配置哈希；重复同任务只复用完全一致的记录，变化需新版本。每次审查及格式修复均创建新根会话。初次＋最多2次格式修复后仍无合格输出记协议失败，技术错误另列，不能伪装成模型拒收。实验锁定后不得按模型表现改题／调提示；参考修订需保留原实验并作为新版本独立统计。

本轮由独立GPT进行实验前参考审核和实验后运行／统计审核，未解决争议才交人工；不执行固定随机人工抽审，不改历史人工状态。实际验收以[验证索引](../../QA_Generator/validation/README.md)为准。
