"""Provider 工厂 —— 根据配置字典实例化对应的 LLM Provider"""

from ai.providers.base import BaseLLMProvider
from ai.providers.openai_compat import OpenAICompatibleProvider

# Provider 注册表：config.json 中的 active_provider 键 → 类
_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "openai_compatible": OpenAICompatibleProvider,
    "gemini": OpenAICompatibleProvider,  # Gemini 通过 OpenAI 兼容层接入，由配置区分
    "deepseek": OpenAICompatibleProvider,
    "kimi": OpenAICompatibleProvider,
    "qwen": OpenAICompatibleProvider,
    "zhipu": OpenAICompatibleProvider,
}


def get_provider(config: dict) -> BaseLLMProvider:
    """
    工厂函数：从配置字典构造 Provider 实例。

    config 结构示例（对应 config.json）：
    {
        "active_provider": "openai_compatible",
        "providers": {
            "openai_compatible": {
                "api_key": "sk-xxx",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-chat"
            }
        }
    }
    """
    active = config.get("active_provider", "openai_compatible")
    provider_cfg = config.get("providers", {}).get(active, {})
    tone = config.get("response_tone", "toxic")

    cls = _REGISTRY.get(active)
    if cls is None:
        raise ValueError(
            f"未知的 provider: '{active}'。"
            f"可选值: {list(_REGISTRY.keys())}"
        )

    return cls(
        api_key=provider_cfg.get("api_key", ""),
        base_url=provider_cfg.get("base_url") or None,
        model=provider_cfg.get("model", "gemini-2.0-flash"),
        tone=tone,
    )


__all__ = ["BaseLLMProvider", "OpenAICompatibleProvider", "get_provider"]
