#!/usr/bin/env python3
"""论文查重程序入口。

程序从命令行接收原文、抄袭版论文和答案文件三个绝对路径，
使用最长公共子序列计算两篇文本的重复率。
"""

import sys
import unicodedata
from pathlib import Path
from typing import Optional, Sequence, Tuple


class PlagiarismError(Exception):
    """项目自定义异常基类。"""


class ArgumentError(PlagiarismError):
    """命令行参数不符合要求。"""


class InputFileError(PlagiarismError):
    """输入文件无法读取或解码。"""


class OutputFileError(PlagiarismError):
    """答案文件无法写入。"""


def normalize_text(text: str) -> str:
    """统一字符宽度、英文大小写和空白字符。

    参数:
        text: 从文件中读取的原始文本。

    返回:
        用于相似度计算的规范化文本。中文标点等非空白字符会保留。
    """
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if not character.isspace())


def longest_common_subsequence_length(left: str, right: str) -> int:
    """使用滚动数组计算两个字符串的最长公共子序列长度。

    时间复杂度为 O(len(left) * len(right))，
    空间复杂度为 O(min(len(left), len(right)))。
    """
    if len(left) < len(right):
        left, right = right, left

    previous = [0] * (len(right) + 1)
    for left_character in left:
        current = [0] * (len(right) + 1)
        for index, right_character in enumerate(right, start=1):
            if left_character == right_character:
                current[index] = previous[index - 1] + 1
            else:
                current[index] = max(previous[index], current[index - 1])
        previous = current

    return previous[-1]


def calculate_similarity(original_text: str, suspect_text: str) -> float:
    """计算两篇文本的重复率。

    公式:
        2 * 最长公共子序列长度 / (原文长度 + 抄袭版长度)

    该公式是对称的，取值范围为 [0.0, 1.0]。当两篇文本都为空时，
    认为二者完全一致；仅有一篇为空时，认为二者没有重复内容。
    """
    original = normalize_text(original_text)
    suspect = normalize_text(suspect_text)

    if not original and not suspect:
        return 1.0
    if not original or not suspect:
        return 0.0

    common_length = longest_common_subsequence_length(original, suspect)
    score = 2.0 * common_length / (len(original) + len(suspect))
    return max(0.0, min(1.0, score))


def read_text(path: Path) -> str:
    """读取指定文本文件，优先使用 UTF-8，兼容 GB18030。"""
    if not path.is_file():
        raise InputFileError(f"输入文件不存在或不是普通文件：{path}")

    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="gb18030")
        except (OSError, UnicodeDecodeError) as error:
            raise InputFileError(f"文件无法按 UTF-8 或 GB18030 解码：{path}") from error
    except OSError as error:
        raise InputFileError(f"读取文件失败：{path}") from error


def write_score(path: Path, score: float) -> None:
    """将重复率保留两位小数后写入答案文件。"""
    try:
        path.write_text(f"{score:.2f}\n", encoding="utf-8")
    except OSError as error:
        raise OutputFileError(f"写入答案文件失败：{path}") from error


def parse_arguments(arguments: Sequence[str]) -> Tuple[Path, Path, Path]:
    """解析并校验命令行参数。"""
    if len(arguments) != 4:
        usage = "用法：python main.py <原文文件绝对路径> <抄袭版论文绝对路径> <答案文件绝对路径>"
        raise ArgumentError(usage)

    original_path = Path(arguments[1])
    suspect_path = Path(arguments[2])
    answer_path = Path(arguments[3])

    if answer_path in (original_path, suspect_path):
        raise ArgumentError("答案文件不能与输入文件相同")

    return original_path, suspect_path, answer_path


def main(arguments: Optional[Sequence[str]] = None) -> int:
    """程序主入口，返回进程退出码。"""
    command_arguments = sys.argv if arguments is None else arguments

    try:
        original_path, suspect_path, answer_path = parse_arguments(command_arguments)
        original_text = read_text(original_path)
        suspect_text = read_text(suspect_path)
        score = calculate_similarity(original_text, suspect_text)
        write_score(answer_path, score)
    except ArgumentError as error:
        print(f"参数错误：{error}", file=sys.stderr)
        return 2
    except (InputFileError, OutputFileError) as error:
        print(f"文件错误：{error}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
