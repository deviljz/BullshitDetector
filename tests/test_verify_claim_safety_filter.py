"""单元测试：verify_claim 遇到 message=None（如 Gemini 安全过滤）不应崩溃。

Gemini 对极端内容（斩首/阉割等）触发安全过滤时，OpenAI 兼容端点会返回
choices[0].message = None。plan_mixin verify 主循环若裸访问 .tool_calls 会抛
"'NoneType' object has no attribute 'tool_calls'"，使整条并发 pipeline 崩溃。

本测试锁定该契约：message=None 时该条 claim 应安全回落到 "? 无法核实"，
不影响其它并发 claim。
"""

import sys
import pathlib
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from ai.providers.plan_mixin import _PlanExecuteMixin  # type: ignore


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResp:
    """模拟安全过滤返回：usage 缺失、message 为 None。"""

    def __init__(self, message):
        self.usage = None
        self.choices = [_FakeChoice(message)]


class _StubNoneMessage(_PlanExecuteMixin):
    _model = "main-model"

    def _create_with_retry(self, **kwargs):
        return _FakeResp(None)  # Gemini 安全过滤：message=None


class _StubEmptyChoices(_PlanExecuteMixin):
    _model = "main-model"

    def _create_with_retry(self, **kwargs):
        resp = _FakeResp(None)
        resp.choices = []  # 极端情况：choices 为空
        return resp


def test_verify_claim_survives_none_message():
    """message=None（安全过滤）时不抛异常，回落到 '? 无法核实'。"""
    with patch("config.manager.load", return_value={}):
        result = _StubNoneMessage()._verify_claim("某极端血腥声明", "文章背景摘要")
    assert isinstance(result, dict)
    assert result["fact_layer"] == "? 无法核实"
    assert result["claim"] == "某极端血腥声明"


def test_verify_claim_survives_empty_choices():
    """choices 为空时同样安全回落，不抛 IndexError。"""
    with patch("config.manager.load", return_value={}):
        result = _StubEmptyChoices()._verify_claim("另一条声明", "背景")
    assert isinstance(result, dict)
    assert result["fact_layer"] == "? 无法核实"
