"""
走势中枢 (CZS) + 背驰判定 — 缠论核心

【原文出处】
  - 第17课《走势中枢定义再研究》、第20课《缠中说禅走势中枢定义》：
    走势中枢 = 某级别走势类型中，被至少三个连续次级别走势所【重叠】的部分，
    中枢区间 = [max(各段低点), min(各段高点)]。
  - 第24课《MACD对背弛的辅助判断》、第27课：
    趋势背驰 = 最后一个中枢的【离开段】力度 < 【进入段】力度。

【算法实现思路】
  - CZS[LINE_TYPE] 泛型: 笔中枢(LINE_TYPE=CBi) 或 段中枢(LINE_TYPE=CSeg)。
  - update_zs_range(): low=max(元素low), high=min(元素high) —— 逐字对应原文中枢定义；
    peak_low/peak_high 记录涉及笔的最宽极值(供三类买卖点 peak 校验)。
  - combine()/do_combine(): 同线段内相邻中枢若区间(zs模式)或峰值(peak模式)重叠则合并
    (对应原文中枢扩展/更大级别中枢)，子中枢存入 sub_zs_lst。
  - try_add_to_end()/in_range(): 新元素与中枢重叠则延伸中枢。
  - end_bi_break(): 离开中枢笔是否真正突破中枢(向下破low/向上破high)。
  - is_divergence(config): 背驰判定 —— 先要求 end_bi_break()，再比较 bi_in(进)与
    bi_out(出)的 MACD 力度: out <= divergence_rate*in 即背驰，返回(是否背驰, 比值)。
  - out_bi_is_peak(): 离开笔是否为最极端笔(供 bs1_peak 一类买卖点校验)。
  - bi_in/bi_out/bi_lst: 进中枢笔、出中枢笔、中枢内部笔(由 KLine_List 回填)。
"""
from typing import Generic, List, Optional, TypeVar

from Bi.Bi import CBi
from BuySellPoint.BSPointConfig import CPointConfig
from Common.Cache import make_cache
from Common.ChanException import CChanException, ErrCode
from Common.FuncUtil import has_overlap, is_macd_divergence
from KLine.KLineUnit import CKLine_Unit
from Seg.Seg import CSeg

LINE_TYPE = TypeVar('LINE_TYPE', CBi, "CSeg")


class CZS(Generic[LINE_TYPE]):
    def __init__(self, lst: Optional[List[LINE_TYPE]], is_sure=True):
        # begin/end：永远指向 klu
        # low/high: 中枢的范围
        # peak_low/peak_high: 中枢所涉及到的笔的最大值，最小值
        self.__is_sure = is_sure
        self.__sub_zs_lst: List[CZS] = []

        if lst is None:
            return

        self.__begin: CKLine_Unit = lst[0].get_begin_klu()
        self.__begin_bi: LINE_TYPE = lst[0]  # 中枢内部的笔

        # self.__low = None
        # self.__high = None
        # self.__mid = None
        self.update_zs_range(lst)

        # self.__end: CKLine_Unit = None
        # self.__end_bi: CBi = None  # 中枢内部的笔
        self.__peak_high = float("-inf")
        self.__peak_low = float("inf")
        for item in lst:
            self.update_zs_end(item)

        self.__bi_in: Optional[LINE_TYPE] = None  # 进中枢那一笔
        self.__bi_out: Optional[LINE_TYPE] = None  # 出中枢那一笔

        self.__bi_lst: List[LINE_TYPE] = []  # begin_bi~end_bi之间的笔，在update_zs_in_seg函数中更新

    def clean_cache(self):
        self._memoize_cache = {}

    @property
    def is_sure(self): return self.__is_sure

    @property
    def sub_zs_lst(self): return self.__sub_zs_lst

    @property
    def begin(self): return self.__begin

    @property
    def begin_bi(self): return self.__begin_bi

    @property
    def low(self): return self.__low

    @property
    def high(self): return self.__high

    @property
    def mid(self): return self.__mid

    @property
    def end(self): return self.__end

    @property
    def end_bi(self): return self.__end_bi

    @property
    def peak_high(self): return self.__peak_high

    @property
    def peak_low(self): return self.__peak_low

    @property
    def bi_in(self): return self.__bi_in

    @property
    def bi_out(self): return self.__bi_out

    @property
    def bi_lst(self): return self.__bi_lst

    def update_zs_range(self, lst):
        self.__low: float = max(bi._low() for bi in lst)
        self.__high: float = min(bi._high() for bi in lst)
        self.__mid: float = (self.__low + self.__high) / 2  # 中枢的中点
        self.clean_cache()

    def is_one_bi_zs(self):
        assert self.end_bi is not None
        return self.begin_bi.idx == self.end_bi.idx

    def update_zs_end(self, item):
        self.__end: CKLine_Unit = item.get_end_klu()
        self.__end_bi: CBi = item
        if item._low() < self.peak_low:
            self.__peak_low = item._low()
        if item._high() > self.peak_high:
            self.__peak_high = item._high()
        self.clean_cache()

    def __str__(self):
        _str = f"{self.begin_bi.idx}->{self.end_bi.idx}"
        if _str2 := ",".join([str(sub_zs) for sub_zs in self.sub_zs_lst]):
            return f"{_str}({_str2})"
        else:
            return _str

    def combine(self, zs2: 'CZS', combine_mode) -> bool:
        if zs2.is_one_bi_zs():
            return False
        if self.begin_bi.seg_idx != zs2.begin_bi.seg_idx:
            return False
        if combine_mode == 'zs':
            if not has_overlap(self.low, self.high, zs2.low, zs2.high, equal=True):
                return False
            self.do_combine(zs2)
            return True
        elif combine_mode == 'peak':
            if has_overlap(self.peak_low, self.peak_high, zs2.peak_low, zs2.peak_high):
                self.do_combine(zs2)
                return True
            else:
                return False
        else:
            raise CChanException(f"{combine_mode} is unsupport zs conbine mode", ErrCode.PARA_ERROR)

    def do_combine(self, zs2: 'CZS'):
        if len(self.sub_zs_lst) == 0:
            self.__sub_zs_lst.append(self.make_copy())
        self.__sub_zs_lst.append(zs2)

        self.__low = min([self.low, zs2.low])
        self.__high = max([self.high, zs2.high])
        self.__peak_low = min([self.peak_low, zs2.peak_low])
        self.__peak_high = max([self.peak_high, zs2.peak_high])
        self.__end = zs2.end
        self.__bi_out = zs2.bi_out
        self.__end_bi = zs2.end_bi
        self.clean_cache()

    def try_add_to_end(self, item):
        if not self.in_range(item):
            return False
        if self.is_one_bi_zs():
            self.update_zs_range([self.begin_bi, item])
        self.update_zs_end(item)
        return True

    def in_range(self, item):
        return has_overlap(self.low, self.high, item._low(), item._high())

    def is_inside(self, seg: CSeg):
        return seg.start_bi.idx <= self.begin_bi.idx <= seg.end_bi.idx

    def is_divergence(self, config: CPointConfig):
        if not self.end_bi_break():  # 最后一笔必须突破中枢
            return False, None
        # 统一走 is_macd_divergence (支持 area/peak/composite/composite_full 复合背驰)
        # 传 zs=self 供 COMPOSITE_FULL 做黄白线回抽零轴检测
        return is_macd_divergence(
            self.get_bi_in(), self.get_bi_out(),
            config.macd_algo, config.divergence_rate, zs=self,
        )

    def init_from_zs(self, zs: 'CZS'):
        self.__begin = zs.begin
        self.__end = zs.end
        self.__low = zs.low
        self.__high = zs.high
        self.__peak_high = zs.peak_high
        self.__peak_low = zs.peak_low
        self.__begin_bi = zs.begin_bi
        self.__end_bi = zs.end_bi
        self.__bi_in = zs.bi_in
        self.__bi_out = zs.bi_out

    def make_copy(self) -> 'CZS':
        copy = CZS(lst=None, is_sure=self.is_sure)
        copy.init_from_zs(zs=self)
        return copy

    @make_cache
    def end_bi_break(self):
        assert self.bi_out is not None
        return (self.bi_out.is_down() and self.bi_out._low() < self.low) or \
            (self.bi_out.is_up() and self.bi_out._high() > self.high)

    @make_cache
    def out_bi_is_peak(self):
        # 返回 (是否最低点，bi_out与中枢里面尾部最接近它的差距比例)
        assert len(self.bi_lst) > 0
        if self.bi_out is None:
            return False, None
        peak_rate = float("inf")
        for bi in self.bi_lst:
            if (self.bi_out.is_down() and bi._low() < self.bi_out._low()) or (self.bi_out.is_up() and bi._high() > self.bi_out._high()):
                return False, None
            r = abs(bi.get_end_val()-self.bi_out.get_end_val())/self.bi_out.get_end_val()
            if r < peak_rate:
                peak_rate = r
        return True, peak_rate

    def get_bi_in(self) -> LINE_TYPE:
        assert self.bi_in is not None
        return self.bi_in

    def get_bi_out(self) -> LINE_TYPE:
        assert self.__bi_out is not None
        return self.__bi_out

    def set_bi_in(self, bi):
        self.__bi_in = bi
        self.clean_cache()

    def set_bi_out(self, bi):
        self.__bi_out = bi
        self.clean_cache()

    def set_bi_lst(self, bi_lst):
        self.__bi_lst = bi_lst
        self.clean_cache()
