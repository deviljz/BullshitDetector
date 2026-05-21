"""ProviderQuirks: 按 model 名修正不兼容的 OpenAI API kwargs。

负责处理已知 model 兼容性差异（如 DeepSeek-reasoner 不支持 forced tool_choice），
让 plan_execute 在不兼容 model 上至少不崩。质量取决于 model 本身，不保证。

设计原则：
- 纯函数：返回新 dict，不修改入参（不可变性）
- 显式：每个 quirk 都有 reason，添加新 quirk 在此集中维护
- 最小：只处理"会硬性报错"的不兼容，不优化质量
"""

from typing import Any


# 已知不支持 forced tool_choice（"required" 或指定 function）的 model 前缀
# 这些 model 的服务端会直接返回 400 error。
# 来源：
# - DeepSeek 官方 issue #813: "deepseek-reasoner does not support tool_choice function"
# - OpenCode Zen 把 deepseek-v4-flash/pro 都路由到 deepseek-reasoner endpoint
_FORCED_TOOL_CHOICE_UNSUPPORTED_PREFIXES = (
    "deepseek-reasoner",
    "deepseek-v4-flash",
    "deepseek-v4-pro",
)


def _is_forced_tool_choice(tc: Any) -> bool:
    if tc == "required":
        return True
    if isinstance(tc, dict) and tc.get("type") == "function":
        return True
    return False


def apply_quirks(model: str, kwargs: dict) -> dict:
    """根据 model 名修正 kwargs。返回新 dict，不修改入参。"""
    out = dict(kwargs)
    model_lower = (model or "").lower()

    # Quirk 1: DeepSeek reasoner 系列不支持 forced tool_choice，降级为 "auto"
    if any(model_lower.startswith(p) for p in _FORCED_TOOL_CHOICE_UNSUPPORTED_PREFIXES):
        tc = out.get("tool_choice")
        if tc is not None and _is_forced_tool_choice(tc):
            out["tool_choice"] = "auto"

    return out
