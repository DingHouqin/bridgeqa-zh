# 候选领域介绍图

日期：2026-09-30。用途：组员选题讨论。四个领域都是候选，尚未决定正式 benchmark 的领域。

## 图册

| 候选领域 | 图片 | 讨论重点 |
|---|---|---|
| 文博馆藏与人物 | [01-museum.png](01-museum.png) | 作品作者、师承、馆藏角色与同名人物 |
| 非遗项目与传承人 | [02-heritage.png](02-heritage.png) | 传承子项、保护单位、名录版本 |
| 高校科研人物与机构 | [03-academic.png](03-academic.png) | 作者署名、发表时单位、时间限定 |
| 文学作品与历史人物 | [04-literature.png](04-literature.png) | 亲属与师友、字与号、历史地名 |

每张图包含领域介绍、适合构题的原因、可用资料、四节点三跳示例和审核重点。选题时先比较组员熟悉程度与资料可获得性，再为优先候选尝试找齐 3 条真实的三跳证据链。

**图中人物、作品、关系链和年份均是虚构构造示意，不是已核验事实，不能作为正式题目或 gold。** 资料名称表示可用于采集或构造数据的来源，不表示这些来源已经提供三跳问答题库；实际采集需逐项核对使用条件、原文与关系唯一性。OpenAlex、ROR、ORCID 和 Met 元数据也不自动构成中文原生证据。

## 资料入口

- 文博：[故宫数字文物库](https://digicol.dpm.org.cn/)、[Met 开放元数据](https://github.com/metmuseum/openaccess)。
- 非遗：[中国非物质文化遗产网](https://www.ihchina.cn/)，配合地方文旅部门和保护单位中文官网。
- 科研：[OpenAlex](https://help.openalex.org/api/)、[ROR](https://ror.org/registry/)、[ORCID 公共数据](https://info.orcid.org/what-is-orcid/services/annual-data-files/)，配合高校官网与论文原文。
- 文学历史：[CBDB 数据下载](https://cbdb.hsites.harvard.edu/download-cbdb-standalone-database)、[DuIE 项目资料](https://github.com/PaddlePaddle/Research/tree/master/KG/DuIE_Baseline)，配合文学馆和人物纪念馆原文。

## 提示词与生成方式

使用内置 imagegen，精确图像模型版本未返回。最终使用的四组提示词见 [prompts.md](prompts.md)。

提示词的主要调整：

1. 统一横版、标题层级、分区与信息量，便于四个候选并列比较。
2. 给每个领域配置不同的低饱和配色与主题插画。
3. 指定中文原文、四个节点和三条标注关系的箭头，控制排版与文字负担。
4. 使用暖白底、留白和清晰对比；不添加排名、未经验证的分数或统计图。
5. 保留虚构示意说明，避免把构造示例理解为真实史料。

生成图片保持原始输出，未做像素编辑；已检查主要文字、节点数量与关系箭头。插画仅用于介绍领域，不表示真实文物、人物肖像或校舍。

## 文件与状态

- 负责人：待组内认领。
- 输入：已有领域讨论与整理后的介绍文字。
- 输出：4 张 PNG、提示词及本说明。
- 状态：介绍图已生成；真实试题、逐跳证据与人工数据审核尚未完成。
- 使用记录：[AI 使用记录](../../../reports/ai-usage.md)。

