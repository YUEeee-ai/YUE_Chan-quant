"""
加密货币行情数据源 (ccxt) — 现货 K 线

注意: ccxt 为可选依赖, 仅在 --data-src ccxt 时需要; 未安装时给出友好报错,
而不是在 import 期直接崩溃。
"""
from datetime import datetime, timezone

from Common.CEnum import AUTYPE, KL_TYPE
from Common.ChanException import CChanException, ErrCode
from Common.FuncUtil import kltype_lt_day
from KLine.KLineUnit import CKLine_Unit

try:
    import ccxt  # noqa: F401
    _CCXT_AVAILABLE = True
except ImportError:
    _CCXT_AVAILABLE = False

from .CommonStockAPI import CCommonStockApi, GetColumnNameFromFieldList, create_item_dict


class CCXT(CCommonStockApi):
    is_connect = None

    def __init__(self, code, k_type=KL_TYPE.K_DAY, begin_date=None, end_date=None, autype=AUTYPE.QFQ):
        super(CCXT, self).__init__(code, k_type, begin_date, end_date, autype)

    def get_kl_data(self):
        if not _CCXT_AVAILABLE:
            raise CChanException("ccxt 未安装, 请执行: pip install ccxt", ErrCode.SRC_DATA_TYPE_ERR)
        fields = "time,open,high,low,close"
        exchange = ccxt.binance()
        timeframe = self.__convert_type()

        # 起始时间 (缺省从交易所可取的最早数据开始, since=None)
        since = None
        if self.begin_date:
            since = exchange.parse8601(f'{self.begin_date}T00:00:00')
        # 结束时间 (毫秒): 不填则取到当前
        until = None
        if self.end_date:
            until = exchange.parse8601(f'{self.end_date}T23:59:59')

        limit = 1000
        while True:
            data = exchange.fetch_ohlcv(self.code, timeframe, since=since, limit=limit)
            if not data:
                break
            for item in data:
                ts = item[0]
                if until is not None and ts > until:
                    return  # 超过回测右端, 停止
                # 用 UTC 避免本地时区偏移导致时间戳错位
                time_obj = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                time_str = time_obj.strftime('%Y-%m-%d %H:%M:%S')
                item_data = [time_str, item[1], item[2], item[3], item[4]]
                yield CKLine_Unit(
                    create_item_dict(item_data, GetColumnNameFromFieldList(fields), auto=not kltype_lt_day(self.k_type)),
                    autofix=True,
                )
            if len(data) < limit:
                break  # 取完最后一批
            since = data[-1][0] + 1  # 从最后一根之后继续翻页
            if until is not None and since > until:
                break

    def SetBasciInfo(self):
        pass

    @classmethod
    def do_init(cls):
        pass

    @classmethod
    def do_close(cls):
        pass

    def __convert_type(self):
        _dict = {
            KL_TYPE.K_DAY: '1d',
            KL_TYPE.K_WEEK: '1w',
            KL_TYPE.K_MON: '1M',
            KL_TYPE.K_5M: '5m',
            KL_TYPE.K_15M: '15m',
            KL_TYPE.K_30M: '30m',
            KL_TYPE.K_60M: '1h',
        }
        if self.k_type not in _dict:
            raise CChanException(f"ccxt 不支持级别 {self.k_type}", ErrCode.SRC_DATA_TYPE_ERR)
        return _dict[self.k_type]
