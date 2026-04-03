---
description: API Key 和敏感信息安全规则
---

# 安全规则

- **任何 API Key、Token、密码、密钥严禁写入代码文件**，只能写入 `config.json`（已在 .gitignore 中）。
- 测试脚本、注释、日志、文档中同样禁止出现真实 Key。
- 提交前必须检查：`git diff --cached` 中不得含任何 key 字符串。
- **提交流程**：先本地 `git commit`，再用 `git diff HEAD~1 HEAD` 检查无敏感信息，确认后才执行 `git push`。
