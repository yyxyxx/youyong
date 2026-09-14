"""main.py 的单元测试。"""

import io
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import main  # noqa: E402  pylint: disable=wrong-import-position


class SimilarityTests(unittest.TestCase):
    """文本预处理、HTML 抽取和相似度算法测试。"""

    def test_empty_texts_are_identical(self) -> None:
        self.assertEqual(main.calculate_similarity("", ""), 1.0)

    def test_single_empty_text_has_no_similarity(self) -> None:
        self.assertEqual(main.calculate_similarity("", "内容"), 0.0)
        self.assertEqual(main.calculate_similarity("内容", ""), 0.0)

    def test_identical_text_returns_one(self) -> None:
        text = "软件工程论文查重"
        self.assertEqual(main.calculate_similarity(text, text), 1.0)

    def test_completely_different_text_returns_zero(self) -> None:
        self.assertEqual(main.calculate_similarity("甲乙丙", "XYZ"), 0.0)

    def test_assignment_sample_has_medium_similarity(self) -> None:
        original = "今天是星期天，天气晴，今天晚上我要去看电影。"
        suspect = "今天是周天，天气晴朗，我晚上要去看电影。"
        score = main.calculate_similarity(original, suspect)
        self.assertGreater(score, 0.60)
        self.assertLess(score, 0.80)

    def test_insertion_keeps_partial_similarity(self) -> None:
        score = main.calculate_similarity("abc", "abxc")
        self.assertGreater(score, 0.40)
        self.assertLess(score, 1.0)

    def test_deletion_keeps_partial_similarity(self) -> None:
        score = main.calculate_similarity("abxc", "abc")
        self.assertGreater(score, 0.40)
        self.assertLess(score, 1.0)

    def test_substitution_keeps_partial_similarity(self) -> None:
        score = main.calculate_similarity("abcd", "abed")
        self.assertGreater(score, 0.30)
        self.assertLess(score, 1.0)

    def test_normalization_ignores_case_width_space_and_punctuation(self) -> None:
        self.assertEqual(main.calculate_similarity("Ａ Ｂ，Ｃ。", "a\tbc"), 1.0)

    def test_ngram_generator_returns_expected_slices(self) -> None:
        self.assertEqual(list(main.iter_ngrams("abcd", 2)), ["ab", "bc", "cd"])

    def test_ngram_generator_rejects_invalid_size(self) -> None:
        with self.assertRaises(ValueError):
            list(main.iter_ngrams("abcd", 0))

    def test_cosine_similarity_known_values(self) -> None:
        first = Counter({"a": 1, "b": 2})
        second = Counter({"a": 1, "b": 2})
        self.assertAlmostEqual(main.cosine_similarity(first, second), 1.0)
        self.assertEqual(main.cosine_similarity(first, Counter({"x": 1})), 0.0)

    def test_plain_text_is_not_html(self) -> None:
        self.assertFalse(main.looks_like_html("这是一段普通论文文本。"))

    def test_github_blob_html_prefers_code_lines(self) -> None:
        html = (
            "<!DOCTYPE html><html><body><nav>GitHub 导航</nav>"
            '<table><tr><td id="LC1" class="blob-code js-file-line">第一行</td>'
            '<td id="LC2" class="blob-code js-file-line">第二行</td></tr></table>'
            "<script>无关脚本</script></body></html>"
        )
        self.assertTrue(main.looks_like_html(html))
        self.assertEqual(main.extract_document_text(html), "第一行\n第二行")

    def test_html_parse_error_is_wrapped(self) -> None:
        html = "<!DOCTYPE html><html><body>正文</body></html>"
        with mock.patch.object(
            main.DocumentHTMLParser,
            "feed",
            side_effect=ValueError("解析失败"),
        ):
            with self.assertRaises(main.InputFileError):
                main.extract_document_text(html)

    def test_cosine_similarity_handles_zero_vectors(self) -> None:
        self.assertEqual(main.cosine_similarity(Counter({"a": 0}), Counter({"a": 1})), 0.0)

    def test_html_skips_nested_noscript_and_void_tags(self) -> None:
        html = (
            "<!DOCTYPE html><html><body><noscript><div>隐藏内容</div></noscript>"
            "<p>论文正文</p><br></body></html>"
        )
        extracted = main.extract_document_text(html)
        self.assertIn("论文正文", extracted)
        self.assertNotIn("隐藏内容", extracted)

    def test_github_blob_html_handles_nested_and_empty_lines(self) -> None:
        html = (
            "<!DOCTYPE html><html><body><table><tr>"
            '<td id="LC1" class="blob-code js-file-line"><span>第一行</span></td>'
            '<td id="LC2" class="blob-code js-file-line"></td>'
            '<td id="LC3" class="blob-code js-file-line">第二行<br></td>'
            "</tr></table></body></html>"
        )
        self.assertEqual(main.extract_document_text(html), "第一行\n第二行")

    def test_normal_html_skips_script_and_style(self) -> None:
        html = (
            "<!DOCTYPE html><html><head><style>页面样式</style></head>"
            "<body><h1>论文标题</h1><p>论文正文</p>"
            "<script>页面脚本</script></body></html>"
        )
        extracted = main.extract_document_text(html)
        self.assertIn("论文标题", extracted)
        self.assertIn("论文正文", extracted)
        self.assertNotIn("页面样式", extracted)
        self.assertNotIn("页面脚本", extracted)


class CommandLineTests(unittest.TestCase):
    """命令行入口和文件读写测试。"""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write_text(self, name: str, content: str) -> Path:
        path = self.directory / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_main_writes_score_with_two_decimals(self) -> None:
        original = self._write_text(
            "original.txt",
            "今天是星期天，天气晴，今天晚上我要去看电影。",
        )
        suspect = self._write_text(
            "suspect.txt",
            "今天是周天，天气晴朗，我晚上要去看电影。",
        )
        answer = self.directory / "answer.txt"

        exit_code = main.main(["main.py", str(original), str(suspect), str(answer)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(answer.read_text(encoding="utf-8"), "0.67\n")

    def test_main_extracts_github_html(self) -> None:
        html = (
            "<!DOCTYPE html><html><body>"
            '<td id="LC1" class="blob-code js-file-line">相同论文内容</td>'
            "</body></html>"
        )
        original = self._write_text("original.txt", html)
        suspect = self._write_text("suspect.txt", "相同论文内容")
        answer = self.directory / "answer.txt"

        exit_code = main.main(["main.py", str(original), str(suspect), str(answer)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(answer.read_text(encoding="utf-8"), "1.00\n")

    def test_main_rejects_wrong_argument_count(self) -> None:
        error_output = io.StringIO()
        with redirect_stderr(error_output):
            exit_code = main.main(["main.py", "only-one-path"])

        self.assertEqual(exit_code, 2)
        self.assertIn("用法", error_output.getvalue())

    def test_main_reports_missing_input(self) -> None:
        original = self.directory / "missing.txt"
        suspect = self._write_text("suspect.txt", "内容")
        answer = self.directory / "answer.txt"
        error_output = io.StringIO()

        with redirect_stderr(error_output):
            exit_code = main.main(["main.py", str(original), str(suspect), str(answer)])

        self.assertEqual(exit_code, 3)
        self.assertIn("输入文件不存在", error_output.getvalue())
        self.assertFalse(answer.exists())

    def test_main_rejects_answer_path_equal_to_input(self) -> None:
        original = self._write_text("original.txt", "内容")
        suspect = self._write_text("suspect.txt", "内容")
        error_output = io.StringIO()

        with redirect_stderr(error_output):
            exit_code = main.main(["main.py", str(original), str(suspect), str(original)])

        self.assertEqual(exit_code, 2)
        self.assertIn("不能与输入文件相同", error_output.getvalue())

    def test_main_reads_gb18030_text(self) -> None:
        original = self.directory / "original.txt"
        suspect = self.directory / "suspect.txt"
        original.write_bytes("软件工程".encode("gb18030"))
        suspect.write_bytes("软件工程".encode("gb18030"))
        answer = self.directory / "answer.txt"

        exit_code = main.main(["main.py", str(original), str(suspect), str(answer)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(answer.read_text(encoding="utf-8"), "1.00\n")

    def test_main_reports_undecodable_input(self) -> None:
        original = self.directory / "invalid.txt"
        suspect = self._write_text("suspect.txt", "内容")
        answer = self.directory / "answer.txt"
        original.write_bytes(b"\xff\xff")
        error_output = io.StringIO()

        with redirect_stderr(error_output):
            exit_code = main.main(["main.py", str(original), str(suspect), str(answer)])

        self.assertEqual(exit_code, 3)
        self.assertIn("无法按", error_output.getvalue())

    def test_main_reports_output_write_error(self) -> None:
        original = self._write_text("original.txt", "内容")
        suspect = self._write_text("suspect.txt", "内容")
        answer_directory = self.directory / "answer"
        answer_directory.mkdir()
        error_output = io.StringIO()

        with redirect_stderr(error_output):
            exit_code = main.main(["main.py", str(original), str(suspect), str(answer_directory)])

        self.assertEqual(exit_code, 3)
        self.assertIn("写入答案文件失败", error_output.getvalue())

    def test_read_text_reports_os_error(self) -> None:
        path = self._write_text("content.txt", "内容")

        with mock.patch.object(Path, "read_text", side_effect=OSError("读取失败")):
            with self.assertRaises(main.InputFileError):
                main.read_text(path)

    def test_script_entry_can_run(self) -> None:
        original = self._write_text("original.txt", "相同内容")
        suspect = self._write_text("suspect.txt", "相同内容")
        answer = self.directory / "answer.txt"

        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "main.py"),
                str(original),
                str(suspect),
                str(answer),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(answer.read_text(encoding="utf-8"), "1.00\n")


if __name__ == "__main__":
    unittest.main()
