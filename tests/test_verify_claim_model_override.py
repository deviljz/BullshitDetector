"""单元测试：verify_claim 阶段的模型 override 钩子 (_verify_claim_model)。

混合模式下，planner 走 self._model，verify_claim 并行走 config.verify_claim_model（如 lite）。
"""

import sys
import pathlib
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from ai.providers.plan_mixin import _PlanExecuteMixin  # type: ignore


class _Stub(_PlanExecuteMixin):
    _model = "main-model"


def test_override_empty_falls_back_to_main_model():
    """config 无 verify_claim_model 字段时，verify 用主 model。"""
    with patch("config.manager.load", return_value={}):
        assert _Stub()._verify_claim_model() == "main-model"


def test_override_empty_string_falls_back():
    """空字符串 override 视为未设置。"""
    with patch("config.manager.load", return_value={"verify_claim_model": ""}):
        assert _Stub()._verify_claim_model() == "main-model"


def test_override_string_takes_effect():
    """非空 override 字符串生效。"""
    with patch("config.manager.load", return_value={"verify_claim_model": "lite-model"}):
        assert _Stub()._verify_claim_model() == "lite-model"


def test_override_survives_config_load_exception():
    """config 读取异常时，安全回落到主 model（不抛）。"""
    with patch("config.manager.load", side_effect=RuntimeError("disk full")):
        assert _Stub()._verify_claim_model() == "main-model"


def test_override_ignores_none_config():
    """config.manager.load 返回 None 时不报错。"""
    with patch("config.manager.load", return_value=None):
        assert _Stub()._verify_claim_model() == "main-model"
