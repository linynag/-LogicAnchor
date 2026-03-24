"""
AI 接口类 (预留)
定义输入输出结构，待后续接入 LLM 模型进行决策或分析。
"""

class AIInterface:
    def __init__(self):
        pass

    def analyze_portfolio(self, portfolio_data: dict) -> str:
        """
        输入当前持仓数据，输出分析建议
        :param portfolio_data: 包含各基金市值、成本、收益率的字典
        :return: 分析文本
        """
        # TODO: 接入大模型 API (如 DeepSeek, ChatGPT)
        return "暂未实现 AI 分析逻辑"

    def suggest_trade(self, fund_code: str, current_nav: float, history_data: list) -> dict:
        """
        对单只基金提供交易建议
        :return: {'action': 'buy/sell/hold', 'reason': '...', 'confidence': 0.9}
        """
        # TODO: 接入量化规则 + LLM 综合判断
        return {"action": "hold", "reason": "No model loaded", "confidence": 0.0}