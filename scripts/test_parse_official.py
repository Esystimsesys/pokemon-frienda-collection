"""OCRが欠落しても公開済みの特殊情報を失わず、新しい読取値は反映する。"""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import parse_official as parser


class PreserveSpecialTest(unittest.TestCase):
    def build(self, special):
        original = json.loads(parser.OUT.read_text())[0]
        original.update(tagPartner="ピカチュウ", legend="でんせつ")
        page = copy.deepcopy(original)
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            paths = {}
            for name in ("SETS", "LEGACY", "OCR", "OCR_HEADER", "ARCADE", "OCR_MOVES",
                         "OCR_EXTRA", "MANUAL", "OCR_SPECIAL", "OUT"):
                paths[name] = root / f"{name}.json"
                paths[name].write_text(json.dumps({} if name == "MANUAL" else []))
                stack.enter_context(patch.object(parser, name, paths[name]))
            paths["SETS"].write_text('[{"key":"test","subdir":"test","order":0}]')
            paths["OUT"].write_text(json.dumps([original]))
            paths["OCR_SPECIAL"].write_text(json.dumps(
                [] if special is None else [{"id": original["id"], **special}]))
            stack.enter_context(patch.object(parser, "ROOT", root / "scripts"))
            stack.enter_context(patch.object(parser, "parse_page", return_value=[page]))
            with contextlib.redirect_stdout(io.StringIO()):
                parser.main()
            return json.loads(paths["OUT"].read_text())[0]

    def test_missing_record_preserves_known_fields(self):
        result = self.build(None)
        self.assertEqual(result["tagPartner"], "ピカチュウ")
        self.assertEqual(result["legend"], "でんせつ")

    def test_null_readings_preserve_known_fields(self):
        result = self.build({"tagPartner": None, "legend": None})
        self.assertEqual(result["tagPartner"], "ピカチュウ")
        self.assertEqual(result["legend"], "でんせつ")

    def test_new_readings_replace_previous_values(self):
        result = self.build({"tagPartner": "イーブイ", "legend": "まぼろし"})
        self.assertEqual(result["tagPartner"], "イーブイ")
        self.assertEqual(result["legend"], "まぼろし")
