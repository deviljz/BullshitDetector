# Changelog

本文件记录 BullshitDetector 的版本变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- Win32 原生全局热键模块 `src/hotkey_win32.py`，使用 `user32.RegisterHotKey` + `QAbstractNativeEventFilter` 捕获 `WM_HOTKEY`
- `src/history_cache.py`：内容寻址缓存鉴定原始输入，供"查看历史"还原

### 变更

- **热键实现改为 OS 托管**：替换 `keyboard` 库底层 hook 方案。原方案在 Windows 休眠/唤醒后 hook 失效、60 秒 QTimer 兜底无法覆盖"休眠期间 timer 停摆"场景；改用 Win32 原生 API 后由 OS 管理热键状态，休眠/唤醒/锁屏自动保持有效
- Plan-Execute 路径 `SUBMIT_CLAIM_RESULT_TOOL.fact_layer` 描述加固：要求声明整体（主语+时间+事件+客体）全部成立才能判 ✓，禁止因"时间点真实存在"或"主语/平台真实存在"就宽松判 ✓
- 分析输出 schema 移除 `radar_chart` / `risk_level` 字段
- `tests/` 下截图、运行时 json、`history.json` / `historyCache/` / `usage.json`、`flutter_app/` 等加入 `.gitignore`

### 修复

- `build.bat` 的 `pip install --upgrade pip` 报错：改为 `python -m pip install --upgrade pip`，避免 pip.exe 自我替换时的文件锁问题
- FAQ "按热键没反应" 说明同步更新为 Win32 方案下的排查流程（占用冲突 winerror 1409 / 管理员优先级 / 自定义热键）

### 移除

- `keyboard>=0.13.5` 依赖从 `requirements.txt` 移除
- `main.py` 中 `_reregister_hotkeys` 方法与 60 秒 QTimer 兜底逻辑

---

## 历史版本概要（自 2026-03-13 首次 commit 起）

以下按功能主题归纳，详细变更见 `git log`。

### Plan-and-Execute 路径（付费精细路径）

- `identify_narrative` 工具提取文章隐含叙事结论
- 声明核查多维度 tool_use 结构化输出（fact / name / number / cause 四层 enum）
- 消除偏乐观 fallback，必须显式通过工具提交结论
- "决定性"声明最多 2 条参与满权重计算
- `claim_importance` 分级指引写入 planner prompt
- 超时声明半惩罚 + `hype_check` 必填兜底
- 同轮 `web_search` 并行执行，claim 内搜索从串行变并行
- 搜索次数限制最多 2 次，防速度回退

### Classic 路径（免费 Gemini 路径）

- `bullshit_nature` 九选一强制枚举（事实错误 / 局部失实 / 基本属实 / 夸大渲染 / 真实但离谱 / 标题党 / 断章取义 / 逻辑混乱 / 属实）
- 有 ✗ 声明时禁止选 "真实但离谱"
- `claim_verification` 补充 `verdict` 字段，修复 UI 全部显示问号
- `sources` 字段兼容字符串与 dict 两种格式
- `_current_date` 惰性求值，避免模块加载时固化日期

### UI / 交互

- 扯淡性质印章（bullshit_nature badge）
- 搜索过程查询词 + 对比参考图标题改为可点击链接
- 参考图点击打开原图、相关来源改用 AI 搜索结果
- Gemini 工具在追问场景禁用，修复追问注入 `_current_date` 问题

### 抓取 / 数据源

- `xueqiu` / `weibo` / `zhihu` 等 WAF 域名改用 Playwright 抓取
- Playwright 加 stealth 模式绕过雪球阿里云 WAF 滑动验证

### 工程

- 项目规则迁移至 `.claude/rules/` 目录
- 移除死代码 `get_final_verdict_prompt` / `get_framing_check_prompt`
- Flutter 客户端启动脚本 `start_flutter.bat` 与辅助测试脚本
