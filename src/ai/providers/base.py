"""BaseLLMProvider —— 所有模型 Provider 的统一抽象接口"""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """
    策略模式基类。上层业务逻辑只依赖此接口，不关心底层是哪家模型。

    子类必须实现 analyze()，输入 base64 编码的图片，
    输出包含以下字段的标准化字典：
        is_fake, confidence, bullshit_index, truth_index,
        toxic_review, flaw_analysis, claims, tactics
    可选：error（分析失败时），_search_log（调试用）
    """

    @abstractmethod
    def analyze(self, image_base64: str) -> dict:
        """
        分析截图内容的真实性。

        Args:
            image_base64: PNG/JPEG 图片的 base64 字符串（不含 data:image 前缀）

        Returns:
            标准化结果字典，字段见类文档
        """
        ...
