"""Tests for P1: _build_evidence_pool and _run_phase2_retry."""

import sys
import pathlib
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))


def _make_claim_result(fact_layer: str = "? 无法核实", claim: str = "claim text",
                       claim_type: str = "fact", claim_importance: str = "重要",
                       note: str = "test") -> dict:
    return {
        "fact_layer": fact_layer,
        "name_layer": "—",
        "number_layer": "—",
        "cause_layer": "—",
        "claim_importance": claim_importance,
        "effective_sources": 0,
        "note": note,
        "claim": claim,
        "claim_type": claim_type,
        "sources": [],
    }


def _provider():
    from ai.providers.plan_mixin import _PlanExecuteMixin

    class FakeProvider(_PlanExecuteMixin):
        _model = "fake"
        _tone = "default"

    return FakeProvider()


class TestBuildEvidencePool(unittest.TestCase):

    def test_empty_url_snippets_returns_empty(self):
        p = _provider()
        result = p._build_evidence_pool({})
        self.assertEqual(result, "")

    def test_pool_contains_all_snippets_with_query(self):
        p = _provider()
        url_snippets = {
            "https://a.com": [
                {"query": "q1", "snippet": "snippet one"},
                {"query": "q2", "snippet": "snippet two"},
                {"query": "q3", "snippet": "snippet three"},
            ]
        }
        result = p._build_evidence_pool(url_snippets)
        self.assertIn("snippet one", result)
        self.assertIn("snippet two", result)
        self.assertIn("snippet three", result)
        self.assertIn('来自 query "q1"', result)
        self.assertIn('来自 query "q2"', result)
        self.assertIn('来自 query "q3"', result)
        self.assertIn("https://a.com", result)

    def test_single_url_truncated_at_600_chars(self):
        p = _provider()
        long_snippet = "A" * 200
        url_snippets = {
            "https://a.com": [
                {"query": f"q{i}", "snippet": long_snippet}
                for i in range(5)
            ]
        }
        result = p._build_evidence_pool(url_snippets)
        # Extract only the block for this URL (from "- https://a.com" to end)
        url_block_start = result.index("- https://a.com")
        url_block = result[url_block_start:]
        # Find next URL block (there isn't one, so just use the whole rest)
        # The URL block should not exceed max_per_url=600 chars
        self.assertLessEqual(len(url_block.split("\n\n")[0]), 650)  # some header overhead

    def test_total_pool_capped_at_4000_chars(self):
        p = _provider()
        long_snippet = "B" * 180
        url_snippets = {
            f"https://url{i}.com": [{"query": "q", "snippet": long_snippet}]
            for i in range(30)
        }
        result = p._build_evidence_pool(url_snippets)
        self.assertLessEqual(len(result), 4200)  # small overhead for header text

    def test_high_frequency_urls_appear_first(self):
        """URL with more snippets (higher frequency) should appear before low-freq ones."""
        p = _provider()
        url_snippets = {
            "https://low.com": [{"query": "q", "snippet": "low freq snippet"}],
            "https://high.com": [
                {"query": f"q{i}", "snippet": f"high freq snippet {i}"}
                for i in range(5)
            ],
        }
        result = p._build_evidence_pool(url_snippets)
        high_pos = result.index("https://high.com")
        low_pos = result.index("https://low.com")
        self.assertLess(high_pos, low_pos)

    def test_duplicate_snippets_deduplicated(self):
        """Same snippet text appearing under same URL twice should only appear once."""
        p = _provider()
        url_snippets = {
            "https://a.com": [
                {"query": "q1", "snippet": "identical snippet"},
                {"query": "q2", "snippet": "identical snippet"},
            ]
        }
        result = p._build_evidence_pool(url_snippets)
        # "identical snippet" should appear exactly once in the result
        self.assertEqual(result.count("identical snippet"), 1)

    def test_pool_header_and_footer_present(self):
        p = _provider()
        url_snippets = {"https://a.com": [{"query": "q", "snippet": "some snippet"}]}
        result = p._build_evidence_pool(url_snippets)
        self.assertIn("其他 claim 已搜证据池", result)
        self.assertIn("fetch_url", result)


class TestRunPhase2Retry(unittest.TestCase):

    def test_no_unverified_skips_verify_claim(self):
        """If no '? 无法核实' claims, _verify_claim is never called."""
        p = _provider()
        results = [
            _make_claim_result("✓ 存在"),
            _make_claim_result("✗ 不存在"),
        ]
        url_snippets = {"https://a.com": [{"query": "q", "snippet": "s"}]}

        with patch.object(p, "_verify_claim") as mock_vc:
            out = p._run_phase2_retry(results, "article", url_snippets, {})

        mock_vc.assert_not_called()
        self.assertEqual(out, results)

    def test_no_pool_text_skips_retry(self):
        """Empty url_snippets → pool_text='' → no retry even if unverified claims exist."""
        p = _provider()
        results = [_make_claim_result("? 无法核实")]

        with patch.object(p, "_verify_claim") as mock_vc:
            out = p._run_phase2_retry(results, "article", {}, {})

        mock_vc.assert_not_called()
        self.assertEqual(out, results)

    def test_phase2_triggered_for_unverified(self):
        """_verify_claim is called exactly once for the unverified claim."""
        p = _provider()
        unverified = _make_claim_result("? 无法核实", claim="unverified claim")
        verified = _make_claim_result("✓ 存在", claim="verified claim")
        results = [unverified, verified]
        url_snippets = {"https://a.com": [{"query": "q", "snippet": "evidence snippet"}]}

        new_result = {**unverified, "fact_layer": "✓ 存在", "note": "phase2 found it"}

        with patch.object(p, "_verify_claim", return_value=new_result) as mock_vc:
            out = p._run_phase2_retry(results, "article text", url_snippets, {})

        self.assertEqual(mock_vc.call_count, 1)
        # Check the unverified claim was updated
        self.assertEqual(out[0]["fact_layer"], "✓ 存在")
        # The verified claim was not touched
        self.assertEqual(out[1]["fact_layer"], "✓ 存在")

    def test_phase2_improved_verdict_replaces_original(self):
        """When phase2 returns non-unverified verdict, original is replaced."""
        p = _provider()
        original = _make_claim_result("? 无法核实")
        url_snippets = {"https://a.com": [{"query": "q", "snippet": "key evidence"}]}
        improved = {**original, "fact_layer": "✓ 存在"}

        with patch.object(p, "_verify_claim", return_value=improved):
            out = p._run_phase2_retry([original], "article", url_snippets, {})

        self.assertEqual(out[0]["fact_layer"], "✓ 存在")

    def test_phase2_still_unverified_preserves_original(self):
        """When phase2 result is still '? 无法核实', original is NOT replaced."""
        p = _provider()
        original = _make_claim_result("? 无法核实", note="original note")
        url_snippets = {"https://a.com": [{"query": "q", "snippet": "snippet"}]}
        still_unverified = {**original, "note": "phase2 note"}

        with patch.object(p, "_verify_claim", return_value=still_unverified):
            out = p._run_phase2_retry([original], "article", url_snippets, {})

        # Should keep original (or at least still be unverified)
        self.assertEqual(out[0]["fact_layer"], "? 无法核实")

    def test_phase2_exception_preserves_original(self):
        """If _verify_claim raises, original result is preserved without crashing."""
        p = _provider()
        original = _make_claim_result("? 无法核实")
        url_snippets = {"https://a.com": [{"query": "q", "snippet": "snippet"}]}

        with patch.object(p, "_verify_claim", side_effect=RuntimeError("boom")):
            out = p._run_phase2_retry([original], "article", url_snippets, {})

        self.assertEqual(out[0]["fact_layer"], "? 无法核实")

    def test_extra_system_text_injected_in_verify_call(self):
        """_verify_claim is called with non-empty extra_system_text containing pool content."""
        p = _provider()
        original = _make_claim_result("? 无法核实")
        url_snippets = {"https://a.com": [{"query": "q", "snippet": "important snippet"}]}
        improved = {**original, "fact_layer": "✓ 存在"}

        with patch.object(p, "_verify_claim", return_value=improved) as mock_vc:
            p._run_phase2_retry([original], "article", url_snippets, {})

        call_kwargs = mock_vc.call_args[1]
        extra = call_kwargs.get("extra_system_text", "")
        self.assertIn("其他 claim 已搜证据池", extra)


if __name__ == "__main__":
    unittest.main()
