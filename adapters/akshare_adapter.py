"""
AkShare 适配器
封装数据获取逻辑，处理 QDII 基金延迟和非交易日等问题。
"""
import akshare as ak
from decimal import Decimal
import warnings
import time
warnings.filterwarnings('ignore')

class AkShareAdapter:
    @staticmethod
    def get_fund_nav(fund_code: str, target_date_str: str, max_retries: int = 3, base_sleep_seconds: float = 0.6):
        """
        获取指定日期的基金净值
        :param fund_code: 基金代码
        :param target_date_str: 目标日期 YYYY-MM-DD
        :return: (nav: Decimal, actual_date: str, is_dirty: bool)
        """
        last_error = None
        for attempt in range(max(1, int(max_retries))):
            try:
                df = ak.fund_open_fund_info_em(fund_code, indicator="单位净值走势")
                if df is None or df.empty:
                    raise RuntimeError("AkShare 返回空数据")

                df['净值日期'] = df['净值日期'].astype(str)
                df_before = df[df['净值日期'] <= target_date_str].sort_values(by='净值日期', ascending=False)

                if df_before.empty:
                    return None, None, True

                actual_date = df_before.iloc[0]['净值日期']
                nav = Decimal(str(df_before.iloc[0]['单位净值']))
                is_dirty = actual_date < target_date_str

                return nav, actual_date, is_dirty
            except Exception as e:
                last_error = e
                if attempt < max(1, int(max_retries)) - 1:
                    sleep_s = float(base_sleep_seconds) * (2 ** attempt)
                    time.sleep(sleep_s)
                    continue
                print(f"[错误] 获取基金 {fund_code} 净值失败: {last_error}")
                return None, None, True
