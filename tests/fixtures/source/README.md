# source/ — 求出处测试图

每张图对应一个 `<name>.json` 预期结果（可选）。

| 文件 | 内容 | 预期 found | 备注 |
|------|------|-----------|------|
| manga_unknown_01.jpg | 黑白漫画，主角召唤剑雨场景，女性配角，中文字幕 | true/false | 用户反馈"随便找的图不对"，需验证准确率 |

## 如何添加新测试图

1. 截图存入本目录
2. 命名规则：`<media_type>_<title_hint>_<序号>.png`
   - anime_spyxfamily_01.png
   - manga_unknown_01.png
   - game_genshin_01.png
3. （可选）同名 `.json` 文件写入预期结果用于自动化测试
