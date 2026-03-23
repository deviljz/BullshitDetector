
## [进行中] verify 先验偏见问题（羊蹄山之魂测试用例）

### 现状
- bi 稳定在 60-100 区间，用户期望约 25
- 已修复：reflect 不再追加"某人在GDC演讲"/"游戏计划发售"类禁止声明
- 已修复：Python 层 eff=0 时强制改判 ✗ 伪造 → ? 无法核实
- 已修复：narrative 声明提示去掉前作对比鼓励
- 已修复：reasoning_effort medium→low

### 剩余问题
模型有时仍输出 eff=2 + ✗ 伪造（违反"来源有效性过滤"规则），原因是：
- 模型找到 Ghost of Tsushima 2021 GDC 演讲来源（Samuel Hawley + Event Deck）并计入 eff=2
- 最新一次测试，模型甚至错误生成了"Samuel Hawley 是 DREDGE 程序员"的幻觉（已通过外部搜索证伪）

### 真实情况（外部验证）
- Ghost of Yotei 已于 **2025年9月25日**发售，MC 实际评分 **86分**（文章说87）
- Samuel Hawley 的 GDC "Event Deck" 演讲是关于 Ghost of **Tsushima**（2021年），非 Ghost of Yotei
- Ghost of Yotei 是否有 Samuel Hawley GDC 2026 演讲：**未确认**

### 下一步方向
1. 确认文章的核心声明（Event Deck/Samuel Hawley/两天回本）是否确实属于 Ghost of Tsushima 被误移植到 Ghost of Yotei
2. 如果是真实的 张冠李戴 文章，bi=76+ 才是正确答案，之前 bi=25 反而是太宽松
3. 若需要保持宽松，考虑在 Python 层对 eff≤1 且 attribution_note 包含"张冠李戴"的 ✗ 伪造 进行二次限流

---

## 加载指示器 UI 改版

**现状：** 右下角两个小窗口——一个图标、一个带"..."动画的文字。

**目标：** 合并为一个窗口，左右分区：
- **左侧**：图标 + 静态文字（去掉"..."动画）
- **右侧**：动态阶段文字，类似 Gemini 网页版，根据当前实际操作显示内容（"正在提取声明…" / "正在搜索：xxx" / "正在汇总结果…" 等），不是固定名称

**实现要点：**
- 右侧文字需要从 AI 执行流程中实时推送（通过 pyqtSignal）
- staged 模式：Stage1提取声明 → Stage2并行搜索各声明（显示搜索词）→ Stage2.5反思 → Stage3汇总
- classic 模式：显示每轮 tool_call 的搜索词
- 非鉴屎官模式：显示通用进度（"正在分析…"）

## 来源溯源 + 数据层分离（方向1 + 方案B）

### 方向1：来源溯源（source genealogy）
在 Stage 2 verify prompt 中加显式检查步骤：
- 搜到多个来源后，判断它们是否都引用同一篇原始报道（发布时间集中、措辞相似）
- 若是，effective_sources 强制记为1，来源性质按原始那篇定
- 纯 prompt 改动，不影响 schema

### 方案B：数据层拆分"被报道"vs"已核实"
在 claim_verification 每条记录中新增字段：
```json
"source_genealogy": "multi_independent" | "same_source_syndicated" | "official_only" | "unknown"
```
- `multi_independent`：多个真正独立的来源确认
- `same_source_syndicated`：多个来源但都引用同一原始报道
- `official_only`：仅有当事方官方声明
- `unknown`：无法判断
UI 据此差异化渲染（如"官方自述"改为黄色标签）

**实施顺序：** 先做方向1（prompt），再做方案B（schema + UI）
