"""
轮动辅助 — 在一篮子标的中挑选"最强走势"

【原文出处】《市场哲学的数学原理》(缠中说禅) 第106课延伸: 走势有强弱之分，
  资金应在强势标的间轮动。轮动是"选股/选标的"层面的辅助，与单标的的缠论
  结构买卖点正交: 先用轮动在候选池里排出强弱序，再对靠前的标的跑缠论策略。

【定位】
  本模块不改动单标的回测逻辑, 只提供一个"强弱打分 + 排序"的工具, 供:
    - main_chan.py 的 rotate 模式(在候选池里选出最强的若干标的);
    - 组合层按强弱分配仓位(强者多配)。

【算法实现思路】
  strength_score(closes, window):
    - 动量: 窗口内收益率 (close[-1]/close[-window] - 1);
    - 趋势质量: 收盘价与 window 均线的偏离 + 均线斜率方向;
    - 平滑: 用窗口内日收益的均值/波动(类夏普)惩罚大起大落。
  rank_pool(price_map, window): 对每个标的算分并降序排序。
  fetch_closes(...): 直接用 DataAPI 取某标的某级别的收盘价序列(供打分)。
"""
from typing import Callable, Dict, List, Optional, Tuple


def strength_score(closes: List[float], window: int = 60) -> float:
    """
    走势强弱打分(越大越强)。closes 为按时间升序的收盘价序列。
    数据不足 window 时用现有长度, 不足 5 根直接返回 0。
    """
    if not closes or len(closes) < 5:
        return 0.0
    w = min(window, len(closes) - 1)
    if w < 1:
        return 0.0
    seg = closes[-(w + 1):]
    base = seg[0]
    last = seg[-1]
    if base <= 0:
        return 0.0
    momentum = last / base - 1.0

    # 均线偏离 + 斜率
    ma = sum(seg) / len(seg)
    ma_bias = (last - ma) / ma if ma else 0.0
    ma_slope = (seg[-1] - seg[0]) / seg[0] / len(seg)

    # 类夏普: 日收益均值 / 波动
    rets = [seg[i] / seg[i - 1] - 1.0 for i in range(1, len(seg)) if seg[i - 1] > 0]
    if rets:
        mean_r = sum(rets) / len(rets)
        var = sum((r - mean_r) ** 2 for r in rets) / len(rets)
        std = var ** 0.5
        sharpe = (mean_r / std) if std > 1e-9 else 0.0
    else:
        sharpe = 0.0

    return momentum + 0.5 * ma_bias + 5.0 * ma_slope + 0.1 * sharpe


def rank_pool(price_map: Dict[str, List[float]], window: int = 60) -> List[Tuple[str, float]]:
    """对候选池按强弱降序排序, 返回 [(symbol, score), ...]"""
    scored = [(sym, strength_score(closes, window)) for sym, closes in price_map.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def select_strongest(price_map: Dict[str, List[float]], top_n: int = 3,
                     window: int = 60, min_score: float = float("-inf")) -> List[str]:
    """选出最强的 top_n 个标的(可设最低分门槛)"""
    ranked = rank_pool(price_map, window)
    return [sym for sym, sc in ranked[:top_n] if sc >= min_score]


def fetch_closes(symbol: str, data_src, begin_time: Optional[str] = None,
                 end_time: Optional[str] = None, lv=None) -> List[float]:
    """
    用 DataAPI 直接取某标的某级别的收盘价序列(升序)。
    data_src: DATA_SRC 枚举; lv: KL_TYPE(默认日线)。失败返回 []。
    """
    from Chan import GetStockAPI
    from Common.CEnum import AUTYPE, KL_TYPE
    import sys
    lv = lv or KL_TYPE.K_DAY
    try:
        api_cls = GetStockAPI(data_src)
        api_cls.do_init()
        inst = api_cls(code=symbol, k_type=lv, begin_date=begin_time,
                       end_date=end_time, autype=AUTYPE.QFQ)
        closes = [float(klu.close) for klu in inst.get_kl_data()]
        api_cls.do_close()
        return closes
    except Exception as e:
        # 不静默吞异常: 让轮动排序里被剔除的标的可追溯到原因
        print(f"[rotation] {symbol} 取数失败, 已跳过: {e}", file=sys.stderr)
        return []
