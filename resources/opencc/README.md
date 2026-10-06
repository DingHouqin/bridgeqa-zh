# 固定字形转换资源

本目录保留官方 BYVoid/OpenCC `ver.1.1.9` 的原字节词表、字表和 Apache-2.0 LICENSE。下载地址、字节数和 SHA-256 见 manifest.json。profile.json 固定本项目算法及资源 SHA，程序同时核对硬编码合同与磁盘内容，运行不下载资源、不依赖 OpenCC 包。

`opencc-derived-longest-first-v1` 从左到右匹配当前位置最长词表 key；同长按 key 字典序；取该行首候选。没有词匹配时取单字首候选，再无匹配则保留原字。每个输入只做一遍，不递归转换输出。这是字形派生，不宣称与完整 OpenCC mmseg 算法等价，也不校订人名、词义或原文讹误。

原始引文和 offset 始终留在原始层。简体引文另存 derived-spans.json，并通过 derivation-ledger.json 绑定原哈希、转换 profile 和当前样本；原来的“子元嘆”转成“子元叹”，没有改成“字元叹”。LICENSE 只用于这些上游资源；正文来源许可仍单独登记。
