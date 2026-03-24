"""
数据库交互层，负责 SQLite 数据库的初始化和读写操作。
所有金额/份额在数据库中以 TEXT 类型存储，以保证 Decimal 的精度不丢失。
"""
import sqlite3
import os
from decimal import Decimal

DB_PATH = 'data/logic_anchor.db'

class DBManager:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        cursor = self.conn.cursor()
        # 持仓表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                fund_code TEXT PRIMARY KEY,
                fund_name TEXT NOT NULL,
                initial_cost TEXT NOT NULL,
                hold_volume TEXT NOT NULL,
                last_nav TEXT NOT NULL,
                nav_date TEXT NOT NULL,
                is_dirty INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 交易流水表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_history (
                id TEXT PRIMARY KEY,
                trade_date TEXT NOT NULL,
                fund_code TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                amount TEXT NOT NULL,
                nav TEXT NOT NULL,
                volume TEXT NOT NULL,
                status TEXT DEFAULT 'SUCCESS',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                trade_date TEXT NOT NULL,
                fund_code TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                amount TEXT NOT NULL,
                nav TEXT NOT NULL,
                volume TEXT NOT NULL,
                status TEXT DEFAULT 'SUCCESS',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_nav (
                fund_code TEXT NOT NULL,
                nav_date TEXT NOT NULL,
                nav TEXT NOT NULL,
                is_dirty INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (fund_code, nav_date)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_metrics (
                metric_date TEXT PRIMARY KEY,
                total_cost TEXT NOT NULL,
                total_value TEXT NOT NULL,
                day_profit TEXT,
                hold_profit TEXT,
                is_dirty INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO transactions (id, trade_date, fund_code, trade_type, amount, nav, volume, status, created_at)
            SELECT id, trade_date, fund_code, trade_type, amount, nav, volume, status, created_at
            FROM trade_history
        ''')
        self.conn.commit()

    def get_all_positions(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM positions')
        return cursor.fetchall()

    def get_position(self, fund_code):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM positions WHERE fund_code = ?', (fund_code,))
        return cursor.fetchone()

    def upsert_position(self, fund_code, fund_name, initial_cost: Decimal, hold_volume: Decimal, last_nav: Decimal, nav_date: str, is_dirty: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO positions (fund_code, fund_name, initial_cost, hold_volume, last_nav, nav_date, is_dirty, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(fund_code) DO UPDATE SET
                initial_cost=excluded.initial_cost,
                hold_volume=excluded.hold_volume,
                last_nav=excluded.last_nav,
                nav_date=excluded.nav_date,
                is_dirty=excluded.is_dirty,
                updated_at=CURRENT_TIMESTAMP
        ''', (fund_code, fund_name, str(initial_cost), str(hold_volume), str(last_nav), nav_date, is_dirty))
        self.conn.commit()

    def get_all_trades(self):
        return self.get_all_transactions()

    def get_all_transactions(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM transactions')
        return cursor.fetchall()

    def get_trades_by_date(self, trade_date: str):
        return self.get_transactions_by_date(trade_date)

    def get_transactions_by_date(self, trade_date: str):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM transactions WHERE trade_date = ?', (trade_date,))
        return cursor.fetchall()

    def get_nav(self, fund_code: str, nav_date: str):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM daily_nav WHERE fund_code = ? AND nav_date = ?', (fund_code, nav_date))
        return cursor.fetchone()

    def get_latest_nav(self, fund_code: str, query_date: str):
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT * FROM daily_nav WHERE fund_code = ? AND nav_date <= ? ORDER BY nav_date DESC LIMIT 1',
            (fund_code, query_date),
        )
        return cursor.fetchone()

    def upsert_nav(self, fund_code: str, nav_date: str, nav: Decimal, is_dirty: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO daily_nav (fund_code, nav_date, nav, is_dirty, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(fund_code, nav_date) DO UPDATE SET
                nav=excluded.nav,
                is_dirty=excluded.is_dirty,
                updated_at=CURRENT_TIMESTAMP
        ''', (fund_code, nav_date, str(nav), int(is_dirty)))
        self.conn.commit()

    def insert_trade(self, trade_id, trade_date, fund_code, trade_type, amount: Decimal, nav: Decimal, volume: Decimal):
        return self.insert_transaction(trade_id, trade_date, fund_code, trade_type, amount, nav, volume)

    def insert_transaction(self, trade_id, trade_date, fund_code, trade_type, amount: Decimal, nav: Decimal, volume: Decimal):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO transactions (id, trade_date, fund_code, trade_type, amount, nav, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (trade_id, trade_date, fund_code, trade_type, str(amount), str(nav), str(volume)))
        self.conn.commit()

    def upsert_daily_metrics(self, metric_date: str, total_cost: Decimal, total_value: Decimal, day_profit, hold_profit, is_dirty: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO daily_metrics (metric_date, total_cost, total_value, day_profit, hold_profit, is_dirty, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(metric_date) DO UPDATE SET
                total_cost=excluded.total_cost,
                total_value=excluded.total_value,
                day_profit=excluded.day_profit,
                hold_profit=excluded.hold_profit,
                is_dirty=excluded.is_dirty,
                updated_at=CURRENT_TIMESTAMP
        ''', (metric_date, str(total_cost), str(total_value), None if day_profit is None else str(day_profit), None if hold_profit is None else str(hold_profit), int(is_dirty)))
        self.conn.commit()

    def close(self):
        self.conn.close()
