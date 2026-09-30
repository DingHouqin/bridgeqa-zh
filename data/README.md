# 数据管理

流转：`raw → normalized → candidates → annotation → public/dev 或 private/hidden`。除纯虚构示例外，目前没有真实数据。

| 目录 | 含义 | Git 策略 |
|---|---|---|
| raw | 来源快照和许可清单 | 默认忽略数据 |
| normalized | 稳定实体、句 ID、时间与来源 | 默认忽略数据 |
| candidates | 未审核题及生成记录 | 默认忽略数据 |
| public/dev | 审核后允许公开的开发题 | 暂时忽略；通过许可与泄漏检查后按版本显式添加 |
| private/hidden | 隐藏题、gold、攻击位置 | 默认忽略，独立私有交付 |
| examples | 完全虚构的格式示例 | 可公开 |

分割先于语言/攻击变体展开。相同 seed 及共享组件、近重复内容应归入同一连通簇，防止跨集合泄漏。Git 忽略不提供访问控制；本地权限和协作渠道由数据负责人管理。
