# 💩 BullshitDetector — AI 鉴屎官

> Windows 桌面防忽悠神器 — 截图即鉴，一眼辨假，毒舌锐评不留情

---

## 功能概览

| 模式 | 快捷键 | 说明 |
|------|--------|------|
| 🔍 **鉴屎官** | `Alt+Q` / `Alt+V` / `Alt+T` | 联网搜索交叉核查，给出扯淡指数 + 破绽分析 |
| 📝 **总结** | 同上 | 提炼核心要点，外文自动翻译为中文 |
| ❓ **解释** | 同上 | 识别角色/梗/术语，一句话直接回答 |
| 🎬 **求出处** | 同上 | 识别截图来自哪部动漫/漫画/影视/游戏 |

---

## 快速开始

### 环境要求

- Python **3.11+**
- Windows 10 / 11

### 安装

```bash
git clone https://github.com/yourname/BullshitDetector.git
cd BullshitDetector
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 配置

```bash
copy config.json.example config.json
```

打开 `config.json`，填入 AI 模型 API Key（至少填 `active_provider` 对应的那个）。
详细说明见 [docs/API_KEYS.md](docs/API_KEYS.md)。

### 启动

```bash
start.bat
```

程序常驻系统托盘（💩），无主窗口。右键托盘图标访问菜单。

---

## 文档

- [📖 使用说明](docs/USAGE.md) — 所有功能的详细使用方式、快捷键、常见问题
- [🔑 API Key 配置](docs/API_KEYS.md) — 各 Key 用途、费用、申请步骤

---

## 项目结构

```
BullshitDetector/
├── src/
│   ├── main.py                    # 入口（托盘 + 热键 + 路由）
│   ├── ai/
│   │   ├── analyzer.py            # 对外公开接口
│   │   ├── prompts.py             # 各模式 System Prompt
│   │   ├── tools.py               # 工具（搜索 / 以图搜图）
│   │   ├── json_utils.py          # 5 级容错 JSON 解析
│   │   └── providers/
│   │       ├── base.py            # BaseLLMProvider 抽象基类
│   │       ├── openai_compat.py   # OpenAI 兼容 Provider
│   │       └── __init__.py        # 工厂函数
│   ├── config/
│   │   ├── __init__.py            # 热键常量 + 代理环境变量
│   │   └── manager.py             # 配置读写
│   ├── screenshot/
│   │   └── capture.py             # 全屏遮罩截图
│   └── ui/
│       ├── result_window.py       # 结果卡片
│       ├── unified_input_dialog.py
│       ├── loading_overlay.py
│       └── text_input_dialog.py
├── docs/
│   ├── USAGE.md                   # 使用说明
│   └── API_KEYS.md                # API Key 配置说明
├── tests/                         # 评估脚本 + 测试 fixtures
├── config.json                    # 用户配置（gitignore，勿提交）
├── config.json.example            # 配置模板
├── requirements.txt
├── start.bat
└── build.bat
```

---

## 技术栈

- **GUI** — PyQt6（无边框窗口 / 全屏遮罩 / 系统托盘）
- **截图** — Pillow + PyQt6 原生截图
- **AI** — OpenAI Python SDK（兼容所有 OpenAI 格式供应商）
- **搜索** — DuckDuckGo (`ddgs`) / Tavily (`tavily-python`)
- **以图搜图** — Google Cloud Vision API（求出处模式可选增强）
- **全局热键** — `keyboard` 库

---

## 许可证

MIT
