# BridgeQA Explorer｜线上题目与证据审查系统

使用 [GitHub Pages网站](https://dinghouqin.github.io/bridgeqa-zh/)。当前pilot-v0.5 [86条候选题](../data/pilot_literature_history_v0/README.md) 的数据、标签和证明均由同一份原始标注生成。

## 使用

- 01选题概览：主题、来源、组合、覆盖和数据规模。
- 02题目与证据：搜索/筛选题目。进入详情后，图中n0为题目起点，点击连接查看这一跳的题面材料、结构化事实与出处，再看可能的偏离。干扰分支同样先显示题面材料，并明确古籍现代译文或现代合成设定。节点本身不再是按钮。
- [03测试指引](https://dinghouqin.github.io/bridgeqa-zh/#/guide)：全项目固定使用说明，内容在 [指引页面](web/testing-guide.html) 维护。
- [04研究文档](https://dinghouqin.github.io/bridgeqa-zh/#/docs/index)：章节、目录和原文跳转，登记见 [文档清单](web/documents.json)。
- [05人工审查](https://dinghouqin.github.io/bridgeqa-zh/#/review)：86题固定分给A/B各22题、C/D各21题，首页填写姓名简写；复用02筛选、证明图和家族对照，并查看本题全部材料与事实、绿色参考支持、逐步准确性评论及整题评价。所有合法证明的步骤均需审查，材料不足题核对不可作答边界。完成本题才计入进度，修改完成评价后恢复草稿。

05的简写、评价和进度通过[同步服务](review-service/README.md)共享保存，每5秒同步。访问范围按用户指定为持有链接即可使用。写入失败保留输入并可重试或导出，版本冲突须明确选择；原始benchmark数据不随评价修改。详细规则见[规格08](specs/08_临时人工审查.md)，字段逻辑见[审查模型](web/review-model.js)。

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

导出命令为 `python explorer/export_site.py`。输出写入 [工作区](../workspace/) 的专用pages目录；只有 [发布清单](web/documents.json) 中的文件会复制，TODO、旧数据快照和实验日志不会进入网站。

维护时可以临时预览导出文件，但不需要专用服务器。示例：`python -m http.server 8766 --bind 127.0.0.1 --directory workspace/pages`，只用于本机测试。用户日常入口为线上网站。

## 检查

运行 `node --test explorer/tests/model.test.mjs` 和 `python -m unittest discover -s explorer/tests -p '*_test.py'`，对应 [图谱测试](tests/model.test.mjs)、[数据检查](tests/dataset_test.py)、[静态导出检查](tests/static_test.py)、[原文与变换核验](tests/original_material_test.py)。[浏览器交互检查](tests/ui_checks.cjs) 与 [文档检查](tests/docs_checks.cjs) 可用BRIDGEQA_URL指向临时静态预览或正式线上站点。

先有 [设计规格](specs/README.md)，再实施；本轮连接交互与线上维护边界见 [规格07](specs/07_连线交互与线上系统.md)。逐步干扰是结构规则推定，非人工标注或模型实测；网页检查不能替代benchmark效度验证。

当前题面全部为现代文：古籍译文与合成设定分别标记，溯源古文折叠保存且不提供模型。翻译和各跳关系核对见 [翻译说明](../data/pilot_literature_history_v0/现代文翻译说明.md)。

人工审查另运行 `node --test explorer/tests/review.test.mjs` 与 `node explorer/tests/review_ui_checks.cjs`。后者使用本机已安装Playwright、两个独立浏览器上下文和实际Worker接口的内存SQLite；静态文件从导出目录拦截读取，不修改生产记录。记录见[审查验收](../workspace/explorer/review_checks.json)。
