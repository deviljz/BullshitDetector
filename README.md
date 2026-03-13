# 鉴屎官 BullshitDetector

> Windows 桌面防忽悠神器 — 截图即鉴，一眼辨假，毒舌锐评不留情

---

## 功能特性

| 功能 | 说明 |
|---|---|
| **快捷键唤醒** | `Alt+Q` 全局快捷键，随时可用 |
| **框选截图** | 亮青色选框 + 实时尺寸提示，丝滑框选任意屏幕区域 |
| **多模型支持** | Gemini / DeepSeek / Kimi / 通义千问 / 智谱，改一行配置切换 |
| **ReAct 推理** | AI 自主调用 DuckDuckGo 搜索核实近期事件，三大铁律交叉验证 |
| **赛博朋克卡片** | 无边框毛玻璃结果卡片，旋转印章 + 弧形仪表盘 + 毒舌锐评大字高亮 |
| **加载动画** | "👃 正在闻屎中..." 角落动画，AI 思考期间不尴尬 |
| **系统托盘** | 常驻后台，右键菜单快捷操作，零打扰 |

---

## 快速开始（Windows）

### 1. 环境要求

- Python **3.10+**
- Windows 10 / 11

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

复制配置模板并填入你的 API Key：

```bash
copy config.json.example config.json
```

打开 `config.json`，修改 `active_provider` 和对应 provider 的 `api_key`：

```json
{
  "active_provider": "openai_compatible",
  "providers": {
    "openai_compatible": {
      "api_key": "你的真实Key",
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
      "model": "gemini-2.0-flash"
    }
  }
}
```

### 4. 启动

```bash
python src/main.py
```

程序会最小化到系统托盘，**无主窗口**。

### 5. 使用

1. 按 `Alt+Q` 唤起全屏遮罩
2. 按住左键拖拽框选目标区域（聊天记录、新闻截图等）
3. 松手后右下角出现 "👃 正在闻屎中..." 动画
4. AI 分析完毕后弹出结果卡片

---

## 切换大模型

只需修改 `config.json` 的 `active_provider` 字段：

| 供应商 | active_provider 值 | 推荐模型 |
|---|---|---|
| Gemini (Google) | `openai_compatible` | `gemini-2.0-flash` |
| DeepSeek | `deepseek` | `deepseek-chat` |
| Kimi（月之暗面）| `kimi` | `moonshot-v1-32k` |
| 通义千问 | `qwen` | `qwen-vl-max` |
| 智谱 GLM | `zhipu` | `glm-4v-flash` |

所有供应商的 API 端点和模型名称均已在 `config.json.example` 中预填。

---

## 项目结构

```
BullshitDetector/
├── src/
│   ├── main.py                    # 应用入口（托盘 + 快捷键调度）
│   ├── ai/
│   │   ├── analyzer.py            # 对外接口（8行薄调度层）
│   │   ├── prompts.py             # 鉴屎官 System Prompt（三大铁律）
│   │   ├── json_utils.py          # 5级容错 JSON 解析
│   │   ├── tools.py               # DuckDuckGo 搜索工具
│   │   └── providers/
│   │       ├── base.py            # BaseLLMProvider 抽象基类
│   │       ├── openai_compat.py   # OpenAI 兼容 Provider（ReAct 循环）
│   │       └── __init__.py        # 工厂函数 get_provider()
│   ├── config/
│   │   ├── __init__.py            # 环境变量兼容层（SCREENSHOT_HOTKEY 等）
│   │   └── manager.py             # ConfigManager（读 config.json，回退 .env）
│   ├── screenshot/
│   │   └── capture.py             # 全屏遮罩 + mss 截图
│   └── ui/
│       ├── result_window.py       # 赛博朋克结果卡片
│       └── loading_overlay.py     # 加载动画
├── tests/
│   ├── test_screenshot_only.py    # 截图链路独立测试（不依赖 AI）
│   ├── test_logic.py              # AI 逻辑单元测试
│   └── run_eval.py                # 自动化评估 pipeline
├── config.json                    # 用户配置（已 gitignore，勿提交）
├── config.json.example            # 配置模板（可提交）
├── requirements.txt
└── .env.example                   # 旧版环境变量配置（向后兼容）
```

---

## 配置说明

### config.json（推荐）

新版配置文件，支持多 Provider 管理，改 `active_provider` 即可一键切换：

```json
{
  "active_provider": "deepseek",
  "providers": {
    "deepseek": {
      "api_key": "sk-xxxxxxxx",
      "base_url": "https://api.deepseek.com",
      "model": "deepseek-chat"
    }
  }
}
```

### .env（旧版，仍支持）

如果没有 `config.json`，程序会自动回退读取 `.env` 文件：

```env
OPENAI_API_KEY=your_key
OPENAI_API_BASE=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

---

## 仅测试截图功能

不依赖 AI 模块，只验证框选截图链路：

```bash
python tests/test_screenshot_only.py
# 按 Alt+Q → 框选 → 控制台打印保存路径
```

截图保存至项目根目录 `temp_capture.png`。

---

## 技术栈

- **GUI** — PyQt6（无边框窗口 / 全屏遮罩 / 系统托盘）
- **截图** — mss（极速屏幕捕获）+ Pillow
- **AI** — OpenAI Python SDK（兼容所有 OpenAI 格式的供应商）
- **搜索** — DuckDuckGo（免费实时搜索，无需 API Key）
- **全局快捷键** — keyboard 库

---

## 许可证

MIT
