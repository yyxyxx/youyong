#!/usr/bin/env python3
"""论文查重程序入口。

程序从命令行接收原文、抄袭版论文和答案文件三个绝对路径。
输入既可以是普通文本，也可以是包含论文正文的 HTML 页面。
"""

from __future__ import annotations

import math
import re
import sys
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Counter as CounterType
from typing import Iterator, Sequence

NGRAM_WEIGHTS = ((1, 0.35), (2, 0.45), (3, 0.20))
TEXT_ENCODINGS = ("utf-8-sig", "gb18030")
SKIPPED_HTML_TAGS = {"script", "style", "noscript"}
VOID_HTML_TAGS = {"br", "hr", "img", "input", "link", "meta"}

HTML_PATTERN = re.compile(r"<!doctype\s+html|<html(?:\s|>)", re.IGNORECASE)


class PlagiarismError(Exception):
    """项目自定义异常基类。"""


class ArgumentError(PlagiarismError):
    """命令行参数不符合要求。"""


class InputFileError(PlagiarismError):
    """输入文件无法读取或解码。"""


class OutputFileError(PlagiarismError):
    """答案文件无法写入。"""


class DocumentHTMLParser(HTMLParser):
    """从普通 HTML 或 GitHub blob 页面中提取论文正文。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skipped_depth = 0
        self._code_line_depth = 0
        self._code_line_parts: list[str] = []
        self._code_lines: list[str] = []
        self._visible_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {name.lower(): value or "" for name, value in attrs}
        classes = set(attributes.get("class", "").split())
        element_id = attributes.get("id", "")
        is_github_code_line = tag in {"td", "div"} and (
            "js-file-line" in classes or element_id.startswith("LC")
        )

        if self._skipped_depth:
            self._skipped_depth += 1
            return
        if tag in SKIPPED_HTML_TAGS:
            self._skipped_depth = 1
            return
        if tag in VOID_HTML_TAGS:
            return
        if self._code_line_depth:
            self._code_line_depth += 1
            return
        if is_github_code_line:
            self._code_line_depth = 1
            self._code_line_parts = []

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """忽略自闭合标签，不让它影响正文提取深度。"""

    def handle_endtag(self, tag: str) -> None:
        if self._skipped_depth:
            self._skipped_depth -= 1
            return
        if self._code_line_depth:
            self._code_line_depth -= 1
            if self._code_line_depth == 0:
                line = "".join(self._code_line_parts).strip()
                if line:
                    self._code_lines.append(line)

    def handle_data(self, data: str) -> None:
        if self._skipped_depth:
            return
        if self._code_line_depth:
            self._code_line_parts.append(data)
        else:
            self._visible_parts.append(data)

    def extracted_text(self) -> str:
        """优先返回 GitHub 代码行，否则返回普通页面可见文字。"""
        if self._code_lines:
            return "\n".join(self._code_lines)
        return "".join(self._visible_parts)


def looks_like_html(text: str) -> bool:
    """判断输入内容是否看起来是 HTML 文档。"""
    return bool(HTML_PATTERN.search(text[:4096]))


def extract_document_text(raw_text: str) -> str:
    """从纯文本或 HTML 中提取用于查重的论文正文。"""
    if not looks_like_html(raw_text):
        return raw_text

    parser = DocumentHTMLParser()
    try:
        parser.feed(raw_text)
        parser.close()
    except Exception as error:
        raise InputFileError("HTML 文档解析失败") from error
    return parser.extracted_text()


def normalize_text(text: str) -> str:
    """统一字符宽度和英文大小写，并去除标点、空格等非内容字符。"""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if character.isalnum())


def iter_ngrams(text: str, size: int) -> Iterator[str]:
    """依次生成指定长度的连续字符片段。"""
    if size <= 0:
        raise ValueError("n-gram 长度必须大于 0")
    for index in range(len(text) - size + 1):
        yield text[index : index + size]


def cosine_similarity(
    first_terms: CounterType[str],
    second_terms: CounterType[str],
) -> float:
    """计算两个词频向量的余弦相似度。"""
    if not first_terms or not second_terms:
        return 0.0

    dot_product = sum(count * second_terms.get(term, 0) for term, count in first_terms.items())
    first_norm = math.sqrt(sum(count * count for count in first_terms.values()))
    second_norm = math.sqrt(sum(count * count for count in second_terms.values()))
    if first_norm == 0.0 or second_norm == 0.0:
        return 0.0
    return dot_product / (first_norm * second_norm)


def calculate_similarity(original_text: str, suspect_text: str) -> float:
    """使用字符级 1/2/3-gram 加权余弦计算重复率。

    公式:
        0.35 × 1-gram 余弦 + 0.45 × 2-gram 余弦 + 0.20 × 3-gram 余弦
    """
    original = normalize_text(extract_document_text(original_text))
    suspect = normalize_text(extract_document_text(suspect_text))

    if not original and not suspect:
        return 1.0
    if not original or not suspect:
        return 0.0

    weighted_score = 0.0
    for ngram_size, weight in NGRAM_WEIGHTS:
        original_terms = Counter(iter_ngrams(original, ngram_size))
        suspect_terms = Counter(iter_ngrams(suspect, ngram_size))
        weighted_score += weight * cosine_similarity(original_terms, suspect_terms)

    clamped_score = max(0.0, min(1.0, weighted_score))
    if math.isclose(clamped_score, 1.0, abs_tol=1e-12):
        return 1.0
    return clamped_score


def read_text(path: Path) -> str:
    """读取指定文本文件，优先使用 UTF-8，兼容 GB18030。"""
    if not path.is_file():
        raise InputFileError(f"输入文件不存在或不是普通文件：{path}")

    last_error: UnicodeDecodeError | None = None
    for encoding in TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
        except OSError as error:
            raise InputFileError(f"读取文件失败：{path}") from error

    detail = "；".join(TEXT_ENCODINGS)
    raise InputFileError(f"文件无法按 {detail} 解码：{path}") from last_error


def write_score(path: Path, score: float) -> None:
    """将重复率保留两位小数后写入答案文件。"""
    try:
        path.write_text(f"{score:.2f}\n", encoding="utf-8")
    except OSError as error:
        raise OutputFileError(f"写入答案文件失败：{path}") from error


def parse_arguments(arguments: Sequence[str]) -> tuple[Path, Path, Path]:
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


def main(arguments: Sequence[str] | None = None) -> int:
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
