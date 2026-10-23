"""
均线强弱辅助 — 抓强势趋势 / 过滤逆势信号

【原文出处】《市场哲学的数学原理》(缠中说禅) 第106课《走势的强弱与均线系统》:
  均线是走势"强弱"的直观辅助 —— 多头排列(短期均线在上、长期在下、依次发散)
  代表走势强、趋势健康; 空头排列代表走势弱。缠论以结构(中枢/背驰)为主、
  均线为辅: 均线用来确认"这段走势强不强、值不值得顺势持有"。

【为什么需要均线辅助】
  缠论的背驰是"反转"信号，天生对强单边趋势不友好: 一段健康的强势上涨里，
  每次次级别回调都可能被结构判为顶背驰，从而过早离场或逆势开空。用均线系统
  给"走势强弱"打分，可以在强势多头排列时抑制逆势做空、强化顺势持有，
  把结构信号与趋势强度结合，更稳地"抓强势趋势"。

【算法实现思路】
  在操作级别上取最近若干根合并K线的收盘价, 计算三条均线(默认 5/10/20):
    - 多头排列: ma_short > ma_mid > ma_long 且 close > ma_short → 强势上涨;
    - 空头排列: ma_short < ma_mid < ma_long 且 close < ma_short → 强势下跌;
    - 均线斜率: 用 ma_short 的一阶差分判断上行/下行;
    - strength ∈ [-1, 1]: 综合排列与价距均线的偏离, 正=偏强多, 负=偏强空。
  输出 MATrendState, 供策略层做"逆势信号否决 + 顺势持有强化"的软门控。
  数据不足(合并K线 < ma_long)时返回 neutral, 不施加任何门控。
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MATrendState:
    """均线强弱状态"""
    close: Optional[float] = None
    ma_short: Optional[float] = None
    ma_mid: Optional[float] = None
    ma_long: Optional[float] = None
    bull_alignment: bool = False      # 多头排列(强势上涨)
    bear_alignment: bool = False      # 空头排列(强势下跌)
    ma_short_rising: bool = False
    ma_short_falling: bool = False
    strength: float = 0.0             # [-1, 1] 正=偏强多, 负=偏强空
    enough_data: bool = False

    @property
    def is_neutral(self) -> bool:
        return not (self.bull_alignment or self.bear_alignment)

    def __str__(self):
        if not self.enough_data:
            return "均线:数据不足"
        tag = "多头排列" if self.bull_alignment else ("空头排列" if self.bear_alignment else "缠绕")
        return f"均线:{tag}(强弱{self.strength:+.2f})"


class MATrendEvaluator:
    """均线强弱评估器"""

    def __init__(self, short: int = 5, mid: int = 10, long: int = 20):
        self.short = short
        self.mid = mid
        self.long = long

    @staticmethod
    def _closes(chan, lv, n: int) -> List[float]:
        """取操作级别最近 n 根合并K线的收盘价(每根用其最后一个klu的close)"""
        try:
            kl = chan[lv]
        except Exception:
            return []
        total = len(kl)
        if total == 0:
            return []
        start = max(0, total - n)
        out = []
        for i in range(start, total):
            try:
                out.append(kl[i][-1].close)
            except Exception:
                continue
        return out

    @staticmethod
    def _ma(closes: List[float], n: int) -> Optional[float]:
        if len(closes) < n:
            return None
        return sum(closes[-n:]) / n

    def evaluate(self, chan, lv) -> MATrendState:
        st = MATrendState()
        # 多取几根以计算均线斜率
        need = self.long + 2
        closes = self._closes(chan, lv, need)
        if len(closes) < self.long:
            return st  # 数据不足 → neutral
        st.enough_data = True
        st.close = closes[-1]
        st.ma_short = self._ma(closes, self.short)
        st.ma_mid = self._ma(closes, self.mid)
        st.ma_long = self._ma(closes, self.long)

        # 均线斜率(用前一根的短均线对比)
        prev_short = self._ma(closes[:-1], self.short)
        if prev_short is not None and st.ma_short is not None:
            st.ma_short_rising = st.ma_short > prev_short
            st.ma_short_falling = st.ma_short < prev_short

        st.bull_alignment = (st.ma_short > st.ma_mid > st.ma_long) and (st.close > st.ma_short)
        st.bear_alignment = (st.ma_short < st.ma_mid < st.ma_long) and (st.close < st.ma_short)

        # 强弱打分: 收盘价相对长均线的偏离(以长均线归一), 截断到 [-1, 1]
        if st.ma_long:
            bias = (st.close - st.ma_long) / st.ma_long
            # 排列加成
            if st.bull_alignment:
                bias += 0.05
            elif st.bear_alignment:
                bias -= 0.05
            st.strength = max(-1.0, min(1.0, bias * 5.0))
        return st
