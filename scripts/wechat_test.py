"""测试微信文章提取"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import warnings
warnings.filterwarnings('ignore')

from text_fetcher import fetch_article

url = sys.argv[1] if len(sys.argv) > 1 else 'https://mp.weixin.qq.com/s/RwpfEYBgHqg-Q4FoHnUYrA'
result = fetch_article(url)
print(f"长度: {len(result)}")
print("---")
print(result[:800])
