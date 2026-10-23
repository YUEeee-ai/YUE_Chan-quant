import abc
from typing import Iterable

from Common.CEnum import DATA_FIELD
from Common.CTime import CTime
from Common.FuncUtil import str2float
from KLine.KLineUnit import CKLine_Unit

# 数据源字段名 → 内部 DATA_FIELD 映射（各数据源子类共用）
_FIELD_DICT = {
    "time": DATA_FIELD.FIELD_TIME,
    "date": DATA_FIELD.FIELD_TIME,
    "open": DATA_FIELD.FIELD_OPEN,
    "high": DATA_FIELD.FIELD_HIGH,
    "low": DATA_FIELD.FIELD_LOW,
    "close": DATA_FIELD.FIELD_CLOSE,
    "volume": DATA_FIELD.FIELD_VOLUME,
    "amount": DATA_FIELD.FIELD_TURNOVER,
    "turn": DATA_FIELD.FIELD_TURNRATE,
}


def GetColumnNameFromFieldList(fileds: str):
    return [_FIELD_DICT[x] for x in fileds.split(",")]


def parse_time_column(inp, auto=True):
    # 支持三种时间串格式:
    #   '2021-09-13'            (10)  日线
    #   '20210902113000000'     (17)  部分源的数字时间戳
    #   '2021-09-13 11:30:00'   (19)  分钟线
    if len(inp) == 10:
        year = int(inp[:4])
        month = int(inp[5:7])
        day = int(inp[8:10])
        hour = minute = 0
    elif len(inp) == 17:
        year = int(inp[:4])
        month = int(inp[4:6])
        day = int(inp[6:8])
        hour = int(inp[8:10])
        minute = int(inp[10:12])
    elif len(inp) == 19:
        year = int(inp[:4])
        month = int(inp[5:7])
        day = int(inp[8:10])
        hour = int(inp[11:13])
        minute = int(inp[14:16])
    else:
        raise Exception(f"unknown time column format:{inp}")
    return CTime(year, month, day, hour, minute, auto=auto)


def create_item_dict(data, column_name, auto=True):
    # data[0] 为时间串, 其余为数值串 → {DATA_FIELD: 值} 的行字典
    for i in range(len(data)):
        data[i] = parse_time_column(data[i], auto=auto) if i == 0 else str2float(data[i])
    return dict(zip(column_name, data))


class CCommonStockApi:
    def __init__(self, code, k_type, begin_date, end_date, autype):
        self.code = code
        self.name = None
        self.is_stock = None
        self.k_type = k_type
        self.begin_date = begin_date
        self.end_date = end_date
        self.autype = autype
        self.SetBasciInfo()

    @abc.abstractmethod
    def get_kl_data(self) -> Iterable[CKLine_Unit]:
        pass

    @abc.abstractmethod
    def SetBasciInfo(self):
        pass

    @classmethod
    @abc.abstractmethod
    def do_init(cls):
        pass

    @classmethod
    @abc.abstractmethod
    def do_close(cls):
        pass
