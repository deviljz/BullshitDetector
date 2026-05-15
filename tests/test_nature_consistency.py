'''Cross-validate LLM-given bullshit_nature against deterministic bi/claim signals.

Regression: 20260515-020953-a15ff3 (Doraemon case) — LLM gave nature=属实
while 3 claims were all ✗ and bi=100. Header was internally contradictory.
'''
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))

from ai.providers.plan_mixin import _PlanExecuteMixin

resolve = _PlanExecuteMixin._resolve_nature


def _claim(fact_layer, importance='决定性', ctype='fact'):
    return {'fact_layer': fact_layer, 'claim_importance': importance, 'claim_type': ctype}


def test_override_when_llm_says_shu_shi_but_all_fake():
    # LLM says 属实 but 3 claims all ✗ → must override (reproduces Doraemon case)
    claims = [_claim('✗ 不存在'), _claim('✗ 不存在'), _claim('✗ 不存在')]
    result = resolve('属实', bi=100, claim_results=claims, title_logic={}, hype={})
    assert result == '事实错误', f'expected 事实错误, got {result}'


def test_override_when_llm_says_ji_ben_shu_shi_with_high_bi():
    # LLM says 基本属实 but bi=80 → must override
    claims = [_claim('✗ 不存在'), _claim('✗ 不存在')]
    result = resolve('基本属实', bi=80, claim_results=claims, title_logic={}, hype={})
    assert result == '事实错误'


def test_override_when_llm_says_zhen_shi_dan_li_pu_with_fake():
    # Any ✗ forbids 真实但离谱 (prompt forbids; double-check at code layer)
    claims = [_claim('✗ 不存在'), _claim('✓ 存在')]
    result = resolve('真实但离谱', bi=60, claim_results=claims, title_logic={}, hype={})
    assert result != '真实但离谱'


def test_keep_shu_shi_when_all_verified_and_low_bi():
    # All ✓ + low bi → keep LLM 属实
    claims = [_claim('✓ 存在'), _claim('✓ 存在')]
    result = resolve('属实', bi=5, claim_results=claims, title_logic={}, hype={})
    assert result == '属实'


def test_keep_ji_ben_shu_shi_when_compatible():
    # bi=20 + all ✓ → keep 基本属实
    claims = [_claim('✓ 存在')]
    result = resolve('基本属实', bi=20, claim_results=claims, title_logic={}, hype={})
    assert result == '基本属实'


def test_fallback_to_deterministic_when_llm_omits_nature():
    # LLM omits nature → fall through to _nature_from_inputs
    claims = [_claim('✗ 不存在')]
    result = resolve(None, bi=70, claim_results=claims, title_logic={}, hype={})
    assert result == '事实错误'
    result = resolve('', bi=70, claim_results=claims, title_logic={}, hype={})
    assert result == '事实错误'


def test_partial_failure_keeps_ju_bu_shi_shi():
    # 1 ✗ + 1 ✓ + LLM says 局部失实 → keep (non-positive nature; bi moderate)
    claims = [_claim('✗ 不存在'), _claim('✓ 存在')]
    result = resolve('局部失实', bi=55, claim_results=claims, title_logic={}, hype={})
    assert result == '局部失实'


def test_legacy_verdict_format_compatible():
    # Old format uses verdict instead of fact_layer; ✗ must still be detected
    claims = [{'verdict': '✗ 伪造', 'claim_importance': '决定性'}]
    result = resolve('属实', bi=90, claim_results=claims, title_logic={}, hype={})
    assert result == '事实错误'
