"""
核心计算引擎
所有关于成本、份额、收益的计算，必须严格使用 Decimal。
"""
from decimal import Decimal, getcontext

# 设置全局精度（一般资金计算留6-8位即可）
getcontext().prec = 10

class CalcEngine:
    
    @staticmethod
    def calc_shares(amount: Decimal, nav: Decimal, fee_rate: Decimal = Decimal('0')) -> Decimal:
        """
        计算买入份额（扣除手续费）
        :param amount: 买入金额
        :param nav: 买入日净值
        :param fee_rate: 费率，默认 0
        :return: 份额
        """
        if nav <= 0:
            return Decimal('0')
        net_amount = amount * (Decimal('1') - fee_rate)
        return net_amount / nav

    @staticmethod
    def calc_sell_amount(shares: Decimal, nav: Decimal, fee_rate: Decimal = Decimal('0')) -> Decimal:
        """
        计算卖出金额（扣除手续费）
        :param shares: 卖出份额
        :param nav: 卖出日净值
        :param fee_rate: 费率
        :return: 卖出所得金额
        """
        gross_amount = shares * nav
        return gross_amount * (Decimal('1') - fee_rate)

    @staticmethod
    def calc_current_value(hold_volume: Decimal, nav: Decimal) -> Decimal:
        """计算当前市值"""
        return hold_volume * nav

    @staticmethod
    def calc_profit(current_value: Decimal, initial_cost: Decimal) -> Decimal:
        """计算绝对收益"""
        return current_value - initial_cost

    @staticmethod
    def calc_profit_rate(current_value: Decimal, initial_cost: Decimal) -> Decimal:
        """计算收益率"""
        if initial_cost == Decimal('0'):
            return Decimal('0')
        return (current_value - initial_cost) / initial_cost