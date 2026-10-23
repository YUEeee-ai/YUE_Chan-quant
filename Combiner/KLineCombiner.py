"""
K线包含关系处理 + 顶底分型识别 (缠论最底层)

【原文出处】《市场哲学的数学原理》第62课《分型与走势的转折》、第63课：
  - 包含关系: 两根K线若高低点存在包含(一根的高低点都在另一根范围内)，需合并；
    合并方向由前一根K线决定 —— 上升中取"高高、低高"(max high, max low)，
    下降中取"低低、高低"(min high, min low)。
  - 顶分型: 三根(合并后)K线，中间一根高点最高且低点也最高；底分型反之。

【算法实现思路】
  - CKLine_Combiner[T] 是泛型合并基类，T 可为 CKLine_Unit(K线) 或 CBi(笔)，
    因此"包含关系处理"这套逻辑同时服务于 K线合并 和 线段特征序列合并。
  - test_combine(): 判定当前合并K线与新元素的关系(COMBINE/UP/DOWN/INCLUDED)。
  - try_add(): 执行合并，严格按方向取 max/min，并特判一字K线(high==low)。
  - update_fx(): 比较 pre/self/next 三根的高低点，标准分支即原文顶/底分型定义；
    exclude_included / allow_top_equal 为放宽变体(可选，默认走标准分支)。
  - get_high_peak_klu/get_low_peak_klu: 定位合并K线内的极值原始K线(带缓存)。
"""
from typing import Generic, Iterable, List, Optional, Self, TypeVar, Union, overload

from Common.Cache import make_cache
from Common.CEnum import FX_TYPE, KLINE_DIR
from Common.ChanException import CChanException, ErrCode
from KLine.KLineUnit import CKLine_Unit

from .CombineItem import CCombine_Item

T = TypeVar('T')


class CKLine_Combiner(Generic[T]):
    def __init__(self, kl_unit: T, _dir):
        item = CCombine_Item(kl_unit)
        self.__time_begin = item.time_begin
        self.__time_end = item.time_end
        self.__high = item.high
        self.__low = item.low

        self.__lst: List[T] = [kl_unit]  # 本级别每一根单位K线

        self.__dir = _dir
        self.__fx = FX_TYPE.UNKNOWN
        self.__pre: Optional[Self] = None
        self.__next: Optional[Self] = None

    def clean_cache(self):
        self._memoize_cache = {}

    @property
    def time_begin(self): return self.__time_begin

    @property
    def time_end(self): return self.__time_end

    @property
    def high(self): return self.__high

    @property
    def low(self): return self.__low

    @property
    def lst(self): return self.__lst

    @property
    def dir(self): return self.__dir

    @property
    def fx(self): return self.__fx

    @property
    def pre(self) -> Self:
        assert self.__pre is not None
        return self.__pre

    @property
    def next(self): return self.__next

    def get_next(self) -> Self:
        assert self.next is not None
        return self.next

    def test_combine(self, item: CCombine_Item, exclude_included=False, allow_top_equal=None):
        if (self.high >= item.high and self.low <= item.low):
            return KLINE_DIR.COMBINE
        if (self.high <= item.high and self.low >= item.low):
            if allow_top_equal == 1 and self.high == item.high and self.low > item.low:
                return KLINE_DIR.DOWN
            elif allow_top_equal == -1 and self.low == item.low and self.high < item.high:
                return KLINE_DIR.UP
            return KLINE_DIR.INCLUDED if exclude_included else KLINE_DIR.COMBINE
        if (self.high > item.high and self.low > item.low):
            return KLINE_DIR.DOWN
        if (self.high < item.high and self.low < item.low):
            return KLINE_DIR.UP
        else:
            raise CChanException("combine type unknown", ErrCode.COMBINER_ERR)

    def try_add(self, unit_kl: T, exclude_included=False, allow_top_equal=None):
        # allow_top_equal = None普通模式
        # allow_top_equal = 1 被包含，顶部相等不合并
        # allow_top_equal = -1 被包含，底部相等不合并
        combine_item = CCombine_Item(unit_kl)
        _dir = self.test_combine(combine_item, exclude_included, allow_top_equal)
        if _dir == KLINE_DIR.COMBINE:
            self.__lst.append(unit_kl)
            if isinstance(unit_kl, CKLine_Unit):
                unit_kl.set_klc(self)
            if self.dir == KLINE_DIR.UP:
                if combine_item.high != combine_item.low or combine_item.high != self.high:  # 处理一字K线
                    self.__high = max([self.high, combine_item.high])
                    self.__low = max([self.low, combine_item.low])
            elif self.dir == KLINE_DIR.DOWN:
                if combine_item.high != combine_item.low or combine_item.low != self.low:  # 处理一字K线
                    self.__high = min([self.high, combine_item.high])
                    self.__low = min([self.low, combine_item.low])
            else:
                raise CChanException(f"KLINE_DIR = {self.dir} err!!! must be {KLINE_DIR.UP}/{KLINE_DIR.DOWN}", ErrCode.COMBINER_ERR)
            self._time_end = combine_item.time_end
            self.clean_cache()
        # 返回UP/DOWN/COMBINE给KL_LIST，设置下一个的方向
        return _dir

    def get_peak_klu(self, is_high) -> T:
        # 获取最大值 or 最小值所在klu/bi
        return self.get_high_peak_klu() if is_high else self.get_low_peak_klu()

    @make_cache
    def get_high_peak_klu(self) -> T:
        for kl in self.lst[::-1]:
            if CCombine_Item(kl).high == self.high:
                return kl
        raise CChanException("can't find peak...", ErrCode.COMBINER_ERR)

    @make_cache
    def get_low_peak_klu(self) -> T:
        for kl in self.lst[::-1]:
            if CCombine_Item(kl).low == self.low:
                return kl
        raise CChanException("can't find peak...", ErrCode.COMBINER_ERR)

    def update_fx(self, _pre: Self, _next: Self, exclude_included=False, allow_top_equal=None):
        # allow_top_equal = None普通模式
        # allow_top_equal = 1 被包含，顶部相等不合并
        # allow_top_equal = -1 被包含，底部相等不合并
        self.set_next(_next)
        self.set_pre(_pre)
        _next.set_pre(self)
        if exclude_included:
            if _pre.high < self.high and _next.high <= self.high and _next.low < self.low:
                if allow_top_equal == 1 or _next.high < self.high:
                    self.__fx = FX_TYPE.TOP
            elif _next.high > self.high and _pre.low > self.low and _next.low >= self.low:
                if allow_top_equal == -1 or _next.low > self.low:
                    self.__fx = FX_TYPE.BOTTOM
        elif _pre.high < self.high and _next.high < self.high and _pre.low < self.low and _next.low < self.low:
            self.__fx = FX_TYPE.TOP
        elif _pre.high > self.high and _next.high > self.high and _pre.low > self.low and _next.low > self.low:
            self.__fx = FX_TYPE.BOTTOM
        self.clean_cache()

    def __str__(self):
        return f"{self.time_begin}~{self.time_end} {self.low}->{self.high}"

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> List[T]: ...

    def __getitem__(self, index: Union[slice, int]) -> Union[List[T], T]:
        return self.lst[index]

    def __len__(self):
        return len(self.lst)

    def __iter__(self) -> Iterable[T]:
        yield from self.lst

    def set_pre(self, _pre: Self):
        self.__pre = _pre
        self.clean_cache()

    def set_next(self, _next: Self):
        self.__next = _next
        self.clean_cache()
