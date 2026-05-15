'''Cross-validate LLM-given verdict_text against bi/claim consensus.

Regression: 20260515-034810-8639aa (Doraemon case) — claim 1 was ✓ "翻译不对属实"
but LLM wrote verdict_text="翻译完全忠实于原著，所谓翻译不对的说法并无事实依据"
(reversed the claim stance). bi=9 (low, implies article 属实) + verdict_text
denying the article = contradiction.
'''
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))

from ai.providers.plan_mixin import _PlanExecuteMixin

resolve = _PlanExecuteMixin._resolve_verdict_text


def _claim(fact_layer, importance='决定性', ctype='fact', claim_text=''):
    return {
        'fact_layer': fact_layer,
        'claim_importance': importance,
        'claim_type': ctype,
        'claim': claim_text,
    }


def test_low_bi_with_deny_phrase_is_overridden():
    # Regression case: bi=9 (article 属实) + verdict_text containing 并无事实依据
    claims = [_claim('✓ 存在'), _claim('? 无法核实', importance='重要', ctype='narrative')]
    bad = '经核查，所谓翻译不对的说法并无事实依据。'
    result = resolve(bad, nature='属实', bi=9, claim_results=claims)
    assert result != bad, '应被覆盖'
    assert '并无事实依据' not in result, '覆盖后不应含否认短语'
    assert '属实' in result or '成立' in result, '覆盖后应表达正向立场'


def test_high_bi_with_affirm_phrase_is_overridden():
    # bi=80 (article 虚假) + verdict_text says "完全属实"
    claims = [_claim('✗ 不存在'), _claim('✗ 不存在')]
    bad = '经核查，文章内容完全属实。'
    result = resolve(bad, nature='事实错误', bi=80, claim_results=claims)
    assert result != bad
    assert '完全属实' not in result


def test_normal_verdict_passes_through():
    # bi=10 + verdict aligned (no deny phrases) → keep
    claims = [_claim('✓ 存在')]
    good = '经核查，文章所述事实基本成立。'
    result = resolve(good, nature='属实', bi=10, claim_results=claims)
    assert result == good


def test_empty_verdict_text_uses_template():
    # LLM omitted verdict_text → build from template
    claims = [_claim('✗ 不存在'), _claim('✗ 不存在')]
    result = resolve('', nature='事实错误', bi=80, claim_results=claims)
    assert result, '不能返回空'
    assert '不成立' in result or '失实' in result or '问题' in result


def test_mid_bi_with_deny_phrase_not_overridden():
    # bi=40 灰色区，不强制覆盖
    claims = [_claim('? 无法核实'), _claim('? 无法核实')]
    text = '部分细节并无确证。'
    result = resolve(text, nature='局部失实', bi=40, claim_results=claims)
    # 中间区允许 LLM 自由表达，不强制覆盖
    assert result == text


def test_high_bi_normal_verdict_passes_through():
    # bi=80 + verdict says 事实错误 → keep
    claims = [_claim('✗ 不存在')]
    good = '经核查，文章核心事实存在重大错误。'
    result = resolve(good, nature='事实错误', bi=80, claim_results=claims)
    assert result == good


def test_template_includes_claim_counts():
    # Template should reflect claim distribution
    claims = [_claim('✗ 不存在'), _claim('✗ 不存在'), _claim('✓ 存在')]
    result = resolve('', nature='局部失实', bi=60, claim_results=claims)
    assert '2' in result, 'should mention fake count'


def test_legacy_verdict_format():
    # Old format claim uses 'verdict' instead of 'fact_layer'
    claims = [{'verdict': '✓ 存在', 'claim_importance': '决定性'}]
    bad = '所谓声明并无事实依据。'
    result = resolve(bad, nature='属实', bi=5, claim_results=claims)
    assert result != bad
