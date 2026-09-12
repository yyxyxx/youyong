"""main.py 的单元测试。"""

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import main  # noqa: E402  pylint: disable=wrong-import-position


class SimilarityTests(unittest.TestCase):
    """计算模块的相似度测试。"""

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

    def test_assignment_sample_returns_expected_score(self) -> None:
        original = "今天是星期天，天气晴，今天晚上我要去看电影。"
        suspect = "今天是周天，天气晴朗，我晚上要去看电影。"
        self.assertAlmostEqual(
            main.calculate_similarity(original, suspect),
            0.8095238095,
            places=6,
        )

    def test_insertion_is_reflected(self) -> None:
        self.assertAlmostEqual(
            main.calculate_similarity("abc", "abxc"),
            6.0 / 7.0,
            places=6,
        )

    def test_deletion_is_reflected(self) -> None:
        self.assertAlmostEqual(
            main.calculate_similarity("abxc", "abc"),
            6.0 / 7.0,
            places=6,
        )

    def test_substitution_is_reflected(self) -> None:
        self.assertAlmostEqual(
            main.calculate_similarity("abcd", "abed"),
            0.75,
            places=6,
        )

    def test_normalization_ignores_case_width_and_whitespace(self) -> None:
        self.assertEqual(main.calculate_similarity("Ａ ＢＣ", "a\tbc"), 1.0)

    def test_punctuation_is_counted(self) -> None:
        self.assertAlmostEqual(
            main.calculate_similarity("你好。", "你好"),
            4.0 / 5.0,
            places=6,
        )

    def test_lcs_length_known_value(self) -> None:
        self.assertEqual(
            main.longest_common_subsequence_length("ABCBDAB", "BDCABA"),
            4,
        )


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
        self.assertEqual(answer.read_text(encoding="utf-8"), "0.81\n")

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
        self.assertIn("无法按 UTF-8 或 GB18030 解码", error_output.getvalue())

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
