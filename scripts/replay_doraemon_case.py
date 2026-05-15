'''Replay 2026-05-15 Doraemon case (cache_id=96d575236f8eee31).

Goal: verify that after the nature-consistency fix + submit_verdict prompt update,
the header fields no longer contradict each other.

Before fix:
  bullshit_index=100, nature=属实, risk=极度危险, truth_label=0% 属实  ← 矛盾
After fix (expected):
  bullshit_index high (likely ~100), nature in {事实错误/局部失实},
  verdict_text/one_line_summary aligned with claim verdicts (no longer assuming Doraemon)
'''
import sys, os, json, base64, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

from ai.analyzer import analyze_screenshot_staged

CACHE = 'historyCache/96d575236f8eee31'
EXTRA_TEXT = '这么多年了，还有读者记得第二行台词说翻译不对'

with open(f'{CACHE}/images/0.jpg', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode()

print(f'Running plan_execute on cache_id=96d575236f8eee31 (Doraemon)\n')
result = analyze_screenshot_staged([img_b64], extra_text=EXTRA_TEXT)

print('=' * 70)
print('=== HEADER ===')
for k, v in result.get('header', {}).items():
    print(f'  {k}: {v}')

print('\n=== CLAIM VERIFICATION ===')
for i, c in enumerate(result.get('claim_verification', [])):
    print(f"\n[{i}] {c.get('claim','')[:200]}")
    print(f"    fact_layer={c.get('fact_layer')} verdict={c.get('verdict')} importance={c.get('claim_importance')} polarity={c.get('polarity')}")

print('\n=== ONE LINE ===')
print(result.get('one_line_summary'))
print('\n=== TOXIC ===')
print(result.get('toxic_review'))
print('\n=== CAVEATS ===')
for c in (result.get('investigation_report') or {}).get('caveats', []):
    print(f'  - {c}')

print('\n=== CONSISTENCY CHECK ===')
from ai.providers.plan_mixin import _claim_is_fake, _claim_is_verified
hdr = result.get('header', {})
bi = hdr.get('bullshit_index')
nat = hdr.get('bullshit_nature')
cv = result.get('claim_verification', [])
fake_n = sum(1 for c in cv if _claim_is_fake(c))     # polarity-aware
verified_n = sum(1 for c in cv if _claim_is_verified(c))
ok = not (fake_n > 0 and nat in {'属实', '基本属实', '真实但离谱'})
print(f'  bi={bi}, nature={nat}, fake_n={fake_n}, verified_n={verified_n} (polarity-aware)')
print(f'  consistency: {"OK ✓" if ok else "FAIL ✗ (nature contradicts claim consensus)"}')
