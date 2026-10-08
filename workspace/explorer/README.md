# Explorer 实现与浏览器验收

系统入口为 [运行说明](../../explorer/README.md)，实现前规格为 [规格系列](../../explorer/specs/README.md)，访问入口为 [线上网站](https://dinghouqin.github.io/bridgeqa-zh/)。

当前完成7个数据/筛选/证明逻辑测试、4个数据加载与静态导出测试，以及14组真实浏览器交互验收。浏览器接口未在本会话提供，按可用能力使用本机已有Playwright与Chromium进行本地无界面浏览器检查，并查看截图；没有访问其他浏览器会话或下载测试依赖。

[浏览器检查记录](browser_checks.json) 保存场景通过列表、预期错误路由、脚本异常与视口；[交付检查](delivery_checks.json) 保存本地链接、源数据散列一致性及产物清单。

## 检查范围

- 概览数据口径、作品/史料和10个组合。
- 全量题库、19个标签维度、搜索、零结果、场景ALL、跨维度AND、刷新和返回条件保持。
- 普通三跳、合法逆关系、同名歧义、时间解释、受限溯因、表文聚合和操作干扰提示。
- 多证明选择及合法材料角色变化；长背景全文；无材料与删桥的原型边界。
- 反事实新答案、两条边改写、原型旧关系、引文与匿名映射。
- 宽图连线选择后保持画布位置；390px窄屏无整页横溢、筛选可折叠、连线键盘选择。
- 固定测试指引在未知数据集参数下直接打开，不请求数据集 bundle；文件链接、刷新、章节跳转和窄屏检查。
- 原始数据只读一致、已登记出处索引、UTF-8、未登记数据集拒绝及导出路径边界。

检查中修复快速连续筛选更新丢条件，并保留证明画布水平滚动。截图和本轮审阅不能代替benchmark人工复核或模型测试。逐步潜在干扰仍是保守结构规则推定。

## 视觉记录

- [概览 · 桌面](01-overview-desktop.png)
- [筛选题库 · 桌面](02-catalog-filtered.png)
- [三跳剖析](03-chain-detail.png)
- [表文聚合剖析](04-aggregation-detail.png)
- [概览 · 窄屏](05-overview-mobile.png)
- [单题剖析 · 窄屏](06-detail-mobile.png)

- [测试指引 · 桌面](07-testing-guide-desktop.png)
- [测试指引 · 窄屏](08-testing-guide-mobile.png)

[交付核对脚本](verify_delivery.py) 检查当前文档链接和原始数据散列，更新交付检查记录。

以上是可重新生成的临时检查产物。用户操作的系统直接读取 [当前候选集](../../data/pilot_literature_history_v0/README.md)，不依赖这些截图。

## 静态发布与文档补充检查

新增2项 [导出测试](../../explorer/tests/static_test.py)，覆盖数据/文件一致性、重复导出清理及输出目录边界。使用 [文档浏览器检查](../../explorer/tests/docs_checks.cjs) 逐章等待加载完成，本次报告整理后验证全部32章、50个原文/下载链接、章节刷新、标题锚点、内部跳转、恢复入口及390px布局；记录见 [文档检查](docs_checks.json)。原有14组交互在静态子路径和本地服务均通过，2项接口检查也通过。

- [文档 · 桌面](09-docs-desktop.png)
- [文档 · 窄屏](10-docs-mobile.png)

检查日期为2026-10-07；静态结果与正式线上访问分别验证。站点部署规则见 [静态规格](../../explorer/specs/06_静态发布与文档.md)。

正式 [网站](https://dinghouqin.github.io/bridgeqa-zh/) 已完成14组交互与4组文档验收，线上无意外脚本异常。初次成功部署为 [f78a1c9](https://github.com/DingHouqin/bridgeqa-zh/commit/f78a1c92a6551c0071b2f027b1f4d4737ebbbbe0)，[Actions运行](https://github.com/DingHouqin/bridgeqa-zh/actions/runs/37580550362) 成功；[已验证发布快照](published_build.json) 保存版本和发布源散列。后续仅测试脚本与验收记录的提交不修改网站功能，发布版本继续由 [线上build记录](https://dinghouqin.github.io/bridgeqa-zh/build.json) 核对。


本次日期化归档与计划拆分的本地检查见 [进展报告](../../docs/report/2026-10-07_项目进展报告.md) 和 [工作计划](../../docs/工作计划.md)。历史线上发布的30章/48个链接与本次本地32章/50个链接分别记录；尚未发布本次文档修改。

本次pilot-v0.2去重后：6项逻辑测试、2项接口测试、2项静态导出测试、14组浏览器交互及33章/51个文档文件链接通过。当前本地题库为86条；历史线上版本与验收快照保留原规模，本次未重新上线。保留规则见 [去重说明](../../data/pilot_literature_history_v0/去重说明.md)。

## 当前维护检查（2026-10-07）

已移除独立本地服务器和启动器，只保留生成线上网站所需源码。题目详情按 [新交互规格](../../explorer/specs/07_连线交互与线上系统.md) 展示 n0 起点、可点击连线、原文优先的逐跳分析和缺失家族版本置灰。上述初次部署及去重后的检查是历史记录；当前候选集为86条，已完成7项逻辑、4项Python、14组浏览器及34章/49个文档文件链接检查。正式发布版本以 [线上构建记录](https://dinghouqin.github.io/bridgeqa-zh/build.json) 为准。

## 原文恢复检查（pilot-v0.3）

材料恢复与文体筛选见 [恢复说明](../../data/pilot_literature_history_v0/原文恢复说明.md)。当前检查为8项JavaScript逻辑、10项Python数据/导出/原文核验及8类故意注错校验；浏览器继续覆盖14组交互，并补查古文、白话文、混合过滤及真实史记原文显示。[古籍原文展示截图](11-original-history-detail.png) 单独保留。旧版本检查数字为历史记录。

## 05人工审查与共享保存（2026-10-08）

按[规格08](../../explorer/specs/08_临时人工审查.md)，86题稳定分为A/B各22题、C/D各21题。05在[原网站](https://dinghouqin.github.io/bridgeqa-zh/#/review)内新增；共享数据保存在[Sites同步服务](../../explorer/review-service/README.md)的D1数据库，不在本机统计为团队进度。

本次12项JavaScript逻辑测试、16项Python数据与导出检查、原有14组浏览器回归及12组审查/接口验收通过。审查检查使用实际Worker代码、两个独立浏览器上下文与内存SQLite，不写生产记录；覆盖任务分配、姓名同步、保存刷新、多证明/缺证、评论主题、完成门槛、草稿恢复、故障重试、并发冲突、导出及390px布局。[检查记录](review_checks.json)保留检查清单。旧界面回归输出位于忽略的临时目录，与历史截图分开。

同步服务版本1部署成功，实际数据库存在DB绑定及review_entries表；从原网站Origin执行读取返回200，PUT预检返回204，数据版本匹配。生产记录在发布时为空，人工审查尚未开展；网页验收不代表benchmark已获得人工认可。

- [05首页 · 桌面](12-review-home-desktop.png)
- [05逐题审查 · 桌面](13-review-detail-desktop.png)
- [05首页 · 手机](14-review-home-mobile.png)
- [05逐题审查 · 手机](15-review-detail-mobile.png)
