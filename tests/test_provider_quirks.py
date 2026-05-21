"""单元测试：ProviderQuirks 适配层（按 model 名修正 OpenAI API kwargs）。

负责处理已知的 model 兼容性问题，让 plan_execute 在不兼容 model 上至少不崩。
质量不保证（用户选 deepseek-reasoner 当 planner 自己负责）。
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from ai.providers.quirks import apply_quirks  # type: ignore


def test_gemini_pass_through_unchanged():
    """已知支持 forced tool_choice 的 model（Gemini/GPT/etc）：kwargs 不变。"""
    kw = {"model": "gemini-3-flash-preview", "tool_choice": "required",
          "tools": [{"type": "function", "function": {"name": "x"}}]}
    out = apply_quirks(kw["model"], dict(kw))
    assert out["tool_choice"] == "required"


def test_deepseek_reasoner_required_downgraded_to_auto():
    """deepseek-reasoner 不支持 tool_choice='required'，应降级为 'auto'。"""
    kw = {"model": "deepseek-reasoner", "tool_choice": "required"}
    out = apply_quirks(kw["model"], dict(kw))
    assert out["tool_choice"] == "auto"


def test_deepseek_v4_flash_required_downgraded():
    """deepseek-v4-flash 后端是 reasoner，同样降级。"""
    out = apply_quirks("deepseek-v4-flash", {"tool_choice": "required"})
    assert out["tool_choice"] == "auto"


def test_deepseek_v4_pro_required_downgraded():
    out = apply_quirks("deepseek-v4-pro", {"tool_choice": "required"})
    assert out["tool_choice"] == "auto"


def test_deepseek_chat_no_change():
    """deepseek-chat（非 reasoner）支持 required，不应降级。"""
    out = apply_quirks("deepseek-chat", {"tool_choice": "required"})
    assert out["tool_choice"] == "required"


def test_deepseek_reasoner_specific_function_dropped():
    """指定函数 tool_choice 在 reasoner 上也不支持，降级为 'auto'。"""
    out = apply_quirks("deepseek-v4-flash", {
        "tool_choice": {"type": "function", "function": {"name": "submit_x"}}
    })
    assert out["tool_choice"] == "auto"


def test_deepseek_no_tool_choice_no_op():
    """没有 tool_choice 字段：不应添加。"""
    out = apply_quirks("deepseek-v4-flash", {"model": "deepseek-v4-flash"})
    assert "tool_choice" not in out


def test_deepseek_auto_passes_through():
    """tool_choice='auto' 兼容所有 reasoner，不变。"""
    out = apply_quirks("deepseek-v4-flash", {"tool_choice": "auto"})
    assert out["tool_choice"] == "auto"


def test_empty_kwargs_returns_empty():
    """边界：空 kwargs 不报错。"""
    out = apply_quirks("any-model", {})
    assert out == {}


def test_returns_new_dict_not_mutating():
    """不可变性：返回新对象，不修改原 kwargs。"""
    kw = {"tool_choice": "required"}
    out = apply_quirks("deepseek-v4-flash", kw)
    assert kw["tool_choice"] == "required"  # 原对象未变
    assert out["tool_choice"] == "auto"  # 新对象已修
