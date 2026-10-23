"""
特征序列元素 (CEigen) — 把"笔"当作K线做包含合并

【原文出处】《市场哲学的数学原理》第67课《线段划分标准的再分辨》：
  线段破坏需用"特征序列"—— 取与线段方向相反的笔作为元素，做包含关系处理，
  再看特征序列是否出现分型。

【算法实现思路】
  - CEigen 继承 CKLine_Combiner[CBi]，即把笔当K线复用第62课的包含合并逻辑。
  - update_fx() 覆写: 除标准分型外，额外标记 self.gap —— 当第一、二元素之间存在
    缺口(原著线段破坏"第二种情形"的关键判据)时 gap=True。
  - GetPeakBiIdx(): 把特征序列分型的峰值KLU映射回对应笔的索引(idx-1)。
  仅被 EigenFX.CEigenFX 使用。
"""
from Bi.Bi import CBi
from Combiner.KLineCombiner import CKLine_Combiner
from Common.CEnum import BI_DIR, FX_TYPE


class CEigen(CKLine_Combiner[CBi]):
    def __init__(self, bi, _dir):
        super(CEigen, self).__init__(bi, _dir)
        self.gap = False

    def update_fx(self, _pre: 'CEigen', _next: 'CEigen', exclude_included=False, allow_top_equal=None):
        super(CEigen, self).update_fx(_pre, _next, exclude_included, allow_top_equal)
        if (self.fx == FX_TYPE.TOP and _pre.high < self.low) or \
           (self.fx == FX_TYPE.BOTTOM and _pre.low > self.high):
            self.gap = True

    def __str__(self):
        return f"{self.lst[0].idx}~{self.lst[-1].idx} gap={self.gap} fx={self.fx}"

    def GetPeakBiIdx(self):
        assert self.fx != FX_TYPE.UNKNOWN
        bi_dir = self.lst[0].dir
        if bi_dir == BI_DIR.UP:  # 下降线段
            return self.get_peak_klu(is_high=False).idx-1
        else:
            return self.get_peak_klu(is_high=True).idx-1
