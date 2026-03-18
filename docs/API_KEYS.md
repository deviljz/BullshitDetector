# API Key 配置说明

本文档列出所有可配置的 API Key，说明用途、费用和申请方式。

---

## 一览表

| Key | 用途 | 必须？ | 费用 |
|-----|------|--------|------|
| AI 模型 Key | 驱动所有 AI 功能（鉴屎/总结/解释/求出处）| ✅ 必须 | 视供应商而定 |
| Tavily API Key | 国内可用的搜索引擎（鉴屎官模式）| 可选 | 免费 1000 次/月 |
| Google Vision API Key | 🎬 求出处：以图搜图，大幅提升识别准确率 | 可选 | 免费 1000 次/月 |

---

## AI 模型 Key

驱动核心 AI 功能，**必须配置至少一个**。

### Gemini（推荐，默认配置）

| 项目 | 说明 |
|------|------|
| 申请地址 | https://aistudio.google.com |
| 免费层 | 有（RPM/RPD 限制，够个人使用）|
| 付费层 | 按 token 计费，**无免费额度** |
| 国内直连 | ❌ 需代理 |
| 推荐模型 | `gemini-2.5-flash`（免费层可用）|

**申请步骤：**
1. 访问 https://aistudio.google.com，用 Google 账号登录
2. 点击「Get API Key」→「Create API Key」
3. 复制 key（格式：`AIzaSy...`）填入 `config.json` 的 `providers.openai_compatible.api_key`

> **付费账号注意**：升级为 Pay-as-you-go 后，每次 API 调用按 token 计费，没有免费额度。
> 如果主要是个人轻量使用，建议保持免费层。

### DeepSeek

| 项目 | 说明 |
|------|------|
| 申请地址 | https://platform.deepseek.com |
| 费用 | 按 token 计费，价格极低（约 $0.14/百万 token）|
| 国内直连 | ✅ |
| 推荐模型 | `deepseek-chat` |

### Kimi（月之暗面）

| 项目 | 说明 |
|------|------|
| 申请地址 | https://platform.moonshot.cn |
| 费用 | 按 token 计费 |
| 国内直连 | ✅ |
| 推荐模型 | `moonshot-v1-32k` |

### 通义千问（阿里云）

| 项目 | 说明 |
|------|------|
| 申请地址 | https://dashscope.aliyun.com |
| 费用 | 按 token 计费，有免费额度 |
| 国内直连 | ✅ |
| 推荐模型 | `qwen-vl-max` |

### 智谱 GLM

| 项目 | 说明 |
|------|------|
| 申请地址 | https://open.bigmodel.cn |
| 费用 | 有免费额度 |
| 国内直连 | ✅ |
| 推荐模型 | `glm-4v-flash` |

---

## Tavily API Key（可选）

用于「🔍 鉴屎官」模式的网络搜索。不配置则使用 DuckDuckGo（需代理）。

| 项目 | 说明 |
|------|------|
| 申请地址 | https://tavily.com |
| 免费额度 | **1000 次/月**，永久免费 |
| 超出收费 | $0.01/次 |
| 国内直连 | ✅ |

**申请步骤：**
1. 访问 https://tavily.com，免费注册
2. 进入 Dashboard，复制 API Key（格式：`tvly-xxx...`）
3. 填入 `config.json` 的 `tavily_api_key` 字段
4. 托盘菜单 → 搜索引擎 → 选「Tavily（国内可用）」

---

## Google Vision API Key（可选）

用于「🎬 求出处」模式的**以图搜图**功能。配置后 AI 识别不确定时会自动调用，命中率显著提升。

| 项目 | 说明 |
|------|------|
| 申请地址 | https://console.cloud.google.com |
| 免费额度 | **每月 1000 次 WEB_DETECTION 永久免费**（无论账号是否付费）|
| 超出收费 | $1.5/1000 次 |
| 国内直连 | ❌ 需代理 |

**申请步骤：**
1. 访问 https://console.cloud.google.com，用 Google 账号登录
2. 在顶部搜索栏搜索「Cloud Vision API」，点击启用
3. 进入「API 和服务」→「凭据」→「+ 创建凭据」→「API 密钥」
4. 复制生成的 key（格式：`AIzaSy...`）
5. 填入 `config.json` 的 `google_vision_api_key` 字段

> **建议**：在凭据设置中将 API 限制设为「Cloud Vision API」，防止 key 被滥用。

**效果对比（实测）：**

| 方法 | 测试图 1（冷门漫画）| 测试图 2（バツハレ）|
|------|------|------|
| AI 纯视觉识别 | ❌ 未识别 | ❌ 未识别 |
| SauceNAO 以图搜图 | ❌ 未命中（<50%）| ❌ 未命中（<44%）|
| Google Vision | ✅ **秒识别** | ✅ **秒识别 + 杂志名** |

---

## 配置示例

```json
{
  "active_provider": "openai_compatible",
  "search_provider": "tavily",
  "tavily_api_key": "tvly-你的key",
  "google_vision_api_key": "AIzaSy-你的key",
  "providers": {
    "openai_compatible": {
      "api_key": "AIzaSy-你的Gemini-key",
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
      "model": "gemini-2.5-flash"
    }
  }
}
```
