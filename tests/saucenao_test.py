import requests, json, sys

API_KEY = 'YOUR_SAUCENAO_KEY_HERE'
img_path = sys.argv[1] if len(sys.argv) > 1 else 'tests/fixtures/source/manga_unknown_02.jpg'

with open(img_path, 'rb') as f:
    img = f.read()

resp = requests.post(
    'https://saucenao.com/search.php',
    data={'output_type': 2, 'db': 999, 'numres': 5, 'api_key': API_KEY},
    files={'file': ('manga.jpg', img, 'image/jpeg')},
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
    timeout=20,
)

print('Status:', resp.status_code)
if resp.status_code == 200:
    data = resp.json()
    for res in data.get('results', [])[:5]:
        h, d = res['header'], res['data']
        title = d.get('source') or d.get('title') or d.get('eng_name') or d.get('jp_name') or '未知'
        url = (d.get('ext_urls') or [''])[0]
        print(f"[{h['similarity']}%] {title}")
        print(f"  {url}")
else:
    print(resp.text[:500])
