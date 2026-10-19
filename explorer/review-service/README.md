# 旧人工审查同步服务（已迁移）

人工审查已经改为[GitHub仓库保存](../../data/human-review/README.md)，[05页面](https://dinghouqin.github.io/bridgeqa-zh/#/review)不再调用本站接口。原数据库保留备份，切换后拒绝新的评价写入并提示刷新原网页，避免旧页面继续保存到旧位置。

以下源文件仅作为旧服务维护记录保留：[Worker](worker.js)、[数据库定义](db/schema.ts)、[发布准备](prepare.mjs)和[构建脚本](build.mjs)。旧服务仍使用原项目和DB绑定，没有删除原始数据。
