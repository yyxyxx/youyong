# 3124004447 个人项目：论文查重

## 运行方式

```bash
python main.py <原文文件绝对路径> <抄袭版论文绝对路径> <答案文件绝对路径>
```

答案文件输出保留两位小数的浮点型重复率。

## 算法

程序先识别并提取普通文本或 GitHub blob HTML 中的论文正文，再进行 Unicode
规范化和字符过滤，最后使用字符级 1/2/3-gram 频次向量的加权余弦相似度：

```text
0.35 × 1-gram 余弦 + 0.45 × 2-gram 余弦 + 0.20 × 3-gram 余弦
```

该方法的时间复杂度接近线性，不依赖第三方库，能够处理题目样例中的 HTML
文件和约一万字符的论文正文。

## 样例结果

| 文件 | 输出重复率 |
|---|---:|
| `orig_0.8_add.txt` | 0.88 |
| `orig_0.8_del.txt` | 0.88 |
| `orig_0.8_dis_1.txt` | 0.97 |
| `orig_0.8_dis_10.txt` | 0.90 |
| `orig_0.8_dis_15.txt` | 0.76 |

本机执行每个样例约 0.16～0.18 秒。

## 项目文档

- `docs/DESIGN.md`：模块设计与算法流程
- `docs/PERFORMANCE.md`：性能分析和优化结果
- `docs/TEST_REPORT.md`：单元测试与覆盖率
- `docs/EXCEPTIONS.md`：异常处理设计
- `PSP.md`：PSP 预估和实际耗时

## 代码质量

代码使用 `ruff` 检查并格式化，检查结果为 0 个警告。

```bash
ruff check .
ruff format --check .
```

## 单元测试

```bash
python -m unittest discover -s tests -v
```

项目共包含 29 个单元测试，主程序分支覆盖率为 99%。