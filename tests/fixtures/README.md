# tests/fixtures — 测试数据目录

## 目录结构

```
fixtures/
├── analyze/      # 鉴屎官模式（截图/文章真实性鉴定）
├── explain/      # 解释模式（角色识别、梗、概念）
├── summarize/    # 总结模式
└── source/       # 求出处模式（动漫/游戏/电影来源识别）
```

## 原有 fixtures/ 根目录文件

根目录下的 `.png/.jpg` 文件均属于 **analyze** 类别（历史遗留），
新增测试图请放到对应子目录。

## 命名规范

```
<media_type>_<content_hint>_<序号>.<ext>
```

- `analyze/`: fake_physics_01.png, real_news_02.png ...
- `source/`: manga_unknown_01.png, anime_spyxfamily_01.png ...
- `explain/`: meme_npc_01.png, char_luffy_01.png ...
