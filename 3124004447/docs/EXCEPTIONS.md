# 异常处理设计说明

## 一、设计目标

程序对可预期的参数、输入文件和输出文件错误进行处理，不让评测程序收到
Python 堆栈或未处理异常。正常输入返回 `0`，参数错误返回 `2`，
文件相关错误返回 `3`。

## 二、异常类型与测试

| 异常 | 触发场景 | 处理方式 | 对应测试 |
|---|---|---|---|
| `ArgumentError` | 参数数量不等于 3 个 | 输出用法并返回 2 | `test_main_rejects_wrong_argument_count` |
| `ArgumentError` | 答案文件等于输入文件 | 拒绝执行并返回 2 | `test_main_rejects_answer_path_equal_to_input` |
| `InputFileError` | 输入文件不存在 | 输出文件错误并返回 3 | `test_main_reports_missing_input` |
| `InputFileError` | 文件不是有效的 UTF-8 或 GB18030 | 输出解码错误并返回 3 | `test_main_reports_undecodable_input` |
| `InputFileError` | 操作系统拒绝读取文件 | 包装底层 `OSError` 并返回 3 | `test_read_text_reports_os_error` |
| `OutputFileError` | 答案路径不可写或是目录 | 包装底层 `OSError` 并返回 3 | `test_main_reports_output_write_error` |

## 三、空文本规则

- 原文和抄袭版都为空：相似度为 `1.00`。
- 只有其中一篇为空：相似度为 `0.00`。

这样可以避免除零错误，同时对两个边界场景给出明确且可测试的结果。