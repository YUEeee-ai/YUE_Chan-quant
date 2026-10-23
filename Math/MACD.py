"""
MACD 指标 (在线增量计算)

【原文出处】第24课《MACD对背弛的辅助判断》：缠论用 MACD 红绿柱面积/高度辅助判断
  背驰(力度衰减)。注意本文件只负责【计算指标序列】，背驰的"力度比较"逻辑在
  Bi.cal_macd_metric 与 ZS.is_divergence 中实现。

【算法实现思路】
  - CMACD_item: 单根K线的 (fast_ema, slow_ema, DIF, DEA, macd) 快照，
    其中 macd=2*(DIF-DEA) 为国内约定的红绿柱。
  - CMACD: 在线增量 MACD(默认12/26/9)，add(value) 用递推式
    ema=(2*value+(p-1)*prev_ema)/(p+1) 更新，首值播种。
  结果逐K线存于 klu.macd，供背驰度量与绘图使用。
"""
from typing import List


class CMACD_item:
    def __init__(self, fast_ema, slow_ema, DIF, DEA):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.DIF = DIF
        self.DEA = DEA
        self.macd = 2 * (DIF - DEA)


class CMACD:
    def __init__(self, fastperiod=12, slowperiod=26, signalperiod=9):
        self.macd_info: List[CMACD_item] = []
        self.fastperiod = fastperiod
        self.slowperiod = slowperiod
        self.signalperiod = signalperiod

    def add(self, value) -> CMACD_item:
        if not self.macd_info:
            self.macd_info.append(CMACD_item(fast_ema=value, slow_ema=value, DIF=0, DEA=0))
        else:
            _fast_ema = (2 * value + (self.fastperiod - 1) * self.macd_info[-1].fast_ema) / (self.fastperiod + 1)
            _slow_ema = (2 * value + (self.slowperiod - 1) * self.macd_info[-1].slow_ema) / (self.slowperiod + 1)
            _dif = _fast_ema - _slow_ema
            _dea = (2 * _dif + (self.signalperiod - 1) * self.macd_info[-1].DEA) / (self.signalperiod + 1)
            self.macd_info.append(CMACD_item(fast_ema=_fast_ema, slow_ema=_slow_ema, DIF=_dif, DEA=_dea))
        return self.macd_info[-1]
