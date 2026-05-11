"""快速测试 explain 功能：覆盖 meme / concept / identify 三种 type"""
import sys, json, base64, io
sys.path.insert(0, 'src')

from PIL import Image
from ai.analyzer import explain_screenshot


def img_to_b64(path: str) -> str:
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


test_cases = [
    ("meme  - YYDS 梗",            "tests/fixtures/explain_meme_yyds.png"),
    ("concept - RAG 术语",          "tests/fixtures/explain_concept_rag.png"),
    ("concept - 虾番茄谣言",        "tests/fixtures/fake_food_shrimp_tomato_warning.png"),
    ("meme   - 美国梗图",            "tests/fixtures/real_weibo_us_meme_liberal_mock.jpg"),
    ("identify - 老东西日漫拼图(25角色)", "tests/fixtures/identify_anime_bingo_oldschool.jpg"),
    ("identify - 机甲（EVA实物）",   "tests/fixtures/identify_mecha_lineup.jpg"),
    ("identify - 游戏角色cos",       "tests/fixtures/identify_game_chars.jpg"),
    ("identify - 星际牛仔cos",       "tests/fixtures/identify_anime_chars.jpg"),
]

for label, path in test_cases:
    print(f"\n{'='*60}")
    print(f"  TEST: {label}")
    print(f"{'='*60}")
    try:
        result = explain_screenshot([img_to_b64(path)])
        ok = "✓" if not result.get("error") else "✗"
        print(f"  {ok} type:         {result.get('type')}")
        print(f"  {ok} subject:      {result.get('subject')}")
        print(f"    short_answer: {result.get('short_answer')}")
        chars = result.get('characters', [])
        if chars:
            print(f"    characters({len(chars)}): " + ", ".join(
                f"{c.get('name')}《{c.get('work')}》" for c in chars[:5]
            ) + ("..." if len(chars) > 5 else ""))
        print(f"    detail:       {result.get('detail')}")
        print(f"    origin:       {result.get('origin')}")
        usage = result.get('usage', '')
        if usage:
            print(f"    usage:        {usage}")
        print(f"    orig_lang:    {result.get('original_language')}")
        if result.get('error'):
            print(f"  !! ERROR: {result.get('error')}")
    except Exception as e:
        import traceback
        print(f"  !! EXCEPTION: {e}")
        traceback.print_exc()

print("\nDone.")
