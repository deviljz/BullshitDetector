# harness hook 改动说明与反馈

**目标读者**：harness-core 的开发者 / 维护者
**报告者项目**：BullshitDetector（Windows 桌面 PyQt 应用 + Flutter 客户端）
**harness 版本**：使用 `harness init` 自动安装的默认 hook 配置
**反馈日期**：2026-04-24

---

## 1. 原厂 hook 默认行为

`harness init` 执行后自动向 `.claude/settings.json` 注入两个 hook：

```jsonc
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": "python \"$CLAUDE_PROJECT_DIR/.harness/run_hook.py\" check --on-edit \"$CLAUDE_TOOL_FILE_PATH\" --warn-only"
      }]
    }
  ],
  "Stop": [
    {
      "hooks": [{
        "type": "command",
        "command": "python \"$CLAUDE_PROJECT_DIR/.harness/run_hook.py\" check --gate"
      }]
    }
  ]
}
```

`matcher` 字段限定的是 **tool 名称**（`Edit|Write|MultiEdit`），不限定文件路径。
每次 Claude 做任何文件编辑（不管是 `src/` 源码、`docs/` 文档、`.harness/config.yaml`、`README.md`、`CHANGELOG.md`），都会触发一次 `harness check --on-edit <path>`，进而跑 `pytest` 扫描 `tests/`。

---

## 2. 我们项目里的实际问题

### 2.1 钩子被误触发的场景

用户在 session 里连续做了这些改动，**每一处都触发了 harness check → pytest**：

- 改 `README.md`（加项目结构说明）
- 改 `docs/USAGE.md`（更新 FAQ）
- 新增 `CHANGELOG.md`
- 改 `build.bat`
- 改 `.claude/settings.json` 自身
- 改 `.harness/config.yaml`

这些都**不是项目代码**，理应不触发 harness 验证。

### 2.2 pytest 扫到 UI 测试 → Qt 窗口抢焦点

本项目 `tests/` 下有大量 `*_test.py` 命名的脚本，其中许多是 PyQt UI 渲染测试
（如 `result_window_test.py`, `loading_overlay_test.py`, `dialog_*.py`,
`unified_input_dialog_test.py`, `stamp_*.py`），会实例化 `QApplication` +
弹出 `QWidget`。

后果：**每次编辑文档都会弹一堆 Qt 窗口抢焦点**，用户在前台其他应用工作时被反复打断。

### 2.3 Stop hook 的额外放大

`Stop` hook 在 **每一轮 Claude 对话结束** 都会跑 `harness check --gate`，
即便用户只是闲聊没有改代码，也会触发全量 pytest，同样抢焦点。

---

## 3. 我们做的 workaround

**改动 A：重写 `.harness/run_hook.py`，加路径过滤**

```python
def _should_run_on_edit(argv: list[str]) -> bool:
    """只有 src/**/*.py 才算"真项目代码"，其余路径一律跳过。"""
    if "--on-edit" not in argv:
        return True  # 非 on-edit 调用（--gate 等）放行
    try:
        i = argv.index("--on-edit")
        path = argv[i + 1]
    except (ValueError, IndexError):
        return True
    norm = path.replace("\\", "/")
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").replace("\\", "/")
    if project_dir and norm.startswith(project_dir):
        norm = norm[len(project_dir):].lstrip("/")
    return norm.startswith("src/") and norm.endswith(".py")


def main() -> int:
    argv = sys.argv[1:]
    if not _should_run_on_edit(argv):
        return 0  # 非项目代码，直接静默返回
    # ... 原有逻辑 ...
```

**改动 B：`.claude/settings.json` 移除 Stop hook**，只保留 PostToolUse。

**改动 C：`.harness/config.yaml` 的 `targets[0].ignore_paths` 明确列出所有
会弹 UI 的测试脚本**：

```yaml
ignore_paths:
  - "tests/ui_*.py"
  - "tests/dialog_*.py"
  - "tests/unified_input*.py"
  - "tests/result_window_test.py"
  - "tests/loading_overlay_test.py"
  - "tests/stamp_*.py"
  - "tests/chat_*.py"
  - "tests/force_show_test.py"
  - "tests/mode_btn_*.py"
  - "tests/startup_opacity_test.py"
  - "tests/fullscreen_*.py"
  - "tests/self_test.py"
  - "tests/flutter_*.py"
  - "tests/python_ref_capture.py"
  - "tests/replay_*.py"  # 会实际调 LLM API 消耗配额
  - "tests/generate_*.py"
  - "tests/capture_*.py"
  - "tests/accuracy_*.py"
  - "tests/run_*.py"
  - "tests/compare_models.py"
  - "tests/saucenao_test.py"
  - "tests/usage_window*.py"
```

以上 3 层是"防御纵深"，任何一层失效另两层兜底。

---

## 4. 给 harness 开发者的建议（按优先级）

### 🔴 P0：`harness init --force` 会覆盖我们改过的 `run_hook.py`

文件头部原注释说"手改请小心——下次 harness init --force 会覆盖"，这是我们本地最关键的定制点。**下次升级 harness 我们的路径过滤就没了**。

**建议**：

- **方案 A（首选）**：把路径过滤 **下沉到 harness CLI 本体**——`harness check --on-edit <path>` 在进入 pytest 前，先读 `config.yaml` 里某个新字段（例如 `code_paths` 或 `trigger_on_edit_paths`），不匹配就直接 `exit 0`。这样 run_hook.py 保持薄，定制逻辑走配置。
- **方案 B**：`harness init` 检测到 `run_hook.py` 已被修改（比如 hash 不等于默认）就跳过覆盖，或加交互确认。
- **方案 C**：把 `run_hook.py` 拆成"通用 wrapper" + "项目级过滤脚本"，后者 init 不覆盖。

### 🟠 P1：`Stop` hook 过于激进

按目前设计，每一轮用户↔Claude 对话结束都跑 `harness check --gate`，即便本轮根本没碰代码。对日常问答/咨询场景是纯浪费；对我们这种 test suite 里混 UI 测试的项目是**反复抢焦点**。

**建议**：

- `harness init` 默认**只装 PostToolUse**，把 `Stop` 改成可选（`harness init --with-gate` 才装）。
- 或者 `Stop` hook 内部加判断：本轮 context 里是否真的有 Edit/Write 发生过，没有就 skip。

### 🟡 P2：`config.yaml` 的 `ignore_paths` 语义不清晰

我们的实测是：`ignore_paths` 似乎只在 **assertion_ast** 等静态检查生效，**没有传递到 pytest 命令行**（pytest 还是扫全 tests/）。

**建议**：

- 明确 `ignore_paths` 的作用边界（文档说明）；
- 或把 `ignore_paths` 翻译成 `pytest --ignore=<path>` 参数自动拼进命令行，让一处配置多处生效。

### 🟢 P3：`harness check` 发现 `0 passed, 0 failed` 时应该 `status=skip` 或 `info`，不是 `warn`

`python_test` 检查返回 `exit_code=1`（pytest 在没收集到测试时返回 1），被 harness 映射成 `warn`。但"项目没 pytest-style 测试"和"有测试但全 fail"语义完全不同，前者应该是 `skip` 或 info。

---

## 5. 我们目前的最终状态

- **保留**：PostToolUse + `run_hook.py` 自带路径过滤 + `config.yaml` 的 `ignore_paths` 排除 UI 测试
- **移除**：Stop hook
- **作用效果**：只有改 `src/**/*.py` 才会跑 `harness check`；其它一切（docs, config, settings, README, build.bat）完全无感

希望这些反馈对 harness-core 的下一版迭代有帮助。如需更多细节或复现步骤，项目仓库可参考 commit `4798ee5`(Apr 2026) 以后的 `.harness/` 目录。
