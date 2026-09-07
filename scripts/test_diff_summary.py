"""PR本文で、中間データだけの差分や読み取り後退を見落とさない。"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import diff_summary as summary


class DataSummaryTest(unittest.TestCase):
    def test_result_and_metadata_changes_are_separate(self):
        before = [{"id": "a", "ocr_complete": False, "had_existing_stats": False},
                  {"id": "b", "ocr_complete": True, "had_existing_stats": False},
                  {"id": "c", "ocr_complete": True}]
        after = [{"id": "a", "ocr_complete": True, "had_existing_stats": True},
                 {"id": "b", "ocr_complete": True, "had_existing_stats": True},
                 {"id": "c", "ocr_complete": False}]
        text = summary.summarise_records(before, after)
        self.assertIn("読み取り結果等の変更 2件", text)
        self.assertIn("既存ステータスの有無の記録だけ 1件", text)
        self.assertIn("不完全→完了 1件 / 完了→不完全 1件", text)

    def test_added_removed_and_order(self):
        self.assertIn("追加 1件、削除 1件", summary.summarise_records(
            [{"id": "a"}], [{"id": "b"}]))
        self.assertIn("並び順のみ", summary.summarise_records(
            [{"id": "a"}, {"id": "b"}], [{"id": "b"}, {"id": "a"}]))

    def test_git_comparison_includes_committed_intermediate_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)

            git("init")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            raw = root / "scripts/raw/result.json"
            raw.parent.mkdir(parents=True)
            raw.write_text(json.dumps([{"id": "a", "ocr_complete": False}]))
            git("add", ".")
            git("commit", "-m", "before")
            base = git("rev-parse", "HEAD").decode().strip()
            raw.write_text(json.dumps([{"id": "a", "ocr_complete": True}]))
            git("commit", "-am", "after")
            with patch.object(summary, "ROOT", root):
                text = summary.render_data_changes(base, True)
                self.assertIn("picks.json）に変更はありません", text)
                self.assertIn("中間データを更新するため", text)
                self.assertIn("不完全→完了 1件", text)
                self.assertIn("ファイル差分はありません", summary.render_data_changes("HEAD", True))
                raw.unlink()
                self.assertIn("result.json`: 削除", summary.render_data_changes(base, True))


if __name__ == "__main__":
    unittest.main()
