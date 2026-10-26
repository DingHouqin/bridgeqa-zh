---
name: member-evidence-audit
description: Audit exactly the submitted member status, answer and ordered proof, without borrowing another member, repairing proof order, or treating correct insufficiency as a defect.
metadata:
  revision: r2-candidate
---

# 当前成员声明审查：R2候选

contexts是唯一证据域；只审candidate当前实际提交的status、顶层答案和有序proof。其他成员、删除前文本、关系库、作品记忆和构造者背书均不补支持。程序提供的proof卡是待审原件，不是可以重写后再评的草稿。

**可答声明：逐格核对原顺序。** query从child向parent查找；entities[i]→entities[i+1]必须由当前提交的facts[i]支持，不能因事实存储方向为parent→child就误判查询方向。核对起点、每步角色／scope、相邻桥接及终点与顶层答案。若提交事实数组或步骤顺序错误，必须要求修订；在心中重排、换一条合法证明或找到另一个正确答案，都不能使原proof通过。明确的有序合同错误是实质证明缺陷，不能降成minor后pass。

**缺证声明：核对它是否确实缺证。** 当前文本没有合法完整链时，insufficient_evidence加空答案、空proof是正确提交形式。缺失的任务证据是拒答理由，写入reason，不应作为候选major finding。若残余重复表达或另一完整合法路径仍在，则“证据不足”声明错误，定位那条完整支持。不要要求证明现实世界不存在关系。

支持组可由多条引文共同完成身份、先行词和关系；无需组内每条单独蕴含整条边。宽引文只要实际承载所需内容就不因宽而失效。同一成员上下文可消解指代，不能借被删句恢复名字对应，妻子生子也不自动建立丈夫亲生父边。

各布尔项评价当前声明而非任务是否可答。确认候选错误才列findings，引用当前材料位置；不确定用于真实解释分歧。理由承认错答案、错proof或major缺陷时，不得同时把对应项标true或给pass。按调用方共同Schema填写，不自行修复或批准发布。此为待继续验证的R2候选。
