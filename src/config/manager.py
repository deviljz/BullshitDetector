"""
ConfigManager —— 读取 config.json，支持回退到环境变量。

加载优先级（高到低）：
  1. 项目根目录的 config.json
  2. 环境变量 / .env 文件（向后兼容旧用户）
"""

import json
import os
import sys
import pathlib

# 打包后用 exe 所在目录；开发时用项目根目录
if getattr(sys, "frozen", False):
    _CONFIG_PATH = pathlib.Path(sys.executable).parent / "config.json"
else:
    _CONFIG_PATH = pathlib.Path(__file__).parent.parent.parent / "config.json"


def load() -> dict:
    """
    返回统一格式的配置字典。

    若 config.json 存在且有效，优先使用；
    否则从环境变量构造兼容配置（保持旧版 .env 用户无感升级）。
    """
    if _CONFIG_PATH.exists():
        try:
            with _CONFIG_PATH.open(encoding="utf-8") as f:
                cfg = json.load(f)
            _validate(cfg)
            return cfg
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[ConfigManager] config.json 解析失败，回退到环境变量: {e}")

    return _from_env()


def save(config: dict) -> None:
    """将配置持久化到 config.json（供设置 UI 调用）"""
    _validate(config)
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_active_provider_cfg(config: dict | None = None) -> dict:
    """快捷方法：返回当前激活 provider 的配置段"""
    cfg = config or load()
    active = cfg.get("active_provider", "openai_compatible")
    return cfg.get("providers", {}).get(active, {})


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _validate(cfg: dict) -> None:
    if "active_provider" not in cfg:
        raise ValueError("config.json 缺少 'active_provider' 字段")
    if "providers" not in cfg:
        raise ValueError("config.json 缺少 'providers' 字段")


def _from_env() -> dict:
    """从环境变量构造兼容格式的配置字典"""
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_API_BASE", "") or None
    model = os.getenv("OPENAI_MODEL", "gemini-2.0-flash")

    # 根据 base_url 猜测 active_provider 名称（仅用于日志，功能无影响）
    if base_url and "deepseek" in base_url:
        active = "deepseek"
    elif base_url and "moonshot" in base_url:
        active = "kimi"
    elif base_url and "dashscope" in base_url or (base_url and "aliyun" in base_url):
        active = "qwen"
    else:
        active = "openai_compatible"

    return {
        "active_provider": active,
        "providers": {
            active: {
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
            }
        },
    }
