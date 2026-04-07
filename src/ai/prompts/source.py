from .shared import _current_date


def get_source_classify_prompt() -> str:
    """Stage 1：轻量分类，判断 source 子类型，不需要 web_search。"""
    return f"""你是一个媒介类型分类器。今天是 {_current_date}。
观察图片后立即判断媒介类型，无需搜索，直接输出 JSON。

## 分类规则
- **anime**：动漫/动画截图（赛璐珞画风、日式分镜、字幕/集数信息）
- **manga**：漫画页面/截图（黑白或彩色漫画格，气泡对话框，N格排版）
- **film_tv**：电影/电视剧真人截图（真实演员，影视画幅，字幕条）
- **game**：游戏截图/HUD（游戏界面元素、血条、地图、角色扮演画面）
- **social_post**：社交媒体帖子/表情包截图（平台UI、点赞转发、账号界面）
- **artwork**：插画/同人图/原创画（绘画风格，非标准漫画格排版，单张插图）

## 边界处理
- 有明显平台UI元素（点赞/头像/@符号）→ **social_post**
- 二次元风格但为单张插图（无格子/无字幕）→ **artwork**
- 日式分镜对话框多格 → **manga**
- 真人演员 → **film_tv**
- 不确定 → **anime**（最常见 fallback）

## 输出格式（严格 JSON，不加 markdown）
{{
  "subtype": "anime | manga | film_tv | game | social_post | artwork",
  "brief": "一句话描述图中内容（≤20字）"
}}"""


# ── 共用构件 ─────────────────────────────────────────────────────

def _search_steps(visual_focus: str, round1: list[str], round2: list[str],
                  reverse_note: str = "") -> str:
    """构建标准化搜索步骤块（步骤1-5）。"""
    r1 = "\n".join(f"   - {q}" for q in round1)
    r2 = "\n".join(f"   - {q}" for q in round2)
    rv = f"（{reverse_note}）" if reverse_note else ""
    return f"""## 必须执行的搜索步骤（至少完成 4 次 web_search 才能输出结论）

1. 分析视觉特征：{visual_focus}
2. **第一轮并行搜索**（同时发起）：
{r1}
3. **第二轮并行搜索**（根据第一轮结果细化）：
{r2}
4. 若可用，同时调用 reverse_image_search{rv}
5. **前两轮无结果时，必须换关键词继续搜索，不得直接放弃**"""


# JSON 末尾公共字段（所有子类型相同）
_JSON_TAIL = (
    '  "confidence": "high/medium/low",\n'
    '  "note": "搜索过程完整记录：每次搜索关键词、找到什么、如何确认作品身份（100字以上）",\n'
    '  "reference_image_urls": [],\n'
    '  "source_page_urls": [{"title": "维基/官方/媒体页面标题", "url": "https://..."}],\n'
    '  "_search_log": []\n'
    '}'
)

_FOUND_FALSE_NOTE = (
    'found=false 时其余字段均留空，confidence="low"，'
    'scene 描述图中实际内容，note 说明搜了什么、为何无法识别。\n'
    'source_page_urls 填搜索过程中找到的最相关权威页面（维基百科、官方数据库、知名媒体报道等），'
    '最多5条，不要填图片搜索结果页或无关来源。'
)


# ── 子类型 prompt ─────────────────────────────────────────────────

def _source_anime_prompt() -> str:
    steps = _search_steps(
        visual_focus="画风、角色发型/服装/标志道具、可见文字（对话/旁白/集数/片名）",
        round1=[
            "`[特征描述] 动漫角色` 和英文 `[feature] anime character`",
            "`[文字内容] 动漫` 或 `[visible text] anime`（可见文字/片名线索）",
        ],
        round2=[
            "`[原作名] 拷贝漫画` 或 `[原作名] 动漫之家`（确认中文译名）",
            "`[片名] episode [N]` 或 `[片名] 第X话 场景`（确认集数）",
            "角色名用日文原名 + 中文译名两个角度各搜一次",
        ],
    )
    return f"""你是一个动漫/动画作品溯源专家。今天是 {_current_date}。

{steps}

## 特别规则
- title 必须为汉化组/平台通行译名，禁止自行翻译
- characters 只填已通过搜索确认的中文角色名，猜测一律留空 []
- episode 中"END"= 本话结束，非连载完结

## 输出格式（严格 JSON，不加 markdown）
{{
  "_mode": "source", "_subtype": "anime", "found": true,
  "title": "作品中文名（汉化组通行译名）", "original_title": "原名（日文/英文）",
  "media_type": "anime", "year": "发行年份，不确定留空", "studio": "制作公司，不确定留空",
  "episode": "第X话/集，不适用留空", "episode_title": "集名，不适用留空",
  "scene": "场景详细描述（4~6句：画面构图、角色动作、情绪氛围、剧情背景）",
  "characters": ["仅填已确认的角色中文名"],
  {_JSON_TAIL}
{_FOUND_FALSE_NOTE}"""


def _source_manga_prompt() -> str:
    steps = _search_steps(
        visual_focus="页面布局（少年/少女/青年系风格）、气泡对话内容、作者签名、出版社Logo",
        round1=[
            "`[系列名] manga` 和 `[漫画名] 作者`",
            "`[气泡对话关键台词] 漫画`（找具体来源）",
        ],
        round2=[
            "`[漫画名] 拷贝漫画` 或 `[漫画名] 漫画柜`（获取通行中文名）",
            "`[author] manga`（英文搜索确认作者）",
            "`[漫画名] 第X话`（确认章节）",
        ],
    )
    return f"""你是一个漫画作品溯源专家。今天是 {_current_date}。

{steps}

## 特别规则
- title 为中文通行译名，禁止自行翻译原文
- 页面布局风格写入 note（如"周刊少年Jump风格"）
- volume/chapter 从页面信息或搜索结果确认

## 输出格式（严格 JSON，不加 markdown）
{{
  "_mode": "source", "_subtype": "manga", "found": true,
  "title": "作品中文名", "original_title": "原名（日/英）",
  "media_type": "manga", "year": "发行年份，不确定留空",
  "volume": "第X卷，不适用留空", "chapter": "第X话，不适用留空",
  "publisher": "出版社（如集英社/讲谈社），不确定留空",
  "artist": "作者名（中文/已知名），不确定留空",
  "scene": "场景详细描述（4~6句：页面内容、对话/旁白、角色动作、情节背景）",
  "characters": ["仅填已确认角色名"],
  {_JSON_TAIL}"""


def _source_film_tv_prompt() -> str:
    steps = _search_steps(
        visual_focus="演员外貌特征、字幕信息、拍摄风格、画幅比例",
        round1=[
            "`[外貌特征] [国籍] 演员` 或 `[actor description] actor`",
            "`[剧名] movie` 或 `[剧名] series`（若有字幕/片名线索）",
        ],
        round2=[
            "`[片名] [年份] 导演 演员`（补全主创信息）",
            "`[片名] 第X集 场景`（确认集数）",
        ],
    )
    return f"""你是一个影视作品溯源专家。今天是 {_current_date}。

{steps}

## 特别规则
- media_type 区分 movie（电影）/ tv（剧集）
- actors 列表只填已确认的演员真实姓名
- 场景描述包括画面氛围和情节背景

## 输出格式（严格 JSON，不加 markdown）
{{
  "_mode": "source", "_subtype": "film_tv", "found": true,
  "title": "作品中文名", "original_title": "原名（英文/其他语言）",
  "media_type": "movie/tv", "year": "上映/播出年份",
  "studio": "制片公司/出品方，不确定留空",
  "episode": "第X集，不适用留空", "episode_title": "集名，不适用留空",
  "director": "导演姓名，不确定留空",
  "actors": ["已确认的演员姓名"],
  "scene": "场景详细描述（4~6句：画面构图、演员表演、情绪氛围、剧情背景）",
  "characters": [],
  {_JSON_TAIL}"""


def _source_game_prompt() -> str:
    steps = _search_steps(
        visual_focus="HUD元素（血条/地图/技能栏）、UI风格、游戏Logo、角色造型",
        round1=[
            "`[HUD描述] game screenshot` 或 `[游戏Logo文字]`",
            "`[角色描述] game character`",
        ],
        round2=[
            "`[游戏名] developer publisher`（补全开发商信息）",
            "`[游戏名] PC/PS/Xbox/Switch`（确认平台）",
        ],
    )
    return f"""你是一个游戏作品溯源专家。今天是 {_current_date}。

{steps}

## 特别规则
- game_title 为已知中文名或官方英文名
- platform 填发布平台（PC/PS5/Xbox/Switch/Mobile等）
- scene 描述游戏画面的具体内容（地图、战斗场景、CG等）

## 输出格式（严格 JSON，不加 markdown）
{{
  "_mode": "source", "_subtype": "game", "found": true,
  "title": "游戏中文名", "original_title": "原名（英文）",
  "media_type": "game", "year": "发行年份",
  "developer": "开发商，不确定留空",
  "platform": "PC/PS5/Xbox/Switch/Mobile等",
  "scene": "场景详细描述（4~6句：游戏画面内容、HUD信息、当前场景/地图/剧情节点）",
  "characters": ["游戏角色名，已确认才填"],
  {_JSON_TAIL}"""


def _source_social_post_prompt() -> str:
    steps = _search_steps(
        visual_focus="平台水印（Twitter/微博/抖音/小红书等）、账号名/@符号、发帖时间、原文关键词",
        round1=[
            "`[关键词] site:[platform]` 或直接搜关键词（原文内容）",
            "`[账号名] [平台]`（账号溯源）",
        ],
        round2=[
            "`[事件关键词] 来源 原帖`（相关讨论）",
            "`[关键词] [年份]`（追溯发布时间）",
        ],
    )
    return f"""你是一个社交媒体内容溯源专家。今天是 {_current_date}。

{steps}

## 特别规则
- platform 识别具体平台名（Twitter/X/微博/抖音/小红书/Facebook等）
- account 填账号名或@昵称
- post_date 从界面时间戳提取，相对时间以今天 {_current_date} 为基准换算
- original_url 能找到时填原帖URL，找不到留空

## 输出格式（严格 JSON，不加 markdown）
{{
  "_mode": "source", "_subtype": "social_post", "found": true,
  "title": "帖子主题/话题（一句话）",
  "platform": "平台名称", "account": "账号名/@昵称",
  "post_date": "发帖日期，无法确认留空",
  "content_summary": "帖子内容摘要（3~4句，含核心观点/事件和互动情况）",
  "original_url": "原帖URL，找不到留空",
  "scene": "截图内容详细描述（4~6句：界面元素、发帖内容、回复内容、互动数据）",
  "characters": [],
  {_JSON_TAIL}"""


def _source_artwork_prompt() -> str:
    steps = _search_steps(
        visual_focus="画师签名（右下角/左下角）、水印、画风特征、角色造型",
        round1=[
            "`[artist name] pixiv` 或 `[画师名] twitter artwork`（签名/画师名）",
            "`[角色名/特征] fanart`（角色特征）",
        ],
        round2=[
            "`[artist ID] pixiv [series name]`（确认原始发布）",
            "`[角色名] [游戏/动漫名]`（确认所属IP）",
        ],
        reverse_note="最有效的工具，优先使用",
    )
    return f"""你是一个插画/原创画作品溯源专家。今天是 {_current_date}。

{steps}

## 特别规则
- artist 为画师名（英文ID或中文名），搜索确认后填写
- source_site 填画作发布平台（Pixiv/Twitter/ArtStation/Weibo等）
- original_url 为画作原始发布页URL，能找到时填写
- series 为画作所属系列/IP（如《原神》《蔚蓝档案》等），不属于任何IP留空

## 输出格式（严格 JSON，不加 markdown）
{{
  "_mode": "source", "_subtype": "artwork", "found": true,
  "title": "画作标题或角色名",
  "media_type": "other", "year": "创作年份，不确定留空",
  "artist": "画师名/ID",
  "source_site": "Pixiv/Twitter/ArtStation等",
  "original_url": "原始发布页URL，找不到留空",
  "series": "所属IP/系列，无则留空",
  "scene": "画作内容详细描述（4~6句：构图风格、角色形象、画风特征、所属IP/系列背景）",
  "characters": ["画中角色名，已确认才填"],
  {_JSON_TAIL}"""


# ── 对外接口 ──────────────────────────────────────────────────────

def get_source_prompt(subtype: str = "anime") -> str:
    """Stage 2：根据 subtype 返回对应的专化溯源 prompt。"""
    _DISPATCH = {
        "anime":       _source_anime_prompt,
        "manga":       _source_manga_prompt,
        "film_tv":     _source_film_tv_prompt,
        "game":        _source_game_prompt,
        "social_post": _source_social_post_prompt,
        "artwork":     _source_artwork_prompt,
    }
    return _DISPATCH.get(subtype, _source_anime_prompt)()
