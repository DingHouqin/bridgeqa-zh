# BridgeQA Explorer｜线上题目与证据审查系统

## 最新页面（2026-10-28）

- [01 全部题目](https://dinghouqin.github.io/bridgeqa-zh/#/overview)：570条输入记录，覆盖七批历史与当前题目，支持全文、批次、类型、结构、条件筛选和完整材料。
- [05 模型实测](https://dinghouqin.github.io/bridgeqa-zh/#/results)：默认最新嵌套／换名Luna24槽，23答复、1技术缺失；[历史Luna／Sol504首答](https://dinghouqin.github.io/bridgeqa-zh/#/results?cohort=v18)单独保留。
- 原05最新开发题库及07评分器导航移除，旧06编号改05。旧题库证据图仍由02访问，评分资料在04文档中保留。

570是输入记录数，含变体及诊断，跨批复用母题，不能当成独立母题数。最新v24为8新增母题＋16部分换名变体。公开投影不含独立金标、关系凭证或私有换名映射。见[全量发布规格](specs/11_全量题库与最新关系题发布.md)及[公开投影](publication_v25/README.md)。以下为历史记录。

**当前状态（2026-10-21）**：[本轮审查已归档](../data/human-review/archive/2026-10-21-pilot-v0.5/README.md)，暂无待审内容；05人工审查入口及服务写入停用，01—04题库、证据、指引与文档保留。旧审查链接显示停用说明，可进入[只读查阅](https://bridgeqa-human-review.spryox2.chatgpt.site/archives/2026-10-21/read-only.html)。下面的审查、预填、保存与GitHub授权说明仅为历史记录。

2026-10-20起，[免GitHub授权审查入口](https://bridgeqa-human-review.spryox2.chatgpt.site/#/review)直接使用共享数据库保存，完整保留题面、图谱与评价功能。B组未完成42题的步骤、整题结论和五项评分预填为草稿建议，文本由用户填写；已完成评价不重置。GitHub Token不再是保存前提。以下旧GitHub保存说明仅作迁移历史；新口径及验收见[规格08](specs/08_临时人工审查.md)及[免授权测试](tests/noauth-review.test.mjs)。

使用 [GitHub Pages网站](https://dinghouqin.github.io/bridgeqa-zh/)。当前pilot-v0.5 [86条候选题](../data/pilot_literature_history_v0/README.md) 的数据、标签和证明均由同一份原始标注生成。

## 使用

- 01选题概览：主题、来源、组合、覆盖和数据规模。
- 02题目与证据：搜索/筛选题目。进入详情后，图中n0为题目起点，点击连接查看这一跳的题面材料、结构化事实与出处，再看可能的偏离。干扰分支同样先显示题面材料，并明确古籍现代译文或现代合成设定。节点本身不再是按钮。
- [03测试指引](https://dinghouqin.github.io/bridgeqa-zh/#/guide)：全项目固定使用说明，内容在 [指引页面](web/testing-guide.html) 维护。
- [04研究文档](https://dinghouqin.github.io/bridgeqa-zh/#/docs/index)：章节、目录和原文跳转，登记见 [文档清单](web/documents.json)。
- [05人工审查](https://dinghouqin.github.io/bridgeqa-zh/#/review)：86题固定分给A/B各43题（原A+C、原B+D），首页可选填姓名简写；复用02筛选、证明图和家族对照，并查看本题全部材料与事实、绿色参考支持、逐步准确性评论及整题评价。所有合法证明的步骤均需审查，材料不足题核对不可作答边界。五个整题评分主题各有1–5分的具体参考。完成本题才计入进度，修改完成评价后恢复草稿；完成、草稿保存结果和缺项原因直接显示在按钮下方。

05的简写、评价和进度直接保存在[GitHub审查目录](../data/human-review/README.md)，内容按用户确认公开。A/B各一个文件，授权后每15秒读取进度；无授权可浏览，每3分钟读取一次。保存需协作者用自己的GitHub Token连接页面，授权仅本页有效。每次输入立即备份，网络或授权失败后仍可恢复；可导入旧JSON，已有不同评价会跳过并提示。原始题目标注不随评价修改。详细规则见[规格08](specs/08_临时人工审查.md)。

缺证题只解释原型，不把原型当作当前可用材料。原文引文用于核验改写，反事实的旧出处不支撑新关系。多份合法证明分别切换，汇合操作保留全部必要依赖。已移除的家族版本灰显。

## 保留什么、删除什么

专用本地HTTP服务器和Windows启动脚本已删除，不维护第二套可视化系统。以下文件仍是线上网站的源代码与发布必需部分：

| 文件 | 作用 |
| --- | --- |
| [HTML入口](web/index.html)、[页面交互](web/app.js)、[样式](web/style.css) | 浏览器使用的原生网页，无React/Vue或复杂构建链。 |
| [数据与图谱逻辑](web/model.js) | 标签筛选、连接图、支持与潜在偏离。 |
| [数据打包](site_data.py) | 只在构建时读取登记数据，核对题号/配对/出处，不启动网络服务。 |
| [静态导出](export_site.py) | 输出网站需要的HTML、静态JSON和允许公开的文档。 |
| [发布工作流](../.github/workflows/pages.yml) | main更新后验证、导出并部署到GitHub Pages。 |

导出命令为 `python explorer/export_site.py`。输出写入 [工作区](../workspace/) 的专用pages目录；只有 [发布清单](web/documents.json) 中的文件会复制，旧数据快照和实验日志不会进入网站。

维护时可以临时预览导出文件，但不需要专用服务器。示例：`python -m http.server 8766 --bind 127.0.0.1 --directory workspace/pages`，只用于本机测试。用户日常入口为线上网站。

## 检查

运行 `node --test explorer/tests/model.test.mjs` 和 `python -m unittest discover -s explorer/tests -p '*_test.py'`，对应 [图谱测试](tests/model.test.mjs)、[数据检查](tests/dataset_test.py)、[静态导出检查](tests/static_test.py)、[原文与变换核验](tests/original_material_test.py)。[浏览器交互检查](tests/ui_checks.cjs) 与 [文档检查](tests/docs_checks.cjs) 可用BRIDGEQA_URL指向临时静态预览或正式线上站点。

先有 [设计规格](specs/README.md)，再实施；本轮连接交互与线上维护边界见 [规格07](specs/07_连线交互与线上系统.md)。逐步干扰是结构规则推定，非人工标注或模型实测；网页检查不能替代benchmark效度验证。

当前题面全部为现代文：古籍译文与合成设定分别标记，溯源古文折叠保存且不提供模型。翻译和各跳关系核对见 [翻译说明](../data/pilot_literature_history_v0/现代文翻译说明.md)。

人工审查另运行 `node --test explorer/tests/review.test.mjs` 与 `node explorer/tests/review_ui_checks.cjs`。后者使用本机已安装Playwright、两个独立浏览器上下文和实际Worker接口的内存SQLite；静态文件从导出目录拦截读取，不修改生产记录。记录见[审查验收](../workspace/explorer/review_checks.json)。
