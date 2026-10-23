"""
买卖点对象 (CBS_Point) — 计算流水线的输出

【原文出处】第20/27/29课：一个买卖点可同时具备多种类型(如既是二类又是类二)，
  且二类/三类买卖点需回指其依赖的第一类买卖点。

【算法实现思路】
  - CBS_Point[LINE_TYPE] 泛型(笔买卖点/段买卖点)，记录: 触发笔 bi、末端 klu、
    is_buy、type(BSP_TYPE 列表，一点可多类型)、relate_bsp1(所依赖的一类买卖点)。
  - 构造时反向把自己挂到 bi.bsp。
  - add_type()/add_another_bsp_prop(): 同一 KLU 上合并新的类型/关联T1。
  - type2str(): 类型转字符串(如 "1,2")。
  由 BSPointList 创建与管理。
"""
from typing import Generic, List, Optional, TypeVar

from Bi.Bi import CBi
from Common.CEnum import BSP_TYPE
from Seg.Seg import CSeg

LINE_TYPE = TypeVar('LINE_TYPE', CBi, CSeg)


class CBS_Point(Generic[LINE_TYPE]):
    def __init__(self, bi: LINE_TYPE, is_buy, bs_type: BSP_TYPE, relate_bsp1: Optional['CBS_Point']):
        self.bi: LINE_TYPE = bi
        self.klu = bi.get_end_klu()
        self.is_buy = is_buy
        self.type: List[BSP_TYPE] = [bs_type]
        self.relate_bsp1 = relate_bsp1

        self.bi.bsp = self  # type: ignore

        self.is_segbsp = False

    def add_type(self, bs_type: BSP_TYPE):
        self.type.append(bs_type)

    def type2str(self):
        return ",".join([x.value for x in self.type])

    def add_another_bsp_prop(self, bs_type: BSP_TYPE, relate_bsp1):
        self.add_type(bs_type)
        if self.relate_bsp1 is None:
            self.relate_bsp1 = relate_bsp1
        elif relate_bsp1 is not None:
            assert self.relate_bsp1.klu.idx == relate_bsp1.klu.idx
