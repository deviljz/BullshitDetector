import requests, base64, json, sys

API_KEY = sys.argv[1] if len(sys.argv) > 1 else ''
img_path = sys.argv[2] if len(sys.argv) > 2 else 'tests/fixtures/source/manga_unknown_02.jpg'

with open(img_path, 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode()

payload = {
    "requests": [{
        "image": {"content": img_b64},
        "features": [{"type": "WEB_DETECTION", "maxResults": 10}]
    }]
}

resp = requests.post(
    f'https://vision.googleapis.com/v1/images:annotate?key={API_KEY}',
    json=payload,
    timeout=30,
)

print('Status:', resp.status_code)
if resp.status_code != 200:
    print(resp.text[:500])
    exit(1)

data = resp.json()['responses'][0].get('webDetection', {})

# Best guess labels
entities = data.get('webEntities', [])
print('\n=== Web Entities (作品名候选) ===')
for e in entities[:8]:
    score = e.get('score', 0)
    desc = e.get('description', '')
    if desc:
        print(f'  [{score:.2f}] {desc}')

# Pages with matching images
pages = data.get('pagesWithMatchingImages', [])
print(f'\n=== Pages with matching images ({len(pages)} found) ===')
for p in pages[:5]:
    print(f'  {p.get("url", "")}')
    title = p.get('pageTitle', '')
    if title:
        print(f'    → {title}')

# Visually similar images
similar = data.get('visuallySimilarImages', [])
print(f'\n=== Visually similar images ({len(similar)} found) ===')
for s in similar[:5]:
    print(f'  {s.get("url", "")}')
