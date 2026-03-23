
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
