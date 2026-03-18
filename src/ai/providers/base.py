"""BaseLLMProvider —— 所有模型 Provider 的统一抽象接口"""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """
    策略模式基类。上层业务逻辑只依赖此接口，不关心底层是哪家模型。

    所有方法返回 (result_dict, token_dict) 元组：
        result_dict: 标准化结果字典
        token_dict:  {"model": str, "input": int, "output": int}
    """

    @abstractmethod
    def analyze(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        """分析截图内容的真实性。images 为 base64 字符串列表。"""
        ...

    @abstractmethod
    def summarize(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        """截图内容一键总结。"""
        ...

    @abstractmethod
    def explain(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        """截图内容一键解释。"""
        ...

    @abstractmethod
    def source_find(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        """识别截图来自哪部作品。"""
        ...

    @abstractmethod
    def follow_up(self, context_text: str, history: list[dict], question: str, mode: str = "analyze") -> tuple[str, dict]:
        """追问对话。返回 (回复文本, token_dict)。"""
        ...
