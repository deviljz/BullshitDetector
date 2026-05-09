# P0+P1+P2: claim 核查兜底 submit + fetch_url 工具 + phase2 重核

> 方案层产物。按 6 大区填写，complexity 必填。

**complexity**: complex  <!-- simple | complex -->

---

## 1. Objective（目标）

**做什么**：
- P0：plan_execute 路径中 `_verify_claim()` 5 轮搜索结束仍未提交时，追加一次 force-submit 调用（tool_choice 强制 submit_claim_result），消除"核查超时或失败"误导性 fallback。
- P2：新增 `fetch_url(url, focus)` 工具供 verify 循环使用，让模型能读完整网页正文（而不只是搜索 snippet），用 trafilatura 抽正文 + url_cache 全程共享。
- P1（B+ 简化版）：phase 1 并行 verify 跑完后，扫描 verdict="? 无法核实" 的 claim；如有则进入 phase 2 串行重核，把 phase 1 所有 claim 已搜过的 URL + 多 snippet 合并 pool 注入"无法核实" claim 的二轮调用，让其能借助其他 claim 找到的证据重新判定。

**为什么做**：当前架构两个根本缺陷——
1. 5 轮搜完没提交 → 显示"核查超时或失败"，误导用户以为系统坏了。
2. 模型只能看搜索引擎给的 200-500 字 snippet，万字文章里的关键信息读不到，导致同一篇 163 文章对 claim 1 命中、对 claim 2/3 漏判（最新一条鉴定就是这个 bug）。

**用户是谁**：plan_execute 路径用户（付费 Gemini / Claude）。Classic 路径不动。

**成功标准**（可验证）：
1. 复现 case：拿 2026-05-09 全球通史那条重跑，3 个曾被判"无法核实"的 claim 至少 1 个变 ✓ 存在或写出有信息量的"无法核实"note。
2. 新工具 `fetch_url` 单测覆盖：正常抓取 + 超时 + 抽取失败 + url_cache 命中。
3. 端到端跑现有 plan_execute 不回归（既有 claim 1 判定不变）。

**非目标**：
- 不改 classic 路径。
- 不改并行 verify 主流程（fetch_url 只是新增工具，不重排执行顺序；phase 2 是 phase 1 后的新增阶段，不打乱 phase 1 内部并行）。
- phase 2 不放宽单 claim fetch 预算（仍 2 次）。

---

## 2. Commands（提供哪些命令/接口）

无新对外命令。新增内部工具：

- `fetch_url(url: str, focus: str = "") -> str`
  - 抓取并抽取网页正文（trafilatura → BeautifulSoup 兜底 → 失败返回 "fetch failed: <reason>"）
  - 抽取后做关键词聚焦切片：
    - `focus` 非空时，先从正文按段落切，保留含 focus 关键词的段落 + 前后各 1 段上下文，拼接至 8000 字上限
    - 命中不足或 `focus` 为空 → 回退"正文开头 8000 字"
  - 单次返回硬上限 8000 字（中文），超出加 "...（已截断）"
  - 全 analyze 共享 url_cache（按 URL 键，命中不重复请求）
  - verify loop 调用时把当前 claim 文本作为 `focus` 传入

---

## 3. Structure（目录/模块）

```
src/ai/tools.py
    ← 新增 fetch_url 函数 + FETCH_URL_TOOL schema
    ← 新增 url_cache（模块级 dict）
    ← execute_tool 增加 fetch_url 分支
src/ai/providers/plan_mixin.py
    ← P0：5 轮 verify 循环后追加 force-submit 调用（tool=[SUBMIT_CLAIM_RESULT_TOOL]，tool_choice="required"）
    ← P2：verify_tools 加入 FETCH_URL_TOOL；_run_one_search 扩展为分发 web_search / fetch_url
    ← P1：维护 url_snippets 累加映射（在 _verify_claim 搜索结果回调里追加）；
          analyze_article_plan_execute 末尾加 _run_phase2_retry：
          扫描"无法核实" claim、构建 B+ pool（多 snippet 合并、单 URL 上限 600 字、总 4000 字）、
          串行重跑、替换结果（仅当 verdict 改善）
    ← _verify_claim 加 extra_system_text 可选参数，phase 2 注入 pool
requirements.txt
    ← 新增 trafilatura
tests/test_fetch_url.py
    ← 新建：fetch_url 工具单测
tests/test_verify_force_submit.py
    ← 新建：P0 force-submit 单测
tests/test_phase2_retry.py
    ← 新建：P1 phase 2 重核单测
```

---

## 4. Style（代码风格 / 依赖选型）

- 遵循现有 tool_use schema 风格（参考 `SUBMIT_CLAIM_RESULT_TOOL` 写法）。
- trafilatura 抽取失败时回退 BeautifulSoup `get_text()`；再失败返回字符串 `"fetch failed: <reason>"`，**不抛异常**（保持工具调用契约）。
- 4 条硬保护栏（实装强制）：
  1. 单次 fetch 截断 8000 字（中文），超出加 "...（已截断）"
  2. 单 claim 内 fetch 次数上限 2 次（超出工具直接返回 "fetch budget exhausted"）
  3. 全 analyze 共享 url_cache（同 URL 只下载一次）
  4. fetch 超时 5 秒，超时返回 "fetch timeout"
- prompt 不写"对 163.com 这类 URL 优先 fetch"等特例化指令；通用规则放在 `get_claim_verify_prompt()` 里："搜索 snippet 不足以判断时可调用 fetch_url 读完整正文"。
- 新依赖只加 trafilatura（`pip install trafilatura`），不引入 selenium/playwright 等浏览器栈。
- 遵循全局 Python style：type annotation、不可变默认参数、无 print。
- P1 B+ pool 构造规则：
  - 数据源：phase 1 verify 过程中 `_run_one_search` 回调里维护的 `url_snippets: dict[url, list[str]]`，每条 search 结果对应 URL 追加 snippet。
  - 同 URL 多 snippet 哈希去重（snippet 文本 md5）。
  - 单 URL 总长度上限 600 字，超出忽略后续 snippet。
  - 总 pool 上限 4000 字，超出按 URL 出现频次排序保留前 N 条。
  - pool 文本格式：每 URL 一段，含"片段 N（来自 query "..."）：snippet 内容"。
- P1 触发条件：phase 1 完成后 `[r for r in results if r["verdict"] == "? 无法核实"]` 非空。无则跳过 phase 2，零开销。
- P1 失败回落：phase 2 重跑结果若 verdict 仍是"? 无法核实"，**保留 phase 1 原结果不退化**（不覆盖原有 sources/note）。

---

## 5. Testing（测试策略）

- **单元 `tests/test_fetch_url.py`**（fetch_url 纯函数）：mock httpx，验证：
  1. trafilatura 抽取成功路径
  2. trafilatura 抽不到时回退 BeautifulSoup `get_text`
  3. 全失败返回 `"fetch failed: <reason>"`
  4. 单次硬截断 8000 字生效
  5. url_cache 命中时不重复请求 httpx
  6. 超时返回 `"fetch timeout"`
  7. `focus` 关键词命中段落优先返回（含前后 1 段上下文）
  8. `focus` 命中不到时回退正文头部 8000 字
- **P0 单元 `tests/test_verify_force_submit.py`**：mock LLM，让前 5 轮都不返回 submit_tc → 验证第 6 轮 force-submit 调用触发，result 非 None，fact_layer 由模型给出而不是写死 "? 无法核实"。
- **P2 集成单元 `tests/test_verify_fetch_dispatch.py`**：mock LLM 让模型第 1 轮返回 `fetch_url` tool_call → 验证 verify loop 正确分发到 fetch_url（mock httpx 返回固定正文）→ tool message 回喂 → 第 2 轮模型基于正文 submit。补充验证：
  - 同一 URL 跨 claim 调用走 url_cache（mock httpx 只被调一次）
  - 单 claim 内第 3 次 fetch 返回 "fetch budget exhausted"
- **P1 单元 `tests/test_phase2_retry.py`**：
  - 触发：构造 phase 1 结果含至少 1 个 "? 无法核实" → 验证 _run_phase2_retry 被调用
  - 不触发：phase 1 全部 verdict 已确定 → 验证 _run_phase2_retry 跳过、零额外 LLM 调用
  - pool 构造：构造 url_snippets 含同 URL 3 个不同 snippet → 验证 pool 正确合并、去重、含来源 query 提示
  - 单 URL 截断：构造 url_snippets 含 1 个 URL × 5 个 200 字 snippet → 验证单 URL 总长度被截到 600 字
  - 总 pool 截断：构造 30 个 URL × 200 字 → 验证总 pool 截到 4000 字、按出现频次排序保留
  - 重跑成功：mock LLM 让重跑返回 verdict="✓ 存在" → 验证原结果被替换
  - 重跑仍失败：mock LLM 让重跑仍返回 "? 无法核实" → 验证原结果保留不退化
- **集成（人工跑一次）**：用 2026-05-09 全球通史那条 cache_id 重跑 plan_execute，对比改前 / 改后 claim 2 和 claim 3 的 verdict 与 sources。
- **回归**：跑 `tests/aiqa/` 已审过的 fixtures，确保 verdict 不变。

---

## 6. Boundaries（边界）

### 绝不做
- 不改 classic 路径。
- 不改 phase 1 内部并行 verify 结构（phase 2 是 phase 1 后串行新增阶段，不打乱 phase 1）。
- 不在 prompt 里硬编码"对 163.com 这类 URL 优先 fetch"等特例。
- 不引入除 trafilatura 外的新依赖（不上 selenium/playwright）。
- fetch 不做反爬伪装（不模拟浏览器、不处理 JS 渲染、不破解 paywall）。
- 不缓存到磁盘（url_cache / url_snippets 仅内存、随 analyze 生命周期）。
- phase 2 不放宽单 claim fetch 预算（仍 2 次）。
- phase 2 失败不退化（重跑仍"无法核实"则保留 phase 1 原结果，不覆盖原 sources/note）。

### 必须做
- 4 条硬保护栏全部实装（截断 8000 字 / 单 claim 2 次 fetch / url_cache / 5 秒超时）。
- P0 force-submit 失败时回落原有 "核查超时或失败" fallback（不影响主流程）。
- fetch_url 失败必须返回 string 不抛异常（保持工具调用契约）。
- requirements.txt 同步加 trafilatura。
- 用 2026-05-09 全球通史那条 case 做回归验证（claim 2/3 至少 1 条 verdict 改善）。
- phase 2 仅在存在"? 无法核实" claim 时触发，无则零开销。
- pool 构造规则严格执行：单 URL 600 字上限、总 pool 4000 字上限、超出按频次保留。

---

## 执行计划（可选）

| 阶段 | 交付物 | 估时 |
|---|---|---|
| 1. P0 force-submit | plan_mixin.py 改 + test_verify_force_submit.py | 30min |
| 2. fetch_url 工具 | tools.py 新函数 + 4 保护栏 + test_fetch_url.py | 60min |
| 3. P2 verify 集成 | plan_mixin.py 接入 FETCH_URL_TOOL + test_verify_fetch_dispatch.py | 30min |
| 4. P1 phase 2 重核 | _run_phase2_retry + url_snippets + B+ pool + test_phase2_retry.py | 60min |
| 5. 端到端验证 | 跑全球通史 case + 回归 fixtures | 30min |
