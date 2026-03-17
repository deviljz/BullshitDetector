# 💩 BullshitDetector — AI 鉴屎官

> Windows 桌面防忽悠神器 — 截图即鉴，一眼辨假，毒舌锐评不留情

---

## 功能概览

| 模式 | 快捷键/入口 | 说明 |
|------|-----------|------|
| 🔍 **鉴屎官** | `Alt+Q` → 框选 → 鉴屎官 | 联网搜索交叉核查，给出扯淡指数 + 破绽分析 |
| 📝 **总结** | `Alt+Q` → 框选 → 总结 | 提炼核心要点，外文自动翻译为中文 |
| ❓ **解释** | `Alt+Q` → 框选 → 解释 | 识别角色/梗/术语，一句话直接回答 |
| 🖼 **图片分析** | `Alt+V` 或托盘菜单 | 粘贴/拖拽图片，同样支持三种模式 |
| 📄 **文字/链接** | `Alt+T` 或托盘菜单 | 粘贴文章正文或 URL，鉴定可信度 |

**加载动画**随模式不同变化：`👃 正在闻屎中` / `📝 正在总结中` / `❓ 正在解释中`

---

## 快速开始

### 环境要求

- Python **3.11+**
- Windows 10 / 11

### 安装步骤

**1. 克隆项目**

```bash
git clone https://github.com/yourname/BullshitDetector.git
cd BullshitDetector
```

**2. 创建虚拟环境并安装依赖**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**3. 配置 API Key**

```bash
copy config.json.example config.json
```

打开 `config.json`，填入你的模型 API Key（至少填 `active_provider` 对应的那个）：

```json
{
  "active_provider": "openai_compatible",
  "search_provider": "ddg",
  "tavily_api_key": "tvly-你的key（可选，国内用户推荐）",
  "providers": {
    "openai_compatible": {
      "api_key": "你的 Gemini / OpenAI Key",
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
      "model": "gemini-2.0-flash"
    }
  }
}
```

**4. 启动**

```bash
start.bat
```

程序常驻系统托盘，无主窗口。右键托盘图标访问设置和菜单。

---

## 使用说明

### 截图鉴定（Alt+Q）

1. 按 `Alt+Q` 唤起全屏遮罩
2. 按住左键拖拽框选目标内容（聊天截图、新闻、朋友圈等）
3. 松手后弹出预览确认弹窗，选择模式：
   - **📝 总结** — 快速提炼，不联网
   - **❓ 解释** — 看不懂就解释，不联网
   - **🔍 鉴屎官** — 联网核查真实性
4. 右下角出现加载动画，AI 分析完毕后弹出结果卡片

### 图片分析（Alt+V）

1. 复制任意图片到剪贴板（或准备好图片文件）
2. 按 `Alt+V`，自动读取剪贴板图片，或手动拖拽文件
3. 选择模式后开始分析

### 托盘菜单

右键系统托盘图标：
- **截图分析** — 同 `Alt+Q`
- **文字/链接分析** — 粘贴文章或 URL
- **图片分析** — 同 `Alt+V`
- **搜索引擎** — 切换 DuckDuckGo / Tavily
- **回复风格** — 毒舌讽刺 / 专业严肃 / 幽默风趣 / 简洁直白

---

## 搜索引擎配置

鉴屎官模式需要联网搜索核实声明。支持两种搜索引擎，可在托盘菜单实时切换：

| 引擎 | 国内可用 | 配置 |
|------|---------|------|
| **DuckDuckGo**（默认）| ❌ 需要代理/VPN | 无需 Key |
| **Tavily** | ✅ 直连可用 | 需 API Key，免费 1000 次/月 |

**Tavily 配置方法：**
1. 访问 https://tavily.com 免费注册
2. 复制 API Key（格式：`tvly-xxxxxxxx`）
3. 填入 `config.json` 的 `tavily_api_key` 字段
4. 托盘菜单 → **搜索引擎** → 选「Tavily（国内可用）」

> 解释和总结模式不需要联网，搜索引擎设置仅影响「🔍 鉴屎官」模式。

---

## 切换大模型

修改 `config.json` 的 `active_provider` 字段即可：

| 供应商 | active_provider 值 | 推荐模型 | 国内直连 |
|--------|-------------------|---------|---------|
| Gemini (Google) | `openai_compatible` | `gemini-2.5-flash`（免费层可用） | ❌ |
| DeepSeek | `deepseek` | `deepseek-chat` | ✅ |
| Kimi（月之暗面）| `kimi` | `moonshot-v1-32k` | ✅ |
| 通义千问 | `qwen` | `qwen-vl-max` | ✅ |
| 智谱 GLM | `zhipu` | `glm-4v-flash` | ✅ |

所有端点和模型名已在 `config.json.example` 中预填。

---

## 重建虚拟环境

如依赖有更新或环境损坏：

```bash
rmdir /s /q .venv
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## 打包为 exe

```bash
build.bat
```

输出在 `dist\BullshitDetector.exe`。打包后将 `config.json` 放到 exe 同目录下运行。

---

## 项目结构

```
BullshitDetector/
├── src/
│   ├── main.py                    # 入口（托盘 + 热键 + 路由）
│   ├── ai/
│   │   ├── analyzer.py            # 对外公开接口
│   │   ├── prompts.py             # 各模式 System Prompt
│   │   ├── tools.py               # 搜索工具（DDG / Tavily）
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
│       ├── result_window.py       # 结果卡片（鉴屎/总结/解释三种布局）
│       ├── screenshot_confirm_dialog.py
│       ├── image_input_dialog.py
│       ├── loading_overlay.py
│       └── text_input_dialog.py
├── tests/                         # 评估脚本 + 测试 fixtures
├── config.json                    # 用户配置（gitignore，勿提交）
├── config.json.example            # 配置模板
├── requirements.txt
├── start.bat                      # 启动脚本
└── build.bat                      # 打包脚本（PyInstaller）
```

---

## 常见问题

**Q: 按热键没反应？**
A: `keyboard` 库在 Windows 需要管理员权限。右键 `start.bat` → 以管理员身份运行。

**Q: 鉴屎官显示"搜索失败"？**
A: DuckDuckGo 国内无法直连，切换到 Tavily（托盘菜单 → 搜索引擎）。

**Q: 打包后 exe 闪退？**
A: 确认 `config.json` 与 exe 在同一目录，且 `api_key` 已填写。

**Q: 解释/总结也需要联网吗？**
A: 不需要。只有「🔍 鉴屎官」模式会触发搜索。

---

## 技术栈

- **GUI** — PyQt6（无边框窗口 / 全屏遮罩 / 系统托盘）
- **截图** — Pillow + PyQt6 原生截图
- **AI** — OpenAI Python SDK（兼容所有 OpenAI 格式供应商）
- **搜索** — DuckDuckGo (`ddgs`) / Tavily (`tavily-python`)
- **全局热键** — `keyboard` 库

---

## 许可证

MIT
