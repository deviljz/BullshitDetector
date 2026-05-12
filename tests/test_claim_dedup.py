"""claim 去重 helper 单元测试

dedup 双信号判定：
- bigram 相似度 ≥ 0.65 → 措辞接近的同义改写
- bigram ≥ 0.30 且共享 ≥ 2 个 3+位数字 → 同事实不同措辞
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai.providers.plan_mixin import _claim_similarity, _is_duplicate_claim, _shared_numbers


def test_identical_claims_high_similarity():
    a = "斯塔夫里阿诺斯《全球通史》中文版将中国文明史从3500年改为5000年。"
    assert _claim_similarity(a, a) >= 0.99


def test_high_bigram_overlap_detected():
    # 措辞接近，bigram >= 0.65
    a = "斯塔夫里阿诺斯《全球通史》中文版将中国文明史从3500年改为5000年。"
    b = "斯塔夫里阿诺斯《全球通史》中文版（如北京大学出版社版）中关于中国文明起源的描述与英文原版存在显著差异，如将3500年改为5000年。"
    assert _is_duplicate_claim(a, [b])


def test_shared_numbers_low_bigram_detected():
    # 同事实不同措辞，bigram 低但共享 3500 + 5000
    a = "著名的《全球通史》，很多人都知道原文的3500年被改成5000年。"
    b = "斯塔夫里阿诺斯《全球通史》中文版将中国文明史从3500年改为5000年。"
    assert _shared_numbers(a, b) >= 2
    assert _is_duplicate_claim(a, [b])


def test_same_subject_different_facts_not_duplicate():
    # 都是关于全球通史中文版，但事实不同；无共同数字
    a = "《全球通史》中文版改了年份。"
    b = "《全球通史》中文版增加了几万字关于中国古代的内容。"
    # bigram 较高（0.6 左右），但无共享数字 → 不判重
    assert not _is_duplicate_claim(a, [b])


def test_unrelated_claims_not_duplicate():
    a = "《全球通史》中文版改了年份。"
    b = "京东被罚 1000 万元因数据合规问题。"
    assert not _is_duplicate_claim(a, [b])


def test_dedup_against_list_with_numbers():
    existing = [
        "《全球通史》中文版将3500年改为5000年。",
        "中文版加了一张表格列出中国领先技术。",
    ]
    # 同事实 + 共享数字 → 判重
    assert _is_duplicate_claim("中文版把 3500 年改为了 5000 年", existing)
    # 不同事实，无共享数字 → 不重
    assert not _is_duplicate_claim("中文版增加了几万字关于中国的内容", existing)


def test_empty_claim_handled():
    assert _claim_similarity("", "abc") == 0.0
    assert not _is_duplicate_claim("", ["something"])


def test_shared_numbers_helper():
    assert _shared_numbers("3500年改成5000年", "原文3500被改为5000") == 2
    assert _shared_numbers("3500年", "5000年") == 0
    assert _shared_numbers("无数字", "也无数字") == 0
