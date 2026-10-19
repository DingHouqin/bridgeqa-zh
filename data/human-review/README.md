# 共享人工审查记录

审查评价直接保存在当前GitHub仓库，A、B各一个JSON文件。用户已确认允许公开这些内容。网页入口仍是[05人工审查](https://dinghouqin.github.io/bridgeqa-zh/#/review)，原始题库不会随评价修改。

## 怎样开始

1. 打开05页面，先确认能看到GitHub中的进度。
2. 展开“GitHub保存授权”，用你自己的GitHub账号创建Token并连接。你已经需要有本仓库的协作者权限；Token不能替代仓库权限。
3. 正常填写、完成或保留为草稿。出现“已保存到GitHub”才表示其他人能读到；否则输入仍保存在当前浏览器。

协作者使用个人Token（classic），只选择 `public_repo`，设置短期有效。这个权限覆盖该账号有写入权限的公开仓库，不局限于本仓库；请仅自己使用。仓库所有者可使用只针对本仓库、Contents读写权限的细粒度Token。GitHub目前对仓库协作者使用细粒度Token存在限制，详见[GitHub授权说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)。

Token仅保留在当前页面内存，刷新后需重新连接；它只发送给GitHub，不写入仓库、本机草稿或导出文件。不需要提供给其他人或粘贴到聊天中。

## 原来的评价怎样接上

已保存到原数据库的评价迁移时保留题号、署名、评分、评论、完成状态和记录版本。若电脑里还有更完整的旧导出文件，点击“导入审查JSON”：新题会保留为待上传评价；题号已有且内容不同的部分会提示并跳过，保留GitHub原版。连接GitHub后点击“同步 / 重试保存”上传新增记录。

## 保存与恢复

每次输入立即备份到当前浏览器，停顿2.5秒后尝试提交；两个保存按钮立即提交。连接GitHub后每15秒读取进度，未连接时每3分钟读取一次以减少匿名请求额度，也可手动同步。每次保存都有Git提交历史；同题被其他设备更新时由你选择版本，不自动覆盖。

只有本目录内的评价变动不会触发整个网站重新部署，网页直接读取GitHub当前文件。数据按题库轮次分目录，存储实现见[GitHub存储模块](../../explorer/web/github-review-store.js)，页面流程见[审查逻辑](../../explorer/web/review.js)，格式与并发方式依据[GitHub文件接口](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents)。
