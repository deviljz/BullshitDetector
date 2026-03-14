# AIQA — AI 鉴屎官质量保障流程

> **AIQA = AI Quality Assurance for 鉴屎官**
> 每次新增 fixture 或修改 prompt 时执行此流程，确保模型行为与人工判断一致。

---

## 流程概览

```
新图片 → [1] 人工鉴定 → [2] 写入 expectations → [3] 运行自动化测试 → [4] 对比结论 → [5] 迭代
```

---

## Step 1：人工鉴定图片

将图片放入 `tests/fixtures/`，然后**人工逐图审查**，回答以下问题：

- 这张图的**核心信息声明**是什么？
- 是否有造假迹象（数据篡改、截图合成、来源归属伪造、时空穿越）？
- 最终判断：
  - `expected_fake`: `True`（造假）/ `False`（真实）
  - `expected_bs_min`: 预期 bullshit_index 下限（0-100）
  - `reason`: 一句话说明判断依据

**注意事项：**
- 区分"截图内容是真实发生的事"与"截图本身是伪造的"
- 社交媒体讨论截图（转发/评论/批评）≠ 官方数据声明，不触发铁律一否决权
- 参考已有结论：`memory/project_aiqa_fixtures.md`

---

## Step 2：写入 expectations

编辑 `tests/run_vision_eval.py`，在 `EXPECTATIONS` 字典中新增条目：

```python
"<文件名>.jpg": {
    "label": "<简短描述>",
    "expected_fake": True,   # 或 False
    "expected_bs_min": 80,   # BS 分下限（fake=False 时填 0）
    "reason": "<一句话判断依据>",
},
```

---

## Step 3：运行自动化测试

```bash
cd F:/Project/BullshitDetector
python -X utf8 tests/run_vision_eval.py
```

测试会对每张图调用真实 AI（含 web_search），输出每条结果的 ✅/❌。

---

## Step 4：对比结论

| 情况 | 含义 | 行动 |
|---|---|---|
| ✅ 全部通过 | AI 结论与人工判断一致 | 流程结束 |
| ❌ AI 给假图低分 | prompt 漏洞或搜索失败 | 检查 prompt 铁律，补充适用边界 |
| ❌ AI 给真图高分 | 误判，prompt 过于激进 | 检查铁律边界，必要时增加 prompt 说明 |
| ❌ 人工判断有误 | 重新审查图片 | 修正 `expected_fake`/`expected_bs_min` |

---

## Step 5：迭代

根据 Step 4 结论，修改以下之一或多个：

- `src/ai/prompts.py` — 修补 prompt 漏洞
- `tests/run_vision_eval.py` — 修正错误标注
- 回到 Step 3 重新运行，直到全部 ✅

---

## 目标

每次 AIQA 结束时，`run_vision_eval.py` 应输出全部 ✅，即 **N/N**（N 为当前 fixture 总数）。

---

## 文件结构

```
tests/
  fixtures/          ← 放置待鉴定图片
  run_vision_eval.py ← 自动化测试主文件（含 EXPECTATIONS 字典）
src/
  ai/
    prompts.py       ← 鉴定 prompt（铁律在此定义）
docs/
  AIQA.md            ← 本文档
```
