"""
系统初始锚点脚本
使用 2026-03-20 为系统起点，结合您提供的 `目前仓位.txt` 绝对数据建立基准。
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
from decimal import Decimal
from infrastructure.db_manager import DBManager
from adapters.akshare_adapter import AkShareAdapter

# 基金代码映射 (从您的目前仓位.txt解析)
FUND_MAP = {
    '华安黄金ETF联接C': '000216',
    '易方达黄金ETF联接C': '000307',
    '嘉实中证半导体产': '014855',
    '嘉实中证半导体产业指数增强C': '014855',
    '嘉实中证半导体产业指数增强 C': '014855',
    '广发纳斯达克100ETF联接(QDI)C': '008763',
    '华宝纳斯达克精选股票(QDI)C': '017437',
    '天弘纳斯达克100指数(QDI)C': '018044',
    '南方纳斯达克100指数(QDII)C': '160140',
    '安信创新先锋混合C': '010238',
    '天弘纳斯达克100指数(QDI)A': '018043',
    '华宝纳斯达克精选股票(QDI)A': '017436',
    '南方有色金属ETF联接C': '004433',
}

def _norm_name(name: str) -> str:
    return re.sub(r'\s+', '', name or '')

def _parse_snapshot(snapshot_path: str, target_date: str):
    lines = open(snapshot_path, 'r', encoding='utf-8').read().splitlines()
    in_section = False
    rows = []
    for line in lines:
        line = line.strip()
        if not line:
            if in_section and rows:
                break
            continue
        if line.startswith(f'{target_date}('):
            in_section = True
            continue
        if re.match(r'^\d{4}-\d{2}-\d{2}\(', line) and in_section:
            break
        if not in_section:
            continue
        if line.startswith('名称'):
            continue
        if '\t' not in line:
            continue
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        name = parts[0]
        amount = Decimal(parts[1].replace(',', '').replace('+', ''))
        hold_profit = Decimal(parts[2].replace(',', '').replace('+', ''))
        rows.append({'fund_name': name, 'amount': amount, 'hold_profit': hold_profit})
    return rows

def main():
    target_date = '2026-03-20'
    db = DBManager()
    ak_adapter = AkShareAdapter()
    
    # 清空旧数据 (重置底座)
    cursor = db.conn.cursor()
    cursor.execute('DELETE FROM positions')
    cursor.execute('DELETE FROM trade_history')
    db.conn.commit()
    
    print(f"开始根据 {target_date} 数据初始化最新仓位底座...")
    
    norm_map = {_norm_name(k): v for k, v in FUND_MAP.items()}
    snapshot_rows = _parse_snapshot('目前仓位.txt', target_date)
    if not snapshot_rows:
        snapshot_rows = [
            {'fund_name': '华安黄金ETF联接C', 'amount': Decimal('17479.41'), 'hold_profit': Decimal('629.41')},
            {'fund_name': '易方达黄金ETF联接C', 'amount': Decimal('19161.75'), 'hold_profit': Decimal('-838.25')},
            {'fund_name': '嘉实中证半导体产', 'amount': Decimal('17996.31'), 'hold_profit': Decimal('-2003.69')},
            {'fund_name': '广发纳斯达克100ETF联接(QDI)C', 'amount': Decimal('838.15'), 'hold_profit': Decimal('-51.85')},
            {'fund_name': '华宝纳斯达克精选股票(QDI)C', 'amount': Decimal('8509.32'), 'hold_profit': Decimal('-710.68')},
            {'fund_name': '天弘纳斯达克100指数(QDI)C', 'amount': Decimal('1313.49'), 'hold_profit': Decimal('-86.51')},
            {'fund_name': '南方纳斯达克100指数(QDII)C', 'amount': Decimal('2873.36'), 'hold_profit': Decimal('-176.64')},
            {'fund_name': '安信创新先锋混合C', 'amount': Decimal('7661.15'), 'hold_profit': Decimal('167.12')},
            {'fund_name': '天弘纳斯达克100指数(QDI)A', 'amount': Decimal('93.82'), 'hold_profit': Decimal('-6.18')},
            {'fund_name': '华宝纳斯达克精选股票(QDI)A', 'amount': Decimal('2348.12'), 'hold_profit': Decimal('-151.88')},
            {'fund_name': '南方有色金属ETF联接C', 'amount': Decimal('16384.89'), 'hold_profit': Decimal('-3615.11')},
        ]
        print("⚠️ 未能从 目前仓位.txt 解析到目标日期快照，改用内置快照数据初始化。")

    for row in snapshot_rows:
        name = row['fund_name']
        code = norm_map.get(_norm_name(name))
        if not code:
            print(f"⚠️ 找不到基金代码映射: {name}")
            continue

        amount = row['amount']
        hold_profit = row['hold_profit']
        initial_cost = amount - hold_profit

        nav, actual_date, is_dirty = ak_adapter.get_fund_nav(code, target_date)
        if nav is None or nav == Decimal('0'):
            print(f"❌ 无法获取 {name} ({code}) 在 {target_date} 的净值，跳过。")
            continue

        snapshot_0323_amount = {
            '000216': Decimal('15642.86'),
            '000307': Decimal('17080.23'),
        }
        snapshot_0323_buy = {
            '000216': Decimal('50.00'),
        }
        if code in snapshot_0323_amount:
            nav23, actual23, dirty23 = ak_adapter.get_fund_nav(code, '2026-03-23')
            if nav23 is not None and nav23 != Decimal('0'):
                amount23 = snapshot_0323_amount[code]
                buy23 = snapshot_0323_buy.get(code, Decimal('0'))
                if amount23 > buy23:
                    implied_nav = amount * nav23 / (amount23 - buy23)
                    nav = implied_nav
                    actual_date = target_date
                    is_dirty = False

        hold_volume = amount / nav
        db.upsert_position(code, name, initial_cost, hold_volume, nav, actual_date, int(is_dirty))
        db.upsert_nav(code, actual_date, nav, int(is_dirty))
        print(f"✅ {name} 初始基准已建立 -> 成本:{initial_cost} 份额:{hold_volume}")

    db.close()
    print("\n🎉 系统底座数据初始化完成，此后每日运行 [运行.py] 即可！")

if __name__ == '__main__':
    main()
