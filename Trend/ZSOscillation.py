"""
中枢震荡监视器 — 中枢区间内的高抛低吸 (原著第92课)

【原文出处】《市场哲学的数学原理》(缠中说禅) 第92课《中枢震荡的监视器》:
  围绕一个中枢的震荡（价格不脱离中枢区间）会延续，直至出现第三类买卖点
  （脱离中枢后回抽不回）为止。震荡期间的操作不是追趋势，而是"下来了补点，
  上去了抛点"的高抛低吸；只有中枢被第三类买卖点确认破坏后，才转为趋势操作。

【为什么需要中枢震荡监视器】
  现有策略以"趋势持有"为主线（同级别分解/级别联立都服务于此），但市场大量
  时间处于中枢震荡。震荡市里追三类买卖点（趋势单）容易被来回扫，而在区间
  上下沿做高抛低吸才是第92课规定的正解。把"是否处于中枢震荡"显式识别出来，
  策略就可以在震荡市中：① 禁止趋势追单（三类买卖点降权/否决）；② 放行区间
  内的盘整背驰低吸/高抛（T1P），与趋势持有正交。

【算法实现思路】
  以操作级别最后一个有效中枢 Z 为监视对象:
    1. 震荡进行中 active: 中枢形成后尚无第三类买卖点（T3A/T3B）确认离开，
       且最新收盘仍在 [Z.low×(1-band), Z.high×(1+band)] 缓冲带内；
    2. 触摸计数: 中枢区间内曾触及下沿/上沿的次数（≥各1次才算有效震荡）；
    3. 位置分区: 收盘处于区间下1/3 → 低吸区(in_low_band)；上1/3 → 高抛区；
    4. 输出 ZSOscillationState(含 advice: 低吸区/高抛区/观望), 供策略层门控。
"""
from dataclasses import dataclass
from typing import Optional

from Common.CEnum import BSP_TYPE, KL_TYPE
from Trend.TrendCommon import fetch_kl, require_valid_zs


@dataclass
class ZSOscillationState:
    """中枢震荡监视状态"""
    active: bool = False            # 中枢震荡进行中(未出现第三类买卖点离开)
    lv: Optional[KL_TYPE] = None
    zs_low: Optional[float] = None  # 监视中枢区间
    zs_high: Optional[float] = None
    zs_mid: Optional[float] = None
    touch_low: int = 0              # 区间内触及下沿的次数
    touch_high: int = 0             # 区间内触及上沿的次数
    close: Optional[float] = None
    in_low_band: bool = False       # 收盘位于区间下1/3(低吸区)
    in_high_band: bool = False      # 收盘位于区间上1/3(高抛区)
    amplitude_pct: float = 0.0      # 中枢区间宽度(相对中点, %)
    bars_in_zs: int = 0             # 中枢形成以来的合并K线数
    advice: str = ""                # "" / "低吸区" / "高抛区" / "观望"
    reason: str = ""

    def __str__(self):
        if not self.active:
            return f"中枢震荡:未激活({self.reason})"
        return (f"中枢震荡:[{self.zs_low:.2f},{self.zs_high:.2f}] "
                f"摸低{self.touch_low}摸高{self.touch_high} → {self.advice}")


class ZSOscillationMonitor:
    """中枢震荡监视器 (第92课)"""

    def __init__(self, band: float = 0.005, min_touch: int = 1):
        self.band = band        # 中枢区间外缓冲带(0.5%), 价格超出即视为已离开
        self.min_touch = min_touch  # 每侧至少触摸次数才算有效震荡

    def detect(self, chan, lv: KL_TYPE) -> ZSOscillationState:
        st = ZSOscillationState(lv=lv)
        kl = fetch_kl(chan, lv, st)
        if kl is None:
            return st

        valid_zs = require_valid_zs(kl, st)
        if valid_zs is None:
            return st
        zs = valid_zs[-1]
        st.zs_low, st.zs_high = zs.low, zs.high
        st.zs_mid = (zs.low + zs.high) / 2
        st.amplitude_pct = (zs.high - zs.low) / st.zs_mid * 100 if st.zs_mid else 0.0

        if len(kl) == 0 or len(kl[-1]) == 0:
            st.reason = "无K线"
            return st
        st.close = kl[-1][-1].close

        # 中枢起点(合并K线索引), 用于统计窗口
        try:
            begin_idx = zs.begin.idx
        except Exception:
            begin_idx = 0

        # 条件1: 尚无第三类买卖点确认离开(中枢破坏)
        try:
            has_t3_after = any(
                (BSP_TYPE.T3A in b.type or BSP_TYPE.T3B in b.type) and b.klu.idx > begin_idx
                for b in kl.bs_point_lst.lst
            )
        except Exception:
            has_t3_after = False
        if has_t3_after:
            st.reason = "中枢已被第三类买卖点破坏, 转趋势操作"
            return st

        # 条件2: 最新收盘仍在中枢区间(含缓冲带)内
        lo, hi = zs.low * (1 - self.band), zs.high * (1 + self.band)
        if st.close < lo or st.close > hi:
            st.reason = "价格已离开中枢区间"
            return st

        # 触摸计数: 中枢形成以来 笔/合并K线 触及两侧的次数
        try:
            for bi in kl.bi_list.bi_list:
                if bi.get_end_klu().idx < begin_idx:
                    continue
                if bi._low() <= lo:
                    st.touch_low += 1
                if bi._high() >= hi:
                    st.touch_high += 1
        except Exception:
            pass

        # 中枢形成以来的K线数
        try:
            st.bars_in_zs = sum(1 for klc in kl if klc[-1].idx >= begin_idx)
        except Exception:
            st.bars_in_zs = 0

        if st.touch_low < self.min_touch or st.touch_high < self.min_touch:
            st.reason = "中枢内两侧触摸不足, 震荡未成形"
            return st

        st.active = True
        # 位置分区(三等分)
        if st.close <= zs.low + (zs.high - zs.low) / 3:
            st.in_low_band = True
            st.advice = "低吸区"
        elif st.close >= zs.high - (zs.high - zs.low) / 3:
            st.in_high_band = True
            st.advice = "高抛区"
        else:
            st.advice = "观望"
        st.reason = f"中枢震荡第{st.bars_in_zs}K, 两侧各摸{min(st.touch_low, st.touch_high)}+次"
        return st
