# -*- coding: utf-8 -*-
"""
pytest tests for _PlanExecuteMixin._verify_claim force-submit fallback.

Three cases:
1. force-submit triggers and succeeds → result uses model's note, not hardcoded fallback
2. force-submit raises Exception → falls back to hardcoded "核查超时或失败"
3. normal path (submit in round 1) → only 1 _create_with_retry call, no force-submit
"""
import sys
import pathlib
import json
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from ai.providers.plan_mixin import _PlanExecuteMixin


# ---------------------------------------------------------------------------
# Helpers to build fake OpenAI-style response objects
# ---------------------------------------------------------------------------

def _make_tool_call(name: str, arguments: dict, tc_id: str = "tc1"):
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments, ensure_ascii=False)
    return tc


def _make_resp(tool_calls, prompt_tokens=10, completion_tokens=5):
    msg = MagicMock()
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


# ---------------------------------------------------------------------------
# Minimal concrete class that mixes in _PlanExecuteMixin
# ---------------------------------------------------------------------------

class _FakeProvider(_PlanExecuteMixin):
    """Bare-minimum host so _PlanExecuteMixin methods work."""
    _model = "fake-model"

    def _create_with_retry(self, **kwargs):
        raise NotImplementedError("must be patched in each test")


# ---------------------------------------------------------------------------
# Case 1: force-submit triggers and succeeds
# ---------------------------------------------------------------------------

def test_force_submit_triggers_and_succeeds():
    """5 rounds only return web_search; 6th call returns submit_claim_result."""
    provider = _FakeProvider()

    # Rounds 1-5: only web_search tool_call (no submit)
    search_tc = _make_tool_call("web_search", {"query": "some query"}, tc_id="s1")
    search_resp = _make_resp([search_tc])

    # Round 6 (force-submit): submit_claim_result
    submit_args = {
        "fact_layer": "? 无法核实",
        "note": "基于已搜信息：找到 X 但不直接对应",
        "effective_sources": 1,
    }
    submit_tc = _make_tool_call("submit_claim_result", submit_args, tc_id="sub1")
    force_resp = _make_resp([submit_tc])

    call_count = {"n": 0}

    def fake_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 5:
            return search_resp
        return force_resp

    # Patch web_search_with_sources to avoid real network calls
    with patch("ai.providers.plan_mixin.web_search_with_sources",
               return_value=("搜索结果内容", ["http://example.com"])):
        provider._create_with_retry = fake_create
        result = provider._verify_claim("某个声明", "文章背景")

    assert result["fact_layer"] == "? 无法核实"
    assert result["note"] == "基于已搜信息：找到 X 但不直接对应", (
        f"note should be from model, got: {result['note']!r}"
    )
    assert call_count["n"] == 6, f"Expected 6 calls (5 rounds + force), got {call_count['n']}"


# ---------------------------------------------------------------------------
# Case 2: force-submit raises Exception → hardcoded fallback
# ---------------------------------------------------------------------------

def test_force_submit_exception_falls_back():
    """Force-submit raises → result is hardcoded 'note=核查超时或失败'."""
    provider = _FakeProvider()

    search_tc = _make_tool_call("web_search", {"query": "some query"}, tc_id="s1")
    search_resp = _make_resp([search_tc])

    call_count = {"n": 0}

    def fake_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 5:
            return search_resp
        raise Exception("API down")

    with patch("ai.providers.plan_mixin.web_search_with_sources",
               return_value=("搜索结果内容", ["http://example.com"])):
        provider._create_with_retry = fake_create
        result = provider._verify_claim("某个声明", "文章背景")

    assert result["note"] == "核查超时或失败", (
        f"Should fall back to hardcoded note, got: {result['note']!r}"
    )
    assert result["fact_layer"] == "? 无法核实"
    assert result["sources"] == []


# ---------------------------------------------------------------------------
# Case 3: normal path — submit in round 1, no force-submit
# ---------------------------------------------------------------------------

def test_normal_path_no_force_submit():
    """Round 1 returns submit_claim_result → only 1 _create_with_retry call."""
    provider = _FakeProvider()

    submit_args = {
        "fact_layer": "✓ 基本属实",
        "note": "有可靠来源支持",
        "effective_sources": 2,
    }
    submit_tc = _make_tool_call("submit_claim_result", submit_args, tc_id="sub1")
    submit_resp = _make_resp([submit_tc])

    call_count = {"n": 0}

    def fake_create(**kwargs):
        call_count["n"] += 1
        return submit_resp

    with patch("ai.providers.plan_mixin.web_search_with_sources",
               return_value=("不会被调用", [])):
        provider._create_with_retry = fake_create
        result = provider._verify_claim("某个声明", "文章背景")

    assert call_count["n"] == 1, f"Expected 1 call, got {call_count['n']}"
    assert result["fact_layer"] == "✓ 基本属实"
    assert result["note"] == "有可靠来源支持"
