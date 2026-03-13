import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gemini-2.0-flash")
SCREENSHOT_HOTKEY = "alt+q"

# 搜索引擎配置
SEARCH_ENGINE = os.getenv("SEARCH_ENGINE", "duckduckgo")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_SEARCH_CX = os.getenv("GOOGLE_SEARCH_CX", "")
