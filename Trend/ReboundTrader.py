"""
短线反弹操作 — 急跌后的抢反弹纪律 (原著第107课)

【原文出处】《市场哲学的数学原理》(缠中说禅) 第107课《如何操作短线反弹》:
  下跌趋势中的反弹是"刀口舔血"，只能短线对待：急跌之后出现的第一段次级别
  买点可以轻仓参与，但① 仓位必须小（反弹不是反转）；② 有明确目标位（上方
  最近的压力，如中枢下沿/下跌起点），到位即走；③ 有明确止损位（信号低点），
  跌破即认赔。绝不能把短线反弹仓位当成趋势仓位一直拿到"走势完美"。

【为什么需要短线反弹模块】
  级别联立/均线层的默认纪律是"高级别下跌未完成时不逆势接飞刀做多"——这对
  趋势仓是对的，但会放过第107课专门讨论的那类机会：急跌（短期超卖）后的
  技术性反弹。本模块把"急跌-买点-目标位-止损位"量化成一个独立的小仓位
  交易计划，与趋势仓完全隔离：它只在急跌到位的窗口内放行轻仓做多，
  到位/破位机械离场，不改变趋势仓的任何逻辑。

【算法实现思路】
  1. 急跌判定: 最近 drop_window 根合并K线内，收盘自区间高点回落 ≥ drop_pct
     → 进入 setup（抢反弹观察窗口），记录窗口内最低价与发生位置;
  2. 入场: setup 有效期间，操作级别出现第一类/盘整背驰买点(T1/T1P)即触发
     entry（具体触发由策略层在买卖点回调中执行，本模块提供判定与计划参数）;
  3. 目标位: 上方最近一个有效中枢的下沿（压力）；若上方无中枢，则取急跌起点
     收盘的 rebound_target_ratio（默认0.618）回撤位;
  4. 止损位: 急跌窗口最低价 × (1 - stop_buffer)，跌破认赔。
  输出 ReboundPlan(setup/entry/target/stop/drop_pct), 供策略层执行小仓位计划。
"""
from dataclasses import dataclass
from typing import Optional

from Common.CEnum import KL_TYPE
from Trend.TrendCommon import fetch_kl


@dataclass
class ReboundPlan:
    """短线反弹交易计划"""
    setup: bool = False        # 急跌窗口有效(可寻找反弹买点)
    lv: Optional[KL_TYPE] = None
    drop_pct: float = 0.0      # 自窗口高点的回落幅度(%)
    drop_bars: int = 0         # 急跌经历的K线数
    high_price: float = 0.0    # 急跌起点(窗口高点)
    low_price: float = 0.0     # 急跌窗口最低价
    low_idx: int = -1          # 最低价所在合并K线索引
    target_price: float = 0.0  # 反弹目标位(上方压力)
    stop_price: float = 0.0    # 反弹止损位(窗口最低价下方)
    reason: str = ""

    def __str__(self):
        if not self.setup:
            return f"短线反弹:无急跌窗口({self.reason})"
        return (f"短线反弹:急跌{self.drop_pct:.1f}%({self.drop_bars}K) "
                f"目标{self.target_price:.2f} 止损{self.stop_price:.2f}")


class ReboundPlanner:
    """短线反弹计划器 (第107课)"""

    def __init__(self, drop_window: int = 20, drop_pct: float = 12.0,
                 target_ratio: float = 0.618, stop_buffer: float = 0.02):
        self.drop_window = drop_window    # 急跌观察窗口(K线数)
        self.drop_pct = drop_pct          # 急跌阈值: 窗口内自高点回落百分比
        self.target_ratio = target_ratio  # 无上方中枢时的回撤目标比例
        self.stop_buffer = stop_buffer

    def plan(self, chan, lv: KL_TYPE) -> ReboundPlan:
        p = ReboundPlan(lv=lv)
        kl = fetch_kl(chan, lv, p)
        if kl is None:
            return p
        n = len(kl)
        if n < 5:
            p.reason = "K线不足"
            return p

        w = min(self.drop_window, n)
        closes = []
        for i in range(n - w, n):
            try:
                closes.append((kl[i][-1].close, kl[i][-1].idx))
            except Exception:
                continue
        if len(closes) < 5:
            p.reason = "收盘价序列不足"
            return p

        peak_price = max(c for c, _ in closes)
        p.high_price = peak_price
        cur_close = closes[-1][0]

        min_close = min(c for c, _ in closes)
        span = peak_price - min_close
        # 收复比例: 当前价从窗口最低点回升了"峰值-谷值"全振幅的多少
        recovered_ratio = (cur_close - min_close) / span if span > 0 else 0.0
        # 急跌判定: 自窗口高点回落 ≥ 阈值, 且尚未从最低点收复过半跌幅(仍在超卖区)
        drop = (peak_price / cur_close - 1) * 100 if cur_close > 0 else 0.0
        if drop < self.drop_pct:
            p.reason = f"回落{drop:.1f}% < 阈值{self.drop_pct:.0f}%"
            p.drop_pct = drop
            return p
        if recovered_ratio > 0.5:
            p.reason = f"已从低点收复{recovered_ratio * 100:.0f}%(>50%), 反弹窗口关闭"
            p.drop_pct = drop
            return p

        # 窗口内最低价与其位置
        low_price, low_idx = float("inf"), -1
        for i in range(n - w, n):
            try:
                klc_low = min(klu.low for klu in kl[i])
            except Exception:
                continue
            if klc_low < low_price:
                low_price, low_idx = klc_low, kl[i][-1].idx
        p.low_price, p.low_idx = low_price, low_idx
        p.drop_pct = drop
        # 实际下跌经历K线数: 从窗口高点位置到当前收盘的跨度(而非整个观察窗口长度)
        peak_pos = max(range(len(closes)), key=lambda i: closes[i][0])
        p.drop_bars = len(closes) - 1 - peak_pos
        p.stop_price = low_price * (1 - self.stop_buffer)

        # 目标位: 上方最近有效中枢下沿; 无则取急跌起点的 target_ratio 回撤位
        target = None
        try:
            for zs in reversed([z for z in kl.zs_list.zs_lst if not z.is_one_bi_zs()]):
                if zs.low > cur_close:
                    target = zs.low
                    break
        except Exception:
            target = None
        if target is None:
            target = low_price + (peak_price - low_price) * self.target_ratio
        p.target_price = target

        p.setup = True
        p.reason = f"急跌{drop:.1f}%后超卖, 反弹目标{target:.2f}"
        return p

    def entry_allowed(self, plan: ReboundPlan, bsp) -> bool:
        """急跌窗口内出现的买点是否可作为反弹入场点: 买点须发生在最低位之后"""
        if not plan.setup:
            return False
        try:
            if bsp.klu.idx < plan.low_idx:
                return False  # 最低点之前的买点, 不是"跌完之后"的反弹点
            return True
        except Exception:
            return False
