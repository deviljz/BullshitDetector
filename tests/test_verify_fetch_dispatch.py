"""Tests for P2: fetch_url integration into _verify_claim loop."""

import sys
import pathlib
import json
import types
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))


def _make_tc(name: str, arguments: dict, tc_id: str = "tc1"):
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_resp(tool_calls: list, usage_in: int = 10, usage_out: int = 5):
    """Build a fake OpenAI-style response."""
    msg = MagicMock()
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage.prompt_tokens = usage_in
    resp.usage.completion_tokens = usage_out
    return resp


def _submit_tc(fact_layer: str = "✓ 存在", tc_id: str = "submit1"):
    return _make_tc(
        "submit_claim_result",
        {
            "fact_layer": fact_layer,
            "name_layer": "—",
            "number_layer": "—",
            "cause_layer": "—",
            "claim_importance": "重要",
            "effective_sources": 1,
            "note": "test note",
        },
        tc_id=tc_id,
    )


class TestFetchUrlDispatched(unittest.TestCase):
    """fetch_url tool call is dispatched and result fed back to model."""

    def _build_mixin(self):
        from ai.providers.plan_mixin import _PlanExecuteMixin

        class FakeProvider(_PlanExecuteMixin):
            _model = "fake-model"
            _tone = "default"

            def _create_with_retry(self_, *a, **kw):
                raise AssertionError("should be patched")

        return FakeProvider()

    def test_fetch_url_dispatched_and_model_uses_result(self):
        """Round 1 returns fetch_url; Round 2 uses fetched text and submits."""
        provider = self._build_mixin()

        fetch_tc = _make_tc("fetch_url", {"url": "https://example.com", "focus": "test claim"}, tc_id="f1")
        submit = _submit_tc(fact_layer="✓ 存在", tc_id="s1")

        round_idx = [0]

        def fake_create(**kw):
            r = round_idx[0]
            round_idx[0] += 1
            if r == 0:
                return _make_resp([fetch_tc])
            else:
                return _make_resp([submit])

        fetched_content = "重要证据：该事件确实发生于2024年"

        with patch.object(provider, "_create_with_retry", side_effect=lambda *a, **kw: fake_create(**kw)):
            with patch("ai.tools.fetch_url", return_value=fetched_content) as mock_fetch:
                with patch("ai.prompts.get_claim_verify_prompt", return_value="system prompt"):
                    result = provider._verify_claim(
                        {"text": "test claim", "type": "fact", "importance": "重要"},
                        "article background",
                    )

        self.assertEqual(result["fact_layer"], "✓ 存在")
        mock_fetch.assert_called_once_with("https://example.com", "test claim")

    def test_url_cache_shared_across_claims(self):
        """fetch_url result cached at module level: trafilatura fetch called once for same URL."""
        import ai.tools as tools_mod

        # Pre-populate cache so second claim skips network
        url = "https://cached.example.com"
        tools_mod._url_cache[url] = "cached page content about the topic"

        provider = self._build_mixin()
        submit = _submit_tc(fact_layer="✓ 存在", tc_id="s1")
        fetch_tc = _make_tc("fetch_url", {"url": url, "focus": "topic"}, tc_id="f1")

        call_count = [0]

        def fake_create(**kw):
            c = call_count[0]
            call_count[0] += 1
            if c == 0:
                return _make_resp([fetch_tc])
            return _make_resp([submit])

        with patch.object(provider, "_create_with_retry", side_effect=lambda *a, **kw: fake_create(**kw)):
            with patch("trafilatura.fetch_url") as mock_trafilatura:
                with patch("ai.prompts.get_claim_verify_prompt", return_value="system prompt"):
                    result = provider._verify_claim(
                        {"text": "topic claim", "type": "fact", "importance": "重要"},
                        "background",
                    )

        # trafilatura should NOT have been called because cache was pre-populated
        mock_trafilatura.assert_not_called()
        self.assertEqual(result["fact_layer"], "✓ 存在")

        # Cleanup
        tools_mod._url_cache.pop(url, None)

    def test_fetch_budget_exhausted_on_third_call(self):
        """Third fetch_url in same claim gets 'fetch budget exhausted', underlying fetch not called."""
        provider = self._build_mixin()

        fetch_tcs = [
            _make_tc("fetch_url", {"url": f"https://example.com/{i}", "focus": "claim"}, tc_id=f"f{i}")
            for i in range(3)
        ]
        submit = _submit_tc(fact_layer="? 无法核实", tc_id="s1")

        round_idx = [0]
        # Round 0: all 3 fetch calls at once; Round 1: submit
        def fake_create(**kw):
            r = round_idx[0]
            round_idx[0] += 1
            if r == 0:
                return _make_resp(fetch_tcs)
            return _make_resp([submit])

        fetch_call_count = [0]

        def counting_fetch(url, focus=""):
            fetch_call_count[0] += 1
            return f"content of {url}"

        with patch.object(provider, "_create_with_retry", side_effect=lambda *a, **kw: fake_create(**kw)):
            with patch("ai.tools.fetch_url", side_effect=counting_fetch) as mock_fetch:
                with patch("ai.prompts.get_claim_verify_prompt", return_value="system prompt"):
                    result = provider._verify_claim(
                        {"text": "claim", "type": "fact", "importance": "重要"},
                        "background",
                    )

        # Only 2 real fetch calls; 3rd was budget-exhausted
        self.assertEqual(fetch_call_count[0], 2)

        # Find the tool messages that went back: look at messages passed in round 1
        # We verify by checking that mock_fetch was called exactly twice
        calls = mock_fetch.call_args_list
        self.assertEqual(len(calls), 2)


class TestUrlSnippetsAccumulation(unittest.TestCase):
    """url_snippets dict is populated from search results."""

    def test_url_snippets_populated_by_search(self):
        from ai.providers.plan_mixin import _PlanExecuteMixin

        round_idx = [0]
        fake_results = [
            {"title": "Article 1", "snippet": "snippet one", "url": "https://a.com"},
            {"title": "Article 2", "snippet": "snippet two", "url": "https://b.com"},
        ]

        search_tc = _make_tc("web_search", {"query": "test query"}, tc_id="w1")
        submit = _submit_tc(fact_layer="✓ 存在", tc_id="s1")

        def fake_create(*a, **kw):
            r = round_idx[0]
            round_idx[0] += 1
            if r == 0:
                return _make_resp([search_tc])
            return _make_resp([submit])

        class FakeProvider(_PlanExecuteMixin):
            _model = "fake-model"
            _tone = "default"
            _create_with_retry = staticmethod(fake_create)

        provider = FakeProvider()
        url_snippets: dict = {}
        query_cache: dict = {}

        with patch("ai.tools._search_provider") as mock_sp:
            mock_sp.search.return_value = fake_results
            with patch("ai.prompts.get_claim_verify_prompt", return_value="system"):
                provider._verify_claim(
                    {"text": "claim", "type": "fact", "importance": "重要"},
                    "background",
                    query_cache=query_cache,
                    url_snippets=url_snippets,
                )

        self.assertIn("https://a.com", url_snippets)
        self.assertIn("https://b.com", url_snippets)
        self.assertEqual(url_snippets["https://a.com"][0]["snippet"], "snippet one")
        self.assertEqual(url_snippets["https://a.com"][0]["query"], "test query")


if __name__ == "__main__":
    unittest.main()
