import requests, base64, json, sys

import os
API_KEY = os.environ.get('GOOGLE_API_KEY') or __import__('json').loads(open('config.json').read()).get('providers', {}).get('openai_compatible', {}).get('api_key', '')
img_path = sys.argv[1] if len(sys.argv) > 1 else 'tests/fixtures/source/manga_unknown_02.jpg'

with open(img_path, 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode()

payload = {
    "contents": [{
        "parts": [
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": img_b64
                }
            },
            {
                "text": "这是一张漫画截图，请用Google搜索找出这是哪部漫画，给出作品名、作者、出版杂志。用中文回答。"
            }
        ]
    }],
    "tools": [{"google_search": {}}],
    "generationConfig": {"temperature": 0}
}

resp = requests.post(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}',
    json=payload,
    timeout=30,
)

print('Status:', resp.status_code)
if resp.status_code != 200:
    print(resp.text[:500])
    exit(1)

data = resp.json()
candidate = data['candidates'][0]
content = candidate['content']['parts']

for part in content:
    if 'text' in part:
        print('\n=== Gemini 回答 ===')
        print(part['text'])
    if 'executableCode' in part:
        print('\n[搜索查询]', part['executableCode'].get('code', ''))

# Show grounding metadata if available
grounding = candidate.get('groundingMetadata', {})
chunks = grounding.get('groundingChunks', [])
if chunks:
    print(f'\n=== 引用来源 ({len(chunks)} 条) ===')
    for c in chunks[:5]:
        web = c.get('web', {})
        print(f'  {web.get("title", "")}')
        print(f'  {web.get("uri", "")}')
