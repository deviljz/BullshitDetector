'''Test claim polarity (supports_article vs refutes_article).

A refutes-type claim with verdict=✓ means "the rebuttal stands → article premise broken",
so it should be penalized as if the article's own claim was ✗.

Regression: 20260515-040111-84ec8b (Doraemon case) — claim 3 was a refutes-type
claim ("image is not from Doraemon original, it's fan-made") and got ✓,
but bi was 20 (basic_可信) instead of being high (事实错误).
'''
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))

from ai.providers.plan_mixin import _claim_penalty_ratio, _PlanExecuteMixin


def _claim(fact_layer, polarity=None, importance='决定性', ctype='fact'):
    c = {'fact_layer': fact_layer, 'claim_importance': importance, 'claim_type': ctype}
    if polarity is not None:
        c['polarity'] = polarity
    return c


# ---------- _claim_penalty_ratio polarity tests ----------

def test_supports_verified_zero_penalty():
    # supports + ✓ → article assertion stands → no penalty (status quo)
    assert _claim_penalty_ratio(_claim('✓ 存在', polarity='supports_article')) == 0.0


def test_supports_fake_full_penalty():
    # supports + ✗ → article assertion fake → full penalty (status quo)
    assert _claim_penalty_ratio(_claim('✗ 不存在', polarity='supports_article')) == 1.0


def test_refutes_verified_full_penalty():
    # refutes + ✓ → rebuttal stands → article premise broken → full penalty
    assert _claim_penalty_ratio(_claim('✓ 存在', polarity='refutes_article')) == 1.0


def test_refutes_fake_zero_penalty():
    # refutes + ✗ → rebuttal fails → article premise intact → no penalty
    assert _claim_penalty_ratio(_claim('✗ 不存在', polarity='refutes_article')) == 0.0


def test_refutes_uncertain_mid_penalty():
    # refutes + ? → rebuttal unverifiable → mid (same as supports + ?)
    r = _claim_penalty_ratio(_claim('? 无法核实', polarity='refutes_article'))
    assert 0.2 < r < 0.4


def test_default_polarity_is_supports():
    # No polarity field → behave as supports_article (backward compatibility)
    assert _claim_penalty_ratio(_claim('✓ 存在')) == 0.0
    assert _claim_penalty_ratio(_claim('✗ 不存在')) == 1.0


def test_legacy_verdict_format_treated_as_supports():
    # Legacy claim (no fact_layer, has verdict) → supports default
    assert _claim_penalty_ratio({'verdict': '✓ 存在'}) == 0.0
    assert _claim_penalty_ratio({'verdict': '✗ 伪造'}) == 1.0


# ---------- _calculate_bi end-to-end with polarity ----------

def test_doraemon_case_bi_should_be_high():
    # Reproduce 20260515-040111-84ec8b after polarity introduced
    cv = [
        _claim('? 无法核实', polarity='supports_article'),  # claim 1
        _claim('? 无法核实', polarity='supports_article', importance='重要', ctype='narrative'),  # claim 2
        _claim('✓ 存在', polarity='refutes_article'),  # claim 3 — image NOT from Doraemon
    ]
    bi, risk = _PlanExecuteMixin._calculate_bi(cv, {}, {})
    assert bi >= 56, f'expected bi ≥ 56 (high warning), got {bi}'
    assert '高度' in risk or '极度' in risk, f'expected high-risk label, got {risk}'


def test_nature_from_inputs_refutes_verified_counted_as_fake():
    # refutes + ✓ should map to 事实错误 path (treated like a fake claim)
    cv = [_claim('✓ 存在', polarity='refutes_article')]
    nature = _PlanExecuteMixin._nature_from_inputs(70, cv, {}, {})
    assert nature in {'事实错误', '局部失实'}, f'got {nature}'


def test_nature_refutes_fake_counted_as_verified():
    # refutes + ✗ should map to 属实/基本属实 (rebuttal failed → article intact)
    cv = [_claim('✗ 不存在', polarity='refutes_article')]
    nature = _PlanExecuteMixin._nature_from_inputs(0, cv, {}, {})
    assert nature in {'属实', '基本属实'}, f'got {nature}'


# ---------- _resolve_nature with polarity ----------

def test_resolve_nature_refutes_verified_forces_override():
    # LLM gave nature='属实' but refutes + ✓ ⇒ should override to 事实错误-like
    cv = [_claim('✓ 存在', polarity='refutes_article'),
          _claim('✓ 存在', polarity='refutes_article')]
    bi, _ = _PlanExecuteMixin._calculate_bi(cv, {}, {})
    result = _PlanExecuteMixin._resolve_nature('属实', bi, cv, {}, {})
    assert result != '属实', f'expected override, got {result}'
