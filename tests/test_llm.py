import unittest

from backend.app.services.llm import _parse_json


class LLMResponseParsingTest(unittest.TestCase):
    def test_parses_json_object(self):
        self.assertEqual(_parse_json('{"summary": {}, "findings": []}')["findings"], [])

    def test_extracts_json_object_from_markdown_fence(self):
        parsed = _parse_json('```json\n{"summary": {}, "findings": []}\n```')

        self.assertEqual(parsed["summary"], {})

    def test_rejects_empty_content(self):
        with self.assertRaisesRegex(RuntimeError, "did not contain JSON content"):
            _parse_json("")

    def test_rejects_non_object_json(self):
        with self.assertRaisesRegex(RuntimeError, "must be an object"):
            _parse_json("[]")


if __name__ == "__main__":
    unittest.main()
