"""
合并元素适配器 — 统一 K线/笔/线段 的 (时间, 高低点) 视图

【原文出处】服务于第62课包含关系处理：合并逻辑需要一个统一接口读取任意元素的
  time_begin/time_end/high/low，才能对 K线、笔、线段复用同一套包含关系算法。

【算法实现思路】
  CCombine_Item 按输入类型分派：
  - CKLine_Unit(原始K线): 直接取其 time/high/low；
  - CBi(笔): 取笔的起止时间与极值；
  - CSeg(线段): 取线段的起止与极值；
  其他类型抛 CChanException(COMMON_ERROR)。
  这样 CKLine_Combiner 既能合并K线(分型)，也能合并笔(特征序列)。
"""
from Common.ChanException import CChanException, ErrCode


class CCombine_Item:
    def __init__(self, item):
        from Bi.Bi import CBi
        from KLine.KLineUnit import CKLine_Unit
        from Seg.Seg import CSeg
        if type(item) == CBi:
            self.time_begin = item.begin_klc.idx
            self.time_end = item.end_klc.idx
            self.high = item._high()
            self.low = item._low()
        elif type(item) == CKLine_Unit:
            self.time_begin = item.time
            self.time_end = item.time
            self.high = item.high
            self.low = item.low
        elif type(item) == CSeg:
            self.time_begin = item.start_bi.begin_klc.idx
            self.time_end = item.end_bi.end_klc.idx
            self.high = item._high()
            self.low = item._low()
        else:
            raise CChanException(f"{type(item)} is unsupport sub class of CCombine_Item", ErrCode.COMMON_ERROR)
