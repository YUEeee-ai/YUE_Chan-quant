"""
小转大 — 小级别背驰引发大级别转折的识别 (原著第44课)

【原文出处】《市场哲学的数学原理》(缠中说禅) 第44课《小级别背驰引发大级别转折》:
  一般情况下，某级别的一个走势类型走完（背驰），对应着该级别的一个第一类买卖点；
  但存在特例 —— 大级别的走势并没有背驰（没有该级别的一类买卖点），只是小级别
  反复背驰，随后大级别走势却被逆转了，这就是"小转大"。操作上，小转大的确认
  必须以小级别背驰后【大级别结构被破坏】（如重新收回中枢）为依据，否则不能
  把每个小级别背驰都当成大级别转折。

【为什么需要识别小转大】
  已有的跨级别背驰归属（LevelLinkage）处理的是"小级别背驰不算大级别反转"
  （归属为次级别回调，禁逆势）；小转大处理的正是它的补集 —— 当大级别没有
  背驰、但小级别背驰后大级别结构被实实在在破坏（跌出中枢后又收回中枢）时，
  允许把它当作大级别早期转折点来操作。两个模块合在一起，才是第44课的完整口径。

【算法实现思路】
  输入: 大级别 large_lv（被转折的级别）、次级别 sub_lv（产生背驰的级别，通常是操作级别）。
  判定一个"向上小转大"（大级别下跌被小级别底背驰逆转）需同时满足:
    1. 无大级别背驰: 大级别最后一个有效中枢的离开段【不背驰】
       （否则就是常规的一类转折，谈不上"小转大"）；
    2. 有小级别背驰: 次级别在大级别末中枢形成以来出现过 T1/T1P 同向背驰，
       且最新一次小背驰之后价格【没有】再创出大级别顺势新极值；
    3. 结构破坏确认: 大级别价格曾跌出（跌破）末中枢下沿，且当前收盘已重新
       站上中枢下沿 —— "跌出去又收回来"= 空头结构被破坏，小转大确认。
  向下小转大完全镜像。三条同时满足输出 active=True，供策略层在级别联立
  本应"禁逆势开仓"时放行早期反转仓（并按 small_turn_big_scale 缩小仓位）。
"""
from dataclasses import dataclass
from typing import List, Optional

from Common.CEnum import BSP_TYPE, KL_TYPE


@dataclass
class SmallTurnBigState:
    """小转大识别状态"""
    is_buy: bool = True               # True=底背驰引发向上转折; False=顶背驰引发向下转折
    active: bool = False              # 小转大是否确认(可放行早期反转仓)
    large_lv: Optional[KL_TYPE] = None
    sub_lv: Optional[KL_TYPE] = None
    zs_low: Optional[float] = None    # 大级别末中枢区间
    zs_high: Optional[float] = None
    sub_divergence_count: int = 0     # 窗口内次级别同向背驰次数
    broke_out: bool = False           # 价格是否曾顺大级别趋势方向冲出中枢
    recovered: bool = False           # 价格是否已收回中枢区间
    reason: str = ""

    def __str__(self):
        if not self.active:
            return f"小转大({'买' if self.is_buy else '卖'}):未确认({self.reason})"
        return (f"小转大({'买' if self.is_buy else '卖'}):确认 小背驰×{self.sub_divergence_count} "
                f"{'跌破后收回' if self.is_buy else '冲破后回落'}")


class SmallTurnBigDetector:
    """小级别背驰引发大级别转折的检测器 (第44课)"""

    def __init__(self, min_sub_divergence: int = 1):
        # 窗口内至少需要的次级别背驰次数（防单次噪声，默认1=宽松）
        self.min_sub_divergence = min_sub_divergence

    # --- 公开接口 ---

    def detect_buy(self, chan, large_lv: KL_TYPE, sub_lv: KL_TYPE, bsp_conf) -> SmallTurnBigState:
        """识别向上的小转大：大级别下跌无背驰，被小级别底背驰逆转"""
        return self._detect(chan, large_lv, sub_lv, is_buy=True, bsp_conf=bsp_conf)

    def detect_sell(self, chan, large_lv: KL_TYPE, sub_lv: KL_TYPE, bsp_conf) -> SmallTurnBigState:
        """识别向下的小转大：大级别上涨无背驰，被小级别顶背驰逆转"""
        return self._detect(chan, large_lv, sub_lv, is_buy=False, bsp_conf=bsp_conf)

    # --- 内部实现 ---

    def _detect(self, chan, large_lv: KL_TYPE, sub_lv: KL_TYPE, is_buy: bool, bsp_conf) -> SmallTurnBigState:
        st = SmallTurnBigState(is_buy=is_buy, large_lv=large_lv, sub_lv=sub_lv)
        try:
            large_kl = chan[large_lv]
            sub_kl = chan[sub_lv]
        except Exception:
            st.reason = "缺少级别数据"
            return st

        valid_zs = [z for z in large_kl.zs_list.zs_lst if not z.is_one_bi_zs()]
        if not valid_zs:
            st.reason = "大级别无有效中枢"
            return st
        last_zs = valid_zs[-1]
        st.zs_low, st.zs_high = last_zs.low, last_zs.high

        if len(large_kl) == 0 or len(large_kl[-1]) == 0:
            st.reason = "大级别无K线"
            return st
        cur_close = large_kl[-1][-1].close

        # 条件1: 大级别末中枢离开段【不背驰】（背驰就是常规转折，非小转大）
        if last_zs.bi_out is not None:
            try:
                is_diver, _ = last_zs.is_divergence(bsp_conf)
            except Exception:
                is_diver = False
            if is_diver:
                st.reason = "大级别自身已背驰(常规一类转折)"
                return st

        # 大级别末中枢形成以来 = 次级别背驰的搜索窗口
        try:
            win_start = last_zs.begin.time.ts
        except Exception:
            win_start = None

        sub_bsps: List = []
        try:
            for b in sub_kl.bs_point_lst.lst:
                if BSP_TYPE.T1 not in b.type and BSP_TYPE.T1P not in b.type:
                    continue
                if b.is_buy != is_buy:
                    continue
                if win_start is not None and b.klu.time.ts < win_start:
                    continue
                sub_bsps.append(b)
        except Exception:
            st.reason = "次级别买卖点读取失败"
            return st

        st.sub_divergence_count = len(sub_bsps)
        if st.sub_divergence_count < self.min_sub_divergence:
            st.reason = "窗口内无次级别背驰"
            return st
        latest_div = sub_bsps[-1]

        # 条件2: 最新小背驰之后价格未再创大级别顺势新极值
        try:
            large_bis = large_kl.bi_list.bi_list
            after_bi = [bi for bi in large_bis if bi.get_end_klu().time.ts >= latest_div.klu.time.ts]
            if not after_bi:
                st.reason = "小背驰后大级别尚无后续笔"
                return st
            if is_buy:
                new_extreme = min(bi._low() for bi in after_bi) < latest_div.bi._low()
            else:
                new_extreme = max(bi._high() for bi in after_bi) > latest_div.bi._high()
            if new_extreme:
                st.reason = "小背驰后价格再创新极值, 背驰失效"
                return st
        except Exception:
            pass  # 笔序列读取失败时跳过该条件（不因此否决）

        # 条件3: 结构破坏 —— 曾顺大级别趋势方向冲出中枢，现已收回
        try:
            in_window = [bi for bi in large_bis if bi.get_end_klu().time.ts >= win_start] if win_start else large_bis
            if is_buy:
                st.broke_out = any(bi._low() < last_zs.low for bi in in_window)
                st.recovered = cur_close > last_zs.low
            else:
                st.broke_out = any(bi._high() > last_zs.high for bi in in_window)
                st.recovered = cur_close < last_zs.high
        except Exception:
            st.reason = "大级别笔序列读取失败"
            return st

        if not st.broke_out:
            st.reason = "价格未曾跌出中枢(无结构破坏)"
            return st
        if not st.recovered:
            st.reason = "价格尚未收回中枢区间"
            return st

        st.active = True
        st.reason = (
            f"大级别背驰段未背驰, 次级别{st.sub_divergence_count}次背驰后"
            f"{'跌破' if is_buy else '冲破'}中枢并已收回, 结构被破坏"
        )
        return st
