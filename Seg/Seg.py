"""
线段 (CSeg) — 缠论次级别走势单元，支持递归级别

【原文出处】《市场哲学的数学原理》第65/67课：线段至少由三笔组成且前三笔有重叠；
  第18课：线段可作为更高级别的"笔"，递归构成"线段的线段"与父级别中枢。

【算法实现思路】
  - CSeg[LINE_TYPE] 是泛型: LINE_TYPE=CBi 时为普通线段，LINE_TYPE=CSeg 时即
    "线段的线段"(父级别)，通过 seg_idx/parent_seg 表达递归级别。
  - 记录 start_bi/end_bi、方向、is_sure、终结原因、zs_lst(本线段内中枢列表)、
    bi_list、eigen_fx(特征序列分型)、bsp(尾部买卖点)。
  - check(): 校验方向与端点值序一致、长度>=3笔，否则抛 SEG_*_ERR。
  - cal_klu_slope/cal_amp/cal_macd_metric: 供背驰/买卖点使用的度量。
  - get_first_multi_bi_zs/get_final_multi_bi_zs/get_multi_bi_zs_cnt:
    取首个/末个"多笔中枢"及中枢数 —— 走势类型(趋势>=2中枢)判定的基础。
  - update_bi_list(): 由笔列表构建趋势线(Math.TrendLine)。
"""
from typing import Generic, List, Optional, Self, TypeVar

from Bi.Bi import CBi
from Common.CEnum import BI_DIR, MACD_ALGO
from Common.ChanException import CChanException, ErrCode
from Common.FuncUtil import cal_macd_amp, cal_macd_slope
from KLine.KLineUnit import CKLine_Unit
from Math.TrendLine import CTrendLine

from .EigenFX import CEigenFX

LINE_TYPE = TypeVar('LINE_TYPE', CBi, "CSeg")


class CSeg(Generic[LINE_TYPE]):
    def __init__(self, idx: int, start_bi: LINE_TYPE, end_bi: LINE_TYPE, is_sure=True, seg_dir=None, reason="normal"):
        assert start_bi.idx == 0 or start_bi.dir == end_bi.dir or not is_sure, f"{start_bi.idx} {end_bi.idx} {start_bi.dir} {end_bi.dir}"
        self.idx = idx
        self.start_bi = start_bi
        self.end_bi = end_bi
        self.is_sure = is_sure
        self.dir = end_bi.dir if seg_dir is None else seg_dir

        from ZS.ZS import CZS
        self.zs_lst: List[CZS[LINE_TYPE]] = []

        self.eigen_fx: Optional[CEigenFX] = None
        self.seg_idx = None  # 线段的线段用
        self.parent_seg: Optional[CSeg] = None  # 在哪个线段里面
        self.pre: Optional[Self] = None
        self.next: Optional[Self] = None

        from BuySellPoint.BSPoint import CBS_Point
        self.bsp: Optional[CBS_Point] = None  # 尾部是不是买卖点

        self.bi_list: List[LINE_TYPE] = []  # 仅通过self.update_bi_list来更新
        self.reason = reason
        self.trend_line = None
        if end_bi.idx - start_bi.idx < 2:
            self.is_sure = False
        self.check()

    def set_seg_idx(self, idx):
        self.seg_idx = idx

    def check(self):
        if not self.is_sure:
            return
        if self.is_down():
            if self.start_bi.get_begin_val() < self.end_bi.get_end_val():
                raise CChanException(f"下降线段起始点应该高于结束点! idx={self.idx}", ErrCode.SEG_END_VALUE_ERR)
        elif self.start_bi.get_begin_val() > self.end_bi.get_end_val():
            raise CChanException(f"上升线段起始点应该低于结束点! idx={self.idx}", ErrCode.SEG_END_VALUE_ERR)
        if self.end_bi.idx - self.start_bi.idx < 2:
            raise CChanException(f"线段({self.start_bi.idx}-{self.end_bi.idx})长度不能小于2! idx={self.idx}", ErrCode.SEG_LEN_ERR)

    def __str__(self):
        return f"{self.start_bi.idx}->{self.end_bi.idx}: {self.dir}  {self.is_sure}"

    def add_zs(self, zs):
        self.zs_lst.append(zs)

    def cal_klu_slope(self):
        assert self.end_bi.idx >= self.start_bi.idx
        return (self.get_end_val()-self.get_begin_val())/(self.get_end_klu().idx-self.get_begin_klu().idx)/self.get_begin_val()

    def cal_amp(self):
        return (self.get_end_val()-self.get_begin_val())/self.get_begin_val()

    def cal_bi_cnt(self):
        return self.end_bi.idx-self.start_bi.idx+1

    def clear_zs_lst(self):
        self.zs_lst = []

    def _low(self):
        return self.end_bi.get_end_klu().low if self.is_down() else self.start_bi.get_begin_klu().low

    def _high(self):
        return self.end_bi.get_end_klu().high if self.is_up() else self.start_bi.get_begin_klu().high

    def is_down(self):
        return self.dir == BI_DIR.DOWN

    def is_up(self):
        return self.dir == BI_DIR.UP

    def get_end_val(self):
        return self.end_bi.get_end_val()

    def get_begin_val(self):
        return self.start_bi.get_begin_val()

    def amp(self):
        return abs(self.get_end_val() - self.get_begin_val())

    def get_end_klu(self) -> CKLine_Unit:
        return self.end_bi.get_end_klu()

    def get_begin_klu(self) -> CKLine_Unit:
        return self.start_bi.get_begin_klu()

    def get_klu_cnt(self):
        return self.get_end_klu().idx - self.get_begin_klu().idx + 1

    def cal_macd_metric(self, macd_algo, is_reverse):
        if macd_algo == MACD_ALGO.SLOPE:
            return self.Cal_MACD_slope()
        elif macd_algo == MACD_ALGO.AMP:
            return self.Cal_MACD_amp()
        else:
            raise CChanException(f"unsupport macd_algo={macd_algo} of Seg, should be one of slope/amp", ErrCode.PARA_ERROR)

    def Cal_MACD_slope(self):
        return cal_macd_slope(self.get_begin_klu(), self.get_end_klu(), self.is_up())

    def Cal_MACD_amp(self):
        return cal_macd_amp(self.get_begin_klu(), self.get_end_klu(), self.is_down())

    def update_bi_list(self, bi_lst, idx1, idx2):
        for bi_idx in range(idx1, idx2+1):
            bi_lst[bi_idx].parent_seg = self
            self.bi_list.append(bi_lst[bi_idx])
        if len(self.bi_list) >= 3:
            self.trend_line = CTrendLine(self.bi_list)

    def get_first_multi_bi_zs(self):
        return next((zs for zs in self.zs_lst if not zs.is_one_bi_zs()), None)

    def get_final_multi_bi_zs(self):
        return next((zs for zs in self.zs_lst[::-1] if not zs.is_one_bi_zs()), None)

    def get_multi_bi_zs_cnt(self):
        return sum(not zs.is_one_bi_zs() for zs in self.zs_lst)
