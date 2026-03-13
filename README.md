# BullshitDetector（鉴屎官）

一个智能内容真实性检测桌面工具，帮助用户识别网络上的虚假信息、夸大宣传和不实言论。

## 核心功能

- **快捷键截图** — 按 `Alt+Q` 唤起全屏遮罩，框选区域截图
- **AI 分析** — 自动将截图发送至 OpenAI GPT-4o 进行真实性分析
- **结果弹窗** — 以 Markdown 格式展示分析结果，支持一键复制
- **系统托盘** — 常驻后台，右键菜单快捷操作

## 技术栈

- Python 3.10+
- PyQt6（GUI / 截图遮罩）
- OpenAI API（GPT-4o 视觉分析）
- mss + Pillow（屏幕截图）

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 OPENAI_API_KEY

# 启动
python src/main.py
```

> Linux 下 `keyboard` 库需要 root 权限监听全局快捷键，可使用 `sudo python src/main.py`。

## 许可证

MIT
