# 五角色原型的最小启动材料

供[准备脚本](../../QA_Generator/prepare_runtime.py)恢复旧构题器的固定输入位置；不修改历史运行器及冻结实验。

- [P01现代文](P01.modern.json)、[P02现代文](P02.modern.json)：2026-10-21已审核的选段。
- [GPT审核及快照](gpt_review.json)：按原字节保留，属于GPT审核而非独立人工真值。
- [哈希清单](manifest.json)：每份输入的SHA-256。

取材源为[Archive.org《红楼梦》120回通行本](https://archive.org/details/20210205_20210205_1123)，条目标示Public Domain Mark 1.0，源文本另保留维基文库使用条件；现代化及修订归属随材料保留。材料只用于受约束原型；正式质量状态见[机制入口](../../QA_Generator/README.md)。
