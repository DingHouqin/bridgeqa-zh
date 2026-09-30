# 分割与泄漏审查（待实现）

负责人 A1。输入：seed、原始题 ID、共享实体/文档/组件与近重复联系；输出：cluster_id、split、版本化 manifest 和排除记录。先分连通簇再展开变体。仅按 seed_id 分割不足以排除共用来源组件，目前 CLI 只检查同 seed 不跨 split。
