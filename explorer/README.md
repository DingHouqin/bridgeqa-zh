# BridgeQA Explorer｜题目与证据审查系统

本目录为获准建立的一级目录，遵循 [规格系列](specs/README.md)。原生前端可在本地服务与GitHub Pages运行，当前数据集为 [文学与历史首轮候选集](../data/pilot_literature_history_v0/README.md)。[在线入口](https://dinghouqin.github.io/bridgeqa-zh/) 与 [在线文档](https://dinghouqin.github.io/bridgeqa-zh/#/docs/index) 使用同一套界面。

## 打开与运行

服务运行后，打开 [本地系统](http://127.0.0.1:8765/)。当前会话已启动该地址，关闭服务后可重启。

从项目根目录运行：

~~~powershell
python explorer/server.py --port 8765
~~~

启动命令对应 [服务器](server.py)。Windows也可双击 [启动脚本](start.cmd)。本地服务仅监听本机；端口被占用时选择空闲端口。Ctrl+C停止服务；本地与在线均不需要npm安装或数据库。

页面读取原始数据，重新构建候选集后刷新即可更新；不覆盖或编辑样本。服务只允许登记数据集及指定文档的文本读取。应用显示标准答案和标注，供研究审查使用。

## 页面

1. **选题概览**：文学/历史主题、真实取材页、记录与家族口径、状态、组合配方、实际场景覆盖、知识干扰控制。领域/组合/场景入口可直接筛选题库。
2. **题目与证据**：全部128条主任务，分页、文本搜索、19个可筛选标签维度。每题全部实际场景直接显示，其余全部标签可展开查看并点击筛选；场景支持ANY/ALL，跨维度AND，维度内OR。筛选条件和页码在URL中保留。
3. **逐题剖析**：题面、标准答案、全部标签、完整证明DAG、逐步支持与潜在偏离、当前完整材料、原文引文、改写前锚点、配对变化、实体映射与家族版本。可下载单题原始标注。
4. **03 测试指引**：固定全项目使用说明，[网页入口](http://127.0.0.1:8765/#guide)；独立于数据集选择，新增数据集时在 [页面内容](web/testing-guide.html) 追加章节。
5. **04 研究文档**：按 [文档清单](web/documents.json) 展示原始Markdown，提供侧栏、章内目录、内部跳转与原文入口；采用稳定的 `#/docs/<slug>` 路由。

## 静态导出与发布

从项目根目录运行 `python explorer/export_site.py`，对应 [静态导出器](export_site.py)。默认发布物生成到 [workspace目录](../workspace/) 下的pages子目录；只能覆盖本导出器标记的专用目录，不改原始数据。仅包含 [发布清单](web/documents.json) 内的资料，不复制实验日志或整个仓库。

预览命令为 `python -m http.server 8766 --bind 127.0.0.1 --directory workspace`，然后打开 [子路径静态预览](http://127.0.0.1:8766/pages/)。导出后刷新即可；网站访问不运行Python。

[Pages工作流](../.github/workflows/pages.yml) 在main相关更新或手动dispatch时验证、导出、上传并部署；PR只验证。仓库Pages的Source需选择GitHub Actions。新增数据集登记在 [服务器注册表](server.py)，新增章节登记在 [文档清单](web/documents.json)；清单也定义允许发布/下载的源文件。界面资源使用 [路径函数](web/urls.js)，Markdown使用 [阅读模块](web/documents.js) 和 [固定版本渲染器](web/vendor/README.md)。

验证入口为 [静态导出测试](tests/static_test.py)、[文档浏览器检查](tests/docs_checks.cjs) 与既有 [浏览器回归](tests/ui_checks.cjs)。发布规则和验收见 [静态规格](specs/06_静态发布与文档.md)。在线含gold，是公开审阅界面。

点击图节点查看对应操作；点击资料ID或引文编号跳转定位。多条证明可分别选择。长背景展开后保留全文。桌面双列，窄屏堆叠并可折叠筛选，宽图在自身画布内横向滚动。

## 解释边界

正确证明来自数据的gold，不解释模型真实内部推理。未引用材料不自动等于干扰：当前证明支持、其他合法证明支持、背景和非参考支持分别显示。

原始attack_design、错误答案候选和知识风险是设计预期；逐步分支、阶段错配日期、未入选页数等由结构规则推定，界面明确注明。**没有人工逐跳干扰标注和模型实测。**

缺桥/无材料题没有当前完整正确链；原型图醒目标注为比较参考，不将删除证据补进当前材料。逻辑“不确定”仍可作为判断题合法答案。反事实引文是改写前锚点，不支撑新边；多证明不会被合并拼接。

详见 [数据语义规格](specs/03_数据映射与干扰语义.md)。

## 实现文件与数据登记

| 文件 | 职责 |
| --- | --- |
| [服务器](server.py) | 数据集白名单、文件更新缓存、来源/场景/配对索引校验、API与文本资源服务。 |
| [HTML入口](web/index.html) | 本地应用入口与基础可访问性。 |
| [页面与交互](web/app.js) | 概览、题库、详情、路由、标签、证明选择与定位。 |
| [数据与分析逻辑](web/model.js) | 标签口径、筛选、证明布局、支持分类、保守潜在干扰规则。 |
| [页面样式](web/style.css) | 桌面与窄屏布局、证据/替代/潜在分支视觉区分。 |
| [固定指引内容](web/testing-guide.html) | 手动维护的全项目页面内容，不从当前选中数据集拼装。 |
| [启动脚本](start.cmd) | Windows本地服务启动。 |
| [筛选与语义测试](tests/model.test.mjs) | 纯数据语义与证明布局校验。 |
| [接口测试](tests/api_test.py) | 原数据一致性、UTF-8、索引、只读与路径限制。 |
| [浏览器验收](tests/ui_checks.cjs) | 真实页面交互、状态与视觉截图；使用本机已有Playwright。 |

新增可选数据集时，在服务器REGISTRY登记兼容目录和标题，并按 [接口规格](specs/04_技术与运行.md) 验证，不接受用户传入任意文件系统路径。未来不同schema需增加适配器，不能默认任何数据集都兼容。

## 验证

从项目根目录运行：

~~~powershell
node --test explorer/tests/model.test.mjs
python explorer/tests/api_test.py
~~~

接口测试需要本地服务已启动。浏览器验收需要本机现有Playwright与Chromium；设置NODE_PATH指向已安装的模块目录，再运行浏览器验收脚本。BRIDGEQA_URL可指向所选本地端口。系统运行本身不需要这些测试依赖。

本轮结果、截图、散列和实际验证范围见 [工作检查说明](../workspace/explorer/README.md)。只对浏览器实现和数据映射做验收，不将系统测试当成benchmark模型评测。未查看其他Git分支；未读取参考报告来决定方案。

