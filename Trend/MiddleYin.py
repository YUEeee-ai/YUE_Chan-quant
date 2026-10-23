"""
中阴阶段 — 转折后的模糊期识别

【原文出处】《市场哲学的数学原理》(缠中说禅) 第89课《中阴阶段》:
  一个走势类型完成(背驰/第一类买卖点出现)之后、下一个明确走势类型
  (新中枢或第三类买卖点确认)形成之前，存在一段方向未定的"中阴阶段"。
  此阶段买卖点信号不可靠，操作上宜减仓、不追、等待新的确认。

【为什么需要识别中阴】
  转折点(如顶背驰一类卖点)只宣告"上一段走势结束"，并不保证"下一段立刻
  顺畅展开"。中阴阶段价格常在旧中枢与新方向之间反复，此时若按边界信号
  满仓追入新方向，容易在模糊期被反复扫。把中阴显式标出来后，策略可以在
  这段期间对新开仓降权(减仓试探)、禁止激进反手，等第三类买卖点或新中枢
  形成再恢复正常仓位。

【算法实现思路】
  以操作级别的买卖点序列 + 中枢序列判定:
    1. 找最近一个"转折边界" = 最后一个 T1/T1P(趋势或盘整背驰一类)买卖点;
    2. 统计该边界【之后】是否已出现确认结构:
         - 新的多笔中枢(begin 落在边界之后); 或
         - 第三类买卖点 T3A/T3B(中枢突破回抽确认)。
    3. 若两者都尚未出现 → 处于中阴阶段(in_middle_yin=True);
       一旦有新中枢或 T3 → 中阴结束。
    4. 额外用 bars_since 记录边界以来经过的合并 K 线数, 供策略设置
       "中阴最长时限"(超时视为已消化, 恢复正常处理)。
"""
from dataclasses import dataclass
from typing import List, Optional

from Common.CEnum import BSP_TYPE


@dataclass
class MiddleYinState:
    """中阴阶段状态"""
    in_middle_yin: bool = False
    boundary_time: Optional[str] = None   # 转折边界(最后一个T1)时间
    bars_since: int = 0                    # 边界以来经过的合并K线数
    new_zs_count: int = 0                  # 边界后新形成的多笔中枢数
    has_t3: bool = False                   # 边界后是否已出现第三类买卖点
    reason: str = ""

    def __str__(self):
        return f"中阴({self.bars_since}K,新中枢{self.new_zs_count},T3={self.has_t3})" if self.in_middle_yin else "非中阴"


class MiddleYinDetector:
    """中阴阶段检测器"""

    def detect(self, chan, lv, max_bars: Optional[int] = None) -> MiddleYinState:
        """
        检测 chan[lv] 当前是否处于中阴阶段。
        max_bars: 中阴最长时限(合并K线数), 超过则视为已消化(非中阴); None=不限。
        """
        st = MiddleYinState()
        try:
            bsp_list = sorted(chan[lv].bs_point_lst.lst, key=lambda x: x.klu.idx)
            valid_zs = [z for z in chan[lv].zs_list.zs_lst if not z.is_one_bi_zs()]
            kl_len = len(chan[lv])
        except Exception:
            return st

        # 1. 最近一个转折边界 (T1/T1P)
        boundary = None
        for b in reversed(bsp_list):
            if BSP_TYPE.T1 in b.type or BSP_TYPE.T1P in b.type:
                boundary = b
                break
        if boundary is None:
            return st  # 尚无转折边界, 谈不上中阴

        boundary_idx = boundary.klu.idx
        st.boundary_time = str(boundary.klu.time)

        # 2. 边界之后的确认结构
        st.has_t3 = any(
            (BSP_TYPE.T3A in b.type or BSP_TYPE.T3B in b.type)
            for b in bsp_list if b.klu.idx > boundary_idx
        )
        st.new_zs_count = sum(
            1 for z in valid_zs if self._zs_begin_idx(z) > boundary_idx
        )

        # 3. bars_since (以合并K线索引近似)
        try:
            last_idx = chan[lv][-1][-1].idx if kl_len > 0 else boundary_idx
            st.bars_since = max(0, last_idx - boundary_idx)
        except Exception:
            st.bars_since = 0

        resolved = st.has_t3 or st.new_zs_count > 0
        timed_out = (max_bars is not None and st.bars_since > max_bars)
        if resolved or timed_out:
            st.in_middle_yin = False
            st.reason = "已出现新中枢/第三类买卖点" if resolved else "中阴超过时限, 视为已消化"
        else:
            st.in_middle_yin = True
            st.reason = "转折后尚无新中枢与第三类买卖点确认, 方向未定"
        return st

    @staticmethod
    def _zs_begin_idx(zs) -> int:
        try:
            return zs.begin.idx
        except Exception:
            return -1
