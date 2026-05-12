# phase1 单 claim 雪球效应优化

> 方案层产物。按 6 大区填写，complexity 必填。

**complexity**: simple  <!-- simple | complex -->

---

## 1. Objective（目标）

**做什么**：
4 条独立调优降低 phase 1 单 claim 的 input token 雪球效应：
- A. **保留 5 轮上限**，但增加**动态停损**：单 claim 内若某一轮的任一 query 与之前轮次已搜过的 query 完全相同 → 该轮处理完毕后立即跳出 search 循环，触发 force-submit 兜底。理由：实测有些 case 模型陷入"每轮重复同样 query"的空转循环（如全球通史 replay），停损避免空转 5 轮。
- B'. fetch_url 预算 = "1 次成功 fetch"（失败/超时不计入预算，允许失败后换 URL 再试）
- C. fetch_url 返回硬上限：8000 字 → 4000 字（中文）
- D. web_search 单条 snippet 截断：~500 字 → 300 字

**为什么做**：
- 实测全球通史 case：单 claim "中文版表格" phase 1 跑出 88K input tokens（占 phase 1 总开销 47%）。
- 雪球来源：5 轮循环每轮 messages 包含累积的 search snippet + fetch_url 全文 + tool 反馈，第 5 轮 input 是第 1 轮的 5-10 倍。
- 单 case 总 token 195K 中，单 claim 88K 是显著瓶颈。

**用户是谁**：plan_execute 路径（付费 Gemini / Claude）用户。Classic 路径不动。

**成功标准**（可验证）：
1. 全球通史 cache_id=c94b6e58 replay：phase 1 总 input 从 ~187K 砍到 ≤ 130K（-30%）。
2. 全 analyze 总 input 从 ~195K 砍到 ≤ 150K。
3. claim verdict 质量不显著退化：claim "中文版表格" verdict 仍判 ✓ 存在；其他 claim verdict 与上次提交（commit 0f7135f）跑结果总体一致（允许 LLM 随机波动 1 个 claim 内）。
4. 40 个 unit test 全过；本任务新增的 fetch_url 4000 截断 / snippet 300 截断 / phase 1 默认 max_rounds=4 / fetch 失败不计预算 单测过。

**非目标**：
- 不动 phase 2 参数（已是 max_rounds=2、fetch budget=1）。
- 不实现 messages 历史压缩 / round 摘要化（复杂、易引入 bug，留下个 spec）。
- 不改 prompt 的搜索指引文字。
- 不改 force-submit 触发条件。
- 不动 url_cache 大小 / lifecycle。
- 不动 claim 拆解去重（已完成）。

---

## 2. Commands（提供哪些命令/接口）

无新对外命令，仅内部参数与常量调整：
- `_verify_claim` 内维护 `seen_queries: set[str]`，每轮 search_tcs 处理时判断：若该轮任一 query 已在 `seen_queries`，标记 `_repeat_triggered = True`，该轮 tool 响应正常回填后跳出 search 循环（仍走 force-submit 兜底）。
- `_verify_claim` 内 fetch 预算改为"1 次成功"：仅当返回内容**不是** `"fetch failed: ..."` / `"fetch timeout"` 时计入 fetch_count。
- `src/ai/tools.py` 新增常量：
  - `_FETCH_TRUNCATE = 4000`（原 8000）
  - `_SNIPPET_TRUNCATE = 300`
- `_format_search_results` 内每条 snippet 截断到 `_SNIPPET_TRUNCATE` 字，超出加 "..."。

---

## 3. Structure（目录/模块）

```
src/ai/providers/plan_mixin.py
    ← _verify_claim phase 1 仍 max_rounds=5（phase 2 显式传 2 不变）
    ← _verify_claim 新增 seen_queries 集合 + 重复 query 检测，命中即跳出 search 循环
    ← fetch_url 调用回填 tool message 后：仅当成功才 fetch_count += 1
    ← 单 claim fetch_count 上限从 2 → 1
src/ai/tools.py
    ← 新增 _FETCH_TRUNCATE = 4000、_SNIPPET_TRUNCATE = 300 常量
    ← _apply_focus_and_truncate 用 _FETCH_TRUNCATE 替换硬编码 8000
    ← _format_search_results 内每条 snippet 截断到 _SNIPPET_TRUNCATE
tests/test_fetch_url.py
    ← case test_hard_truncate_8000 改名 test_hard_truncate_4000 + 阈值断言改 4000
    ← 新增 test_snippet_truncated_to_300
tests/test_verify_force_submit.py
    ← 新增 test_repeat_query_triggers_early_termination：mock 让模型 round 2 重发 round 1 的 query
       验证 verify 循环在 round 2 后立即跳出（不再到 round 3-4），最终走 force-submit
    ← 新增 test_fetch_failure_not_counted_in_budget：mock 让 fetch_url 返回 "fetch failed:..."
       验证 fetch_count 未递增，模型可继续 fetch 下一 URL
```

---

## 4. Style（代码风格 / 依赖选型）

- 截断常量集中在 `src/ai/tools.py` 顶部，命名 `_FETCH_TRUNCATE` / `_SNIPPET_TRUNCATE`。
- snippet 截断在 `_format_search_results` 内统一做（覆盖 DDG + Tavily 两个 provider），不要在各 provider 抓取处做。
- "失败不计预算"判定：内容前缀严格匹配 `"fetch failed:"` 或 等于 `"fetch timeout"`（其他字符串视为成功）。
- 重复 query 检测：`seen_queries` 集合在 `_verify_claim` 内初始化，key 为 query 字符串原文（不做 normalize）。检测命中后**本轮的 tool 响应必须正常回填**（OpenAI 协议），然后再 break。
- 重复 query 检测命中时，**该轮新 query（非重复部分）也照常执行**，结果一并塞入 messages，避免丢失模型最后一波探索。
- 不引入新依赖。
- max_rounds 签名保持 5，phase 2 调用处仍显式传 2，向后兼容。

---

## 5. Testing（测试策略）

- **单元更新**（`tests/test_fetch_url.py`）：
  - 旧 `test_hard_truncate_8000` → 重命名 `test_hard_truncate_4000`：mock 返回 5000 字 → 断言 ≤ 4000+"已截断" 后缀长度
  - 新增 `test_snippet_truncated_to_300`：mock `_search_provider.search` 返回 1 条 500 字 snippet → 断言 `_format_search_results` 输出该 snippet ≤ 300 字 + "..."
- **单元更新**（`tests/test_verify_force_submit.py`）：
  - 原 force-submit 测试保留（max_rounds=5 不变）
  - 新增 `test_repeat_query_triggers_early_termination`：mock LLM round 1 返回 query A，round 2 又返回 query A → 断言 search 循环在 round 2 后跳出（非 round 4），调用 _create_with_retry 总次数明显少于 5 + force-submit
  - 新增 `test_fetch_failure_not_counted_in_budget`：mock LLM 让模型连续 3 次返回 fetch_url tool_call；mock `fetch_url` 前 2 次返回 `"fetch failed: HTTP 403"`、第 3 次返回正文；断言 fetch_count 最终 = 1，模型成功 fetch 第 3 个 URL
- **集成（人工跑一次）**：
  - 全球通史 cache_id=c94b6e58 replay
  - 记录改前 / 改后对比到 `scripts/_replay_global_history.json`：phase 1 总 input、单 claim 最高 input、claim verdict、header verdict 文本
  - 与上次提交（commit 0f7135f）数据对比

---

## 6. Boundaries（边界）

### 绝不做
- 不动 phase 2 参数（max_rounds=2、fetch budget=1）。
- 不实现 messages 历史压缩 / round 摘要化。
- 不改 prompt 文本（claim_verify / planner / replanner）。
- 不改 force-submit 触发条件或 force-submit 内部逻辑。
- 不动 url_cache 大小 / lifecycle / reset 时机。
- 不在 fetch_url / web_search 函数签名上加新参数（仅内部常量调整）。
- "失败不计预算"不放宽到 phase 2（phase 2 单独是 budget=1，本任务不动）。

### 必须做
- max_rounds 默认值改 4 后所有调用点向后兼容。
- snippet 截断对 DDG / Tavily 两个 provider 都生效（在 _format_search_results 统一截）。
- 截断逻辑保留 "..." / "已截断" 提示文字。
- 4 条改动彼此独立，可单独 revert（不互相依赖）。
- 全球通史 replay 跑一次，记录数字对比并附在 PR / commit message。
- 全部 40 个原有 unit test + 本次新增 4 个测试全过。

---

## 执行计划

| 阶段 | 交付物 | 估时 |
|---|---|---|
| 1. 改 _verify_claim：seen_queries 重复检测 + fetch budget "成功才计" | plan_mixin.py | 20min |
| 2. 改 fetch_url 截断 + snippet 截断（常量化） | tools.py | 15min |
| 3. 更新 / 新增 单测 | tests/ | 25min |
| 4. 全球通史 replay 验证 + 记录 token 对比 | scripts/_replay_global_history.json + commit message | 10min |
