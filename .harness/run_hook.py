#!/usr/bin/env python
"""harness hook wrapper：没装 harness 就静默跳过（优雅降级）

这个脚本由 `harness init` 自动生成并安装到 .claude/settings.json 调用。
手改请小心——下次 harness init --force 会覆盖。
"""
from __future__ import annotations
import shutil
import subprocess
import sys


def main() -> int:
    exe = shutil.which("harness")
    if not exe:
        # 协作者没装 harness → 静默跳过，不打扰他
        return 0
    try:
        result = subprocess.run([exe, *sys.argv[1:]], check=False)
        return result.returncode
    except Exception as e:
        print(f"[harness hook] exec failed: {e}", file=sys.stderr)
        return 0  # 不阻塞对话


if __name__ == "__main__":
    sys.exit(main())
