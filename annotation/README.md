# 审核协作

按 `docs/05-annotation-guide.md` 先独立审核，再裁决。两位审核者不得用同一生成输出互相确认 gold。CSV 模板只给字段，不预填通过结论；正式标签和真实审核记录放私有目录。

review-template.csv 每行一次审核；adjudication-template.csv 每行一个争议裁决。每跳必要性、单文档捷径、替代路径、攻击是否保持 gold、翻译是否对齐都要给依据。审核耗时与拒绝原因用于成本分析。
