import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.core.config import Settings
from backend.app.core.schemas import ReviewRequest, ReviewRoute
from backend.app.services.llm import LiteLLMClient, _parse_json


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

    def test_solar_call_uses_provider_default_max_tokens(self):
        client = LiteLLMClient(
            Settings(
                llm_mode="litellm",
                upstage_api_key="test-key",
                upstage_api_base_url="https://api.upstage.ai/v1",
            )
        )
        request = ReviewRequest.from_dict(
            {
                "repository": {"owner": "team", "name": "repo"},
                "pull_request": {"number": 1, "head_sha": "head"},
            }
        )
        route = ReviewRoute(
            name="policy_context_review",
            model_tier="solar3-medium",
            use_rag=False,
            focus=["general"],
            reasons=["checks passed"],
            confidence=0.9,
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"summary":{"overall_risk":"low","short_comment":"ok"},'
                        '"findings":[]}'
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
        )

        with patch("litellm.completion", return_value=response) as completion:
            client.generate_review(request, route, [], [{"role": "user", "content": "review"}])

        kwargs = completion.call_args.kwargs
        self.assertNotIn("max_tokens", kwargs)
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})


if __name__ == "__main__":
    unittest.main()
