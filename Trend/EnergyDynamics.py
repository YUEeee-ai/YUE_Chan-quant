"""
能量动力结构 — 走势的能量度量与能量背驰 (原著第104课)

【原文出处】《市场哲学的数学原理》(缠中说禅) 第104课《几何结构与能量动力结构》:
  缠论自称"未竟"的一篇：走势不只有几何结构（分型/笔/线段/中枢），还有
  能量动力结构 —— 推动走势运行的"力度"。几何上价格创新高但推动能量一段比
  一段弱，就是"能量背驰"，它常常先于几何背驰出现，是更原始的衰竭信号。
  原文以 MACD 红绿柱的面积/高度作为能量的近似度量。

【算法实现思路】
  以 MACD 能量近似动力（红绿柱 |macd| 沿走势段的累积）:
    1. energy(bi): 笔内全部K线 Σ|macd柱|; MACD 缺失时退化用 Σ|收盘变动|;
    2. 进出能量比: 大级别末中枢 bi_out 能量 / bi_in 能量 → last_ratio;
    3. 能量背驰 divergence_energy: 离开段把价格推过进入段极值（顺势新极值），
       但能量比 < decay_threshold（默认0.8，即能量衰减超20%）→ 价格与能量背离;
    4. 输出 EnergyState(含同向段能量序列 trend_energy_seq 供外部分析)。
  策略层用法: 能量背驰是【许可性】信号——允许顺势仓在几何卖点被门控挡住时
  提前离场（能量先于结构衰竭），并否决在能量背驰方向的追势开仓；它从不是
  阻挡性信号，不干预"持有"逻辑。
"""
from dataclasses import dataclass, field
from typing import List, Optional

from Common.CEnum import KL_TYPE
from Trend.TrendCommon import fetch_kl, require_valid_zs


@dataclass
class EnergyState:
    """能量动力状态"""
    lv: Optional[KL_TYPE] = None
    last_ratio: Optional[float] = None     # 末中枢离开段/进入段能量比
    energy_in: float = 0.0                 # 进入段能量
    energy_out: float = 0.0                # 离开段能量
    divergence_energy: bool = False        # 能量背驰(价格新极值 + 能量衰减)
    divergence_down: Optional[bool] = None # 能量背驰方向: True=下跌侧(空头衰竭)/False=上涨侧
    trend_energy_seq: List[float] = field(default_factory=list)  # 相邻中枢进出比序列
    reason: str = ""

    def __str__(self):
        if self.last_ratio is None:
            return f"能量动力:无数据({self.reason})"
        return (f"能量动力:进出比{self.last_ratio:.2f} "
                f"{'能量背驰!' if self.divergence_energy else '能量正常'} | {self.reason}")


class EnergyEvaluator:
    """能量动力评估器 (第104课)"""

    def __init__(self, decay_threshold: float = 0.8):
        self.decay_threshold = decay_threshold

    @staticmethod
    def _bi_energy(bi) -> float:
        """一笔的能量: Σ|MACD柱|, 无MACD则退化 Σ|K线收盘变动|"""
        total = 0.0
        has_macd = False
        try:
            for klc in bi.klc_lst:
                for klu in klc.lst:
                    m = getattr(klu, "macd", None)
                    if m is not None:
                        total += abs(m.macd)
                        has_macd = True
        except Exception:
            pass
        if has_macd:
            return total
        # 退化: 价格位移能量
        try:
            prev = bi.get_begin_klu().close
            for klc in bi.klc_lst:
                for klu in klc.lst:
                    total += abs(klu.close - prev)
                    prev = klu.close
        except Exception:
            total += abs(bi.get_end_val() - bi.get_begin_val())
        return total

    def evaluate(self, chan, lv: KL_TYPE) -> EnergyState:
        st = EnergyState(lv=lv)
        kl = fetch_kl(chan, lv, st)
        if kl is None:
            return st

        valid_zs = require_valid_zs(kl, st)
        if valid_zs is None:
            return st

        # 相邻中枢进出能量比序列(最多最近5个中枢)
        ratios: List[float] = []
        for zs in valid_zs[-5:]:
            if zs.bi_in is None or zs.bi_out is None:
                continue
            try:
                e_in = self._bi_energy(zs.bi_in)
                e_out = self._bi_energy(zs.bi_out)
            except Exception:
                continue
            if e_in > 0:
                ratios.append(e_out / e_in)
        st.trend_energy_seq = ratios
        if not ratios:
            st.reason = "中枢缺少进/出段"
            return st

        last_zs = valid_zs[-1]
        if last_zs.bi_in is not None and last_zs.bi_out is not None:
            st.energy_in = self._bi_energy(last_zs.bi_in)
            st.energy_out = self._bi_energy(last_zs.bi_out)
            st.last_ratio = st.energy_out / st.energy_in if st.energy_in > 0 else None

        # 能量背驰: 离开段创出顺势新极值, 但能量比低于阈值
        if st.last_ratio is not None and st.last_ratio < self.decay_threshold \
                and last_zs.bi_out is not None and last_zs.bi_in is not None:
            try:
                if last_zs.bi_out.is_down():
                    st.divergence_energy = bool(last_zs.bi_out._low() < last_zs.bi_in._low())
                    st.divergence_down = True
                else:
                    st.divergence_energy = bool(last_zs.bi_out._high() > last_zs.bi_in._high())
                    st.divergence_down = False
            except Exception:
                st.divergence_energy = False
        if st.divergence_energy:
            st.reason = f"离开段新极值但能量比{st.last_ratio:.2f}<{self.decay_threshold}(能量背驰)"
        elif st.last_ratio is not None:
            st.reason = f"能量比{st.last_ratio:.2f}"
        return st
