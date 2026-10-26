---
name: member-evidence-audit
description: Review the original member claims and ordered proof under current-context evidence, separating textual entailment, query direction and the final disposition.
metadata:
  revision: r3-candidate
---

# 当前成员声明：R3候选

只核对contexts内证据与candidate原样提交的状态、顶层答案和证明，不借其他成员、删前文本、库或作品知识。proof卡展开原件，不表示程序认可，也不允许先重排再评价。

事实存储parent→child；查询与路径child→parent。例如“查某人的父亲”从孩子走到父亲，箭头方向合法。逐个i核对entities[i]到entities[i+1]是否由facts[i]支持，并符合query第i步角色、scope、桥接与终点。事实集合正确不能补救提交顺序错误；实体终点正确也不能补救顶层错答案。

再核对自然文本是否蕴含各边。局部语法、明示身份与亲属谓词可以组合：“某人有／生了两个儿子，长子甲、次子乙”在叙述主体及父亲身份明确时支持其与两子的父子边；已明确的女性“生了某子”支持其母边。这些是文本语义，不是引入作品常识，不必重写为固定句式。多条引文共同消解称谓和关系是一个支持组；组内每条无需独立蕴含整条边。不能由只有妻子生子的句子擅自推出丈夫亲生父边，也不能将否定、梦境或别的scope当当前事实。

正确缺证声明应通过：当前没有完整合法链，空答案、空proof是合规形式。缺边写入理由，不作候选major缺陷；若另一完整支持仍在，就应拒绝这个伪缺证声明，定位残余链。范围不清才保留未决，不自行重开既定证据政策。

输出前逐项反读：reason说候选应修订，对照verdict是否仍pass；说某边或答案不成立，对照相应支持项是否仍true；说候选拒答正确，对照是否误列缺边为major。修正自身字段冲突，不改候选。错答案、错状态、错证明、合法直答捷径均须要求修订。无候选缺陷则不为了找错列finding。步骤索引依共同合同为0、1，发布由程序另行控制。
