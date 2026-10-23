"""
yfinance 行情数据源适配器 — 美/港/A 三市统一取数
支持级别: 日线/周线/月线/分钟级(1m,5m,15m,30m,60m)
代码格式(yfinance 约定):
    美股:   AAPL / MSFT / SPY / QQQ / NVDA
    港股:   0700.HK / 9988.HK / 0005.HK
    A股:    600519.SS(沪) / 000001.SZ(深)
自动复权处理; 市场归属由 Common.market_capability.detect_market 按后缀路由。
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, date
from typing import Iterable, Optional

from Common.CEnum import AUTYPE, DATA_FIELD, KL_TYPE
from Common.CTime import CTime
from KLine.KLineUnit import CKLine_Unit

from .CommonStockAPI import CCommonStockApi


# yfinance interval 映射
INTERVAL_MAP = {
    KL_TYPE.K_1M: "1m",
    KL_TYPE.K_5M: "5m",
    KL_TYPE.K_15M: "15m",
    KL_TYPE.K_30M: "30m",
    KL_TYPE.K_60M: "60m",
    KL_TYPE.K_DAY: "1d",
    KL_TYPE.K_WEEK: "1wk",
    KL_TYPE.K_MON: "1mo",
}

# yfinance period 映射 (当未指定begin_date时使用的回溯期)
PERIOD_MAP = {
    KL_TYPE.K_1M: "7d",
    KL_TYPE.K_5M: "60d",
    KL_TYPE.K_15M: "60d",
    KL_TYPE.K_30M: "60d",
    KL_TYPE.K_60M: "730d",
    KL_TYPE.K_DAY: "max",
    KL_TYPE.K_WEEK: "max",
    KL_TYPE.K_MON: "max",
}


class CUSStockApi(CCommonStockApi):
    """
    美股数据源 (yfinance)
    code 格式: 美股ticker, 如 "AAPL", "TSLA", "SPY", "QQQ"
    """
    is_connect = None

    def __init__(self, code, k_type=KL_TYPE.K_DAY, begin_date=None, end_date=None, autype=AUTYPE.QFQ):
        super(CUSStockApi, self).__init__(code, k_type, begin_date, end_date, autype)

    def get_kl_data(self) -> Iterable[CKLine_Unit]:
        interval = INTERVAL_MAP.get(self.k_type)
        if interval is None:
            raise Exception(f"Unsupported k_type for US stock: {self.k_type}")

        # 构建 yfinance 下载参数
        kwargs = {
            "interval": interval,
            "auto_adjust": False,  # 手动处理复权
        }

        if self.begin_date:
            kwargs["start"] = self.begin_date
        else:
            kwargs["period"] = PERIOD_MAP.get(self.k_type, "max")

        if self.end_date:
            kwargs["end"] = self.end_date

        # 下载数据
        ticker = yf.Ticker(self.code)
        df = ticker.history(**kwargs)

        if df.empty:
            raise Exception(f"No data returned for {self.code} ({self.k_type})")

        # 复权处理
        if self.autype == AUTYPE.QFQ:
            # 前复权: yfinance 的 Adj Close 已经是对应除权后的价格
            # 用 adjclose 比例调整 open/high/low/close
            # 注意: yfinance 服务端 Adj Close 存在 ~1e-6 级抖动(同一标的不同请求会返回
            # 略有差异的缓存版本), 噪声注入复权价后会在K线合并的等值比较上翻转笔/中枢结构,
            # 导致同一命令多次运行结果不同(000001.SZ 实测 7 次 7 个结果)。
            # 舍入到 0.001(远低于任何市场最小报价单位)消除抖动, 保证可重复性。
            if "Adj Close" in df.columns:
                ratio = df["Adj Close"] / df["Close"]
                df["Open"] = (df["Open"] * ratio).round(3)
                df["High"] = (df["High"] * ratio).round(3)
                df["Low"] = (df["Low"] * ratio).round(3)
                df["Close"] = (df["Close"] * ratio).round(3)
            elif "Dividends" in df.columns:
                # 新版yfinance字段变化: 无 Adj Close 时拒绝静默跳过(避免"看似复权实则未复权")
                raise RuntimeError(
                    f"{self.code}: yfinance 未返回 Adj Close 列, 无法做前复权; "
                    "请升级/降级 yfinance 或改用不复权(--autype none)或 BaoStock 数据源")
        elif self.autype == AUTYPE.NONE:
            pass  # 不复权，使用原始价格
        elif self.autype == AUTYPE.HFQ:
            # yfinance history() 不直接提供后复权价; 明确报错而非静默返回未复权价
            raise RuntimeError(
                f"{self.code}: yfinance 数据源不支持后复权(HFQ); "
                "请改用前复权(--autype qfq)、不复权(--autype none), 或换用 BaoStock 数据源")

        # 逐行生成 CKLine_Unit
        for idx, row in df.iterrows():
            klu = self._parse_row(idx, row)
            if klu is not None:
                yield klu

    def _parse_row(self, idx, row) -> Optional[CKLine_Unit]:
        """解析单行数据为 CKLine_Unit"""
        try:
            # 解析时间
            if isinstance(idx, pd.Timestamp):
                ts = idx.to_pydatetime()
            elif isinstance(idx, datetime):
                ts = idx
            else:
                ts = pd.Timestamp(idx).to_pydatetime()

            time_obj = CTime(ts.year, ts.month, ts.day, ts.hour, ts.minute)

            # 提取OHLCV
            open_p = float(row.get("Open", row.get("open", 0)))
            high_p = float(row.get("High", row.get("high", 0)))
            low_p = float(row.get("Low", row.get("low", 0)))
            close_p = float(row.get("Close", row.get("close", 0)))
            volume = float(row.get("Volume", row.get("volume", 0)))

            # 跳过无效数据
            if open_p == 0 and close_p == 0:
                return None

            data_dict = {
                DATA_FIELD.FIELD_TIME: time_obj,
                DATA_FIELD.FIELD_OPEN: open_p,
                DATA_FIELD.FIELD_HIGH: high_p,
                DATA_FIELD.FIELD_LOW: low_p,
                DATA_FIELD.FIELD_CLOSE: close_p,
                DATA_FIELD.FIELD_VOLUME: volume,
            }

            return CKLine_Unit(data_dict, autofix=True)

        except Exception as e:
            return None

    def SetBasciInfo(self):
        """获取股票基本信息"""
        try:
            ticker = yf.Ticker(self.code)
            info = ticker.info
            self.name = info.get("shortName", self.code)
            self.is_stock = info.get("quoteType", "EQUITY") in ("EQUITY", "ETF", "MUTUALFUND")
        except Exception:
            self.name = self.code
            self.is_stock = True

    @classmethod
    def do_init(cls):
        pass  # yfinance 无需显式登录

    @classmethod
    def do_close(cls):
        pass
