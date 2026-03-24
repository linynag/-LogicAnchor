"""
交易监听器
负责比对外部流水 CSV 和数据库内的交易历史，识别新交易并自动执行更新操作。
"""
import csv
import hashlib
from decimal import Decimal
from infrastructure.db_manager import DBManager
from adapters.akshare_adapter import AkShareAdapter
from services.calc_engine import CalcEngine

class TradeListener:
    def __init__(self, db: DBManager):
        self.db = db
        self.ak_adapter = AkShareAdapter()
        self.calc = CalcEngine()

    def generate_trade_id(self, date_str, code, amount, t_type):
        """生成唯一交易ID，防止重复导入"""
        raw = f"{date_str}_{code}_{amount}_{t_type}"
        return hashlib.md5(raw.encode('utf-8')).hexdigest()

    def process_csv(self, csv_path: str):
        """
        读取买入流水 CSV：
        期望格式：日期,代码,金额,类型
        例如：2026-03-24,000216,1000.00,买入
        """
        try:
            existing_trades = self.db.get_all_trades()
            existing_ids = {t['id'] for t in existing_trades}
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    date_str = row['日期'].strip()
                    code = row['代码'].strip()
                    amount_str = row['金额'].strip()
                    t_type = row['类型'].strip()

                    try:
                        amount = Decimal(amount_str)
                    except:
                        continue

                    trade_id = self.generate_trade_id(date_str, code, amount_str, t_type)
                    
                    # 检查是否已存在
                    if trade_id in existing_ids:
                        continue
                    existing_ids.add(trade_id)
                        
                    print(f"[*] 发现新交易: {date_str} {t_type} {code} 金额:{amount}")
                    self._process_single_trade(trade_id, date_str, code, amount, t_type)
        except FileNotFoundError:
            print(f"[*] 未找到输入文件 {csv_path}，跳过流水监听。")

    def _process_single_trade(self, trade_id, date_str, code, amount: Decimal, t_type):
        # 1. 获取净值
        nav, actual_date, is_dirty = self.ak_adapter.get_fund_nav(code, date_str)
        if nav is None:
            print(f"  [警告] 无法获取 {code} 在 {date_str} 的净值，交易挂起。")
            return
        self.db.upsert_nav(code, actual_date, nav, int(is_dirty))

        # 2. 计算份额
        if t_type == '买入':
            volume = self.calc.calc_shares(amount, nav)
        elif t_type == '卖出':
            # 这里简化处理：卖出时金额通常指代卖出本金或实际到账，若给出金额反推份额：
            volume = self.calc.calc_shares(amount, nav)
        else:
            return

        # 3. 记录流水
        self.db.insert_trade(trade_id, date_str, code, t_type, amount, nav, volume)

        # 4. 更新持仓 (读取老持仓 -> 计算新持仓 -> 写入)
        pos = self.db.get_position(code)
        if pos:
            fund_name = pos['fund_name']
            old_cost = Decimal(pos['initial_cost'])
            old_vol = Decimal(pos['hold_volume'])
            
            if t_type == '买入':
                new_cost = old_cost + amount
                new_vol = old_vol + volume
            elif t_type == '卖出':
                # 扣减成本的逻辑（等比例扣减）
                ratio = volume / old_vol if old_vol > Decimal('0') else Decimal('1')
                deduct_cost = old_cost * ratio
                new_cost = old_cost - deduct_cost
                new_vol = old_vol - volume
                if new_vol < Decimal('0'): new_vol = Decimal('0')
                if new_cost < Decimal('0'): new_cost = Decimal('0')

            # 这里更新的时候，nav_date 依然用最新的 actual_date 标记
            self.db.upsert_position(code, fund_name, new_cost, new_vol, nav, actual_date, int(is_dirty))
            print(f"  [成功] 更新 {fund_name} 持仓 -> 总成本: {new_cost:.2f}, 总份额: {new_vol:.2f}")
        else:
            print(f"  [警告] 数据库中没有 {code} 的初始仓位记录，请先初始化底座。")
