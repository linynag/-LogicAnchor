"""
主入口文件
负责启动系统、执行流水监听，并展示当前资产看板。
"""
import sys
import datetime
from infrastructure.db_manager import DBManager
from core.trade_listener import TradeListener
from adapters.akshare_adapter import AkShareAdapter
from services.calc_engine import CalcEngine
from decimal import Decimal

def display_portfolio(db: DBManager, target_date: str):
    ak_adapter = AkShareAdapter()
    calc = CalcEngine()
    query_prev_date = (datetime.datetime.strptime(target_date, '%Y-%m-%d') - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    def get_nav(code: str, query_date: str, fallback_nav: Decimal, fallback_date: str):
        nav, actual_date, is_dirty = ak_adapter.get_fund_nav(code, query_date)
        if nav is None:
            cached = db.get_latest_nav(code, query_date)
            if cached:
                cached_date = cached['nav_date']
                dirty = (cached_date < query_date) or bool(cached['is_dirty'])
                return Decimal(cached['nav']), cached_date, dirty
            return fallback_nav, fallback_date, True
        stored = db.get_nav(code, actual_date)
        if stored:
            dirty = (actual_date < query_date) or bool(stored['is_dirty'])
            return Decimal(stored['nav']), stored['nav_date'], dirty
        db.upsert_nav(code, actual_date, nav, int(is_dirty))
        return nav, actual_date, bool(is_dirty)
    
    positions = db.get_all_positions()
    if not positions:
        print("当前没有任何持仓记录。")
        return

    print(f"\n========== LogicAnchor 资产看板 ({target_date}) ==========")
    print(f"{'基金名称':<25} {'持有份额':>10} {'持仓成本':>12} {'最新净值':>8} {'净值日':>10} {'当前市值':>12} {'昨日收益':>10} {'持有收益':>10} {'状态'}")
    print("-" * 100)

    trade_cache = {}

    def get_trade_maps(trade_date: str):
        cached = trade_cache.get(trade_date)
        if cached is not None:
            return cached

        trades = db.get_trades_by_date(trade_date)
        cashflow = {}
        volumes = {}
        for t in trades:
            code = t['fund_code']
            trade_type = t['trade_type']
            amount = Decimal(t['amount'])
            volume = Decimal(t['volume'])
            cf = cashflow.setdefault(code, {'buy': Decimal('0'), 'sell': Decimal('0')})
            vv = volumes.setdefault(code, {'buy': Decimal('0'), 'sell': Decimal('0')})
            if trade_type == '买入':
                cf['buy'] += amount
                vv['buy'] += volume
            elif trade_type == '卖出':
                cf['sell'] += amount
                vv['sell'] += volume

        trade_cache[trade_date] = (cashflow, volumes)
        return cashflow, volumes

    total_value = Decimal('0')
    total_cost = Decimal('0')
    total_profit = Decimal('0')
    total_day_profit = Decimal('0')
    missing_day_profit = 0
    any_dirty = False

    for pos in positions:
        code = pos['fund_code']
        name = pos['fund_name']
        end_vol = Decimal(pos['hold_volume'])
        cost = Decimal(pos['initial_cost'])
        
        fallback_nav = Decimal(pos['last_nav'])
        fallback_date = pos['nav_date']
        today_nav, today_actual_date, today_is_dirty = get_nav(code, target_date, fallback_nav, fallback_date)

        prev_for_nav = (datetime.datetime.strptime(today_actual_date, '%Y-%m-%d') - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        prev_nav, prev_actual_date, prev_is_dirty = get_nav(code, prev_for_nav, fallback_nav, fallback_date)

        cashflow, volumes = get_trade_maps(today_actual_date)
        cf = cashflow.get(code, {'buy': Decimal('0'), 'sell': Decimal('0')})
        vv = volumes.get(code, {'buy': Decimal('0'), 'sell': Decimal('0')})
        begin_vol = end_vol - vv['buy'] + vv['sell']
        if begin_vol < Decimal('0'):
            begin_vol = Decimal('0')

        end_value = calc.calc_current_value(end_vol, today_nav)
        begin_value = calc.calc_current_value(begin_vol, prev_nav)
        day_profit = None
        allow_show = today_actual_date == target_date or today_actual_date == query_prev_date
        if allow_show and today_actual_date > prev_actual_date:
            day_profit = end_value + cf['sell'] - (begin_value + cf['buy'])
        hold_profit = calc.calc_profit(end_value, cost)
        
        total_value += end_value
        total_cost += cost
        total_profit += hold_profit
        if day_profit is None:
            missing_day_profit += 1
        else:
            total_day_profit += day_profit
        any_dirty = any_dirty or bool(today_is_dirty)
        
        status_str = f"⚠️ 数据延迟(净值日:{today_actual_date})" if today_is_dirty else f"✅ 正常(净值日:{today_actual_date})"

        # 中文对齐补齐空格
        name_str = name + chr(12288) * (15 - len(name))
        day_profit_str = "--" if day_profit is None else f"{day_profit:.2f}"
        print(f"{name_str} {end_vol:>10.2f} {cost:>12.2f} {today_nav:>8.4f} {today_actual_date:>10} {end_value:>12.2f} {day_profit_str:>10} {hold_profit:>10.2f} {status_str}")

    print("-" * 100)
    print(f"总计持仓成本: {total_cost:.2f} 元")
    print(f"总计当前市值: {total_value:.2f} 元")
    if missing_day_profit == 0:
        print(f"总计昨日收益: {total_day_profit:.2f} 元")
    else:
        print(f"总计昨日收益: {total_day_profit:.2f} 元（{missing_day_profit}只基金暂不可算）")
    print(f"总计持有收益: {total_profit:.2f} 元")
    print("===============================================================\n")

    db.upsert_daily_metrics(
        target_date,
        total_cost,
        total_value,
        None if missing_day_profit > 0 else total_day_profit,
        total_profit,
        1 if any_dirty else 0,
    )

def main():
    db = DBManager()
    
    # 1. 启动监听器，读取新流水
    listener = TradeListener(db)
    # 假设你每天维护这个 CSV
    csv_path = 'data/交易流水.csv' 
    listener.process_csv(csv_path)

    # 2. 展示当前看板
    today_str = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now().strftime('%Y-%m-%d')
    
    display_portfolio(db, today_str)

    db.close()

if __name__ == '__main__':
    main()
