# 性能分析与改进记录

## 一、测试环境

- Python：3.12.14
- 测试数据：课程提供的 `orig.txt` 和 5 个 `orig_0.8_*` 样例
- 原文规范化后约 9,534 个字符
- 最长样例正文约 11,297 个字符
- 性能工具：`cProfile`、`time.perf_counter`、`tracemalloc`

## 二、首版方案与问题

首版采用最长公共子序列，时间复杂度为 `O(m × n)`。

原文约 9,534 个字符，添加版本约 11,297 个字符，单次比较量超过
1 亿次。纯 Python 双重循环无法稳定满足 5 秒限制，因此首版算法不适合
课程提供的实际测试规模。

## 三、性能改进

最终方案改为字符级 1/2/3-gram 加权余弦相似度：

```text
0.35 × 1-gram 余弦 + 0.45 × 2-gram 余弦 + 0.20 × 3-gram 余弦
```

- 只需线性扫描文本并统计 n-gram 次数。
- 使用标准库 `Counter` 统计频次。
- 不依赖第三方库或分词词典。
- HTML 先提取正文，避免脚本、样式和导航内容参与计算。

## 四、真实样例运行时间

每个样例单独启动一次 `main.py`，包含读取、HTML 解析、规范化和相似度计算：

| 样例 | 输出 | 单个样例耗时 |
|---|---:|---:|
| `orig_0.8_add.txt` | 0.88 | 约 0.16 秒 |
| `orig_0.8_del.txt` | 0.88 | 约 0.17 秒 |
| `orig_0.8_dis_1.txt` | 0.97 | 约 0.17 秒 |
| `orig_0.8_dis_10.txt` | 0.90 | 约 0.18 秒 |
| `orig_0.8_dis_15.txt` | 0.76 | 约 0.17 秒 |

全部结果均远低于 5 秒限制。对字符数约 9,700 的 `orig_0.8_dis_15.txt` 使用 `tracemalloc` 测得峰值内存约 2.32 MB，远低于 2048 MB 限制。

## 五、cProfile 结果

对 `orig.txt` 和 `orig_0.8_add.txt` 执行 cProfile：

```text
182568 function calls in 0.109 seconds

main.calculate_similarity       0.069 秒
collections.Counter 统计       0.029 秒
main.cosine_similarity         0.020 秒
main.normalize_text            0.020 秒
main.iter_ngrams               0.014 秒
```

主要耗时集中在 n-gram 统计和余弦向量点积。由于算法已经接近线性，
当前规模下不需要进一步复杂优化。

## 六、复杂度

- 时间复杂度：`O(n)`
- 额外空间：`O(n)`，用于保存 n-gram 计数
- 500 到 10,000 字符级别均可以在 5 秒内完成。