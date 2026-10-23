from .CEnum import BI_DIR, KL_TYPE, MACD_ALGO


def kltype_lt_day(_type):
    return _type in [KL_TYPE.K_1M, KL_TYPE.K_5M, KL_TYPE.K_15M, KL_TYPE.K_30M, KL_TYPE.K_60M]


def kltype_lte_day(_type):
    return _type in [KL_TYPE.K_1M, KL_TYPE.K_5M, KL_TYPE.K_15M, KL_TYPE.K_30M, KL_TYPE.K_60M, KL_TYPE.K_DAY]


def check_kltype_order(type_list: list):
    _dict = {
        KL_TYPE.K_1M: 1,
        KL_TYPE.K_3M: 2,
        KL_TYPE.K_5M: 3,
        KL_TYPE.K_15M: 4,
        KL_TYPE.K_30M: 5,
        KL_TYPE.K_60M: 6,
        KL_TYPE.K_DAY: 7,
        KL_TYPE.K_WEEK: 8,
        KL_TYPE.K_MON: 9,
        KL_TYPE.K_QUARTER: 10,
        KL_TYPE.K_YEAR: 11,
    }
    last_lv = float("inf")
    for kl_type in type_list:
        cur_lv = _dict[kl_type]
        assert cur_lv < last_lv, "lv_list的顺序必须从大级别到小级别"
        last_lv = cur_lv


def revert_bi_dir(dir):
    return BI_DIR.DOWN if dir == BI_DIR.UP else BI_DIR.UP


def has_overlap(l1, h1, l2, h2, equal=False):
    return h2 >= l1 and h1 >= l2 if equal else h2 > l1 and h1 > l2


def str2float(s):
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_inf(v):
    if type(v) == float:
        if v == float("inf"):
            v = 'float("inf")'
        if v == float("-inf"):
            v = 'float("-inf")'
    return v


def _dif_pullback_zero(zs, bi_in, bi_out, rel_thred=0.3):
    """
    黄白线(DIF)回抽零轴检测 (缠师第24课趋势背驰的形态前提)

    原理: 一个趋势中, 进中枢波把 DIF 拉到高位, 中枢震荡期间 DIF 应回抽到零轴附近,
      出中枢波再次拉出但力度不足 → 背驰。若中枢期间 DIF 始终远离零轴, 说明是
      单一波段的延续而非"两波比较", 不构成标准趋势背驰。
    实现: 取中枢内部所有 KLU 的 |DIF| 最小值, 若 <= rel_thred × (进/出波 DIF 幅度)
      即认为黄白线回抽到了零轴附近。无 zs 或无数据时返回 True(不额外约束, 如盘整背驰)。
    """
    if zs is None:
        return True
    difs = []
    try:
        for bi in zs.bi_lst:
            for klc in bi.klc_lst:
                for klu in klc.lst:
                    difs.append(klu.macd.DIF)
    except Exception:
        return True
    if not difs:
        return True
    min_abs_dif = min(abs(d) for d in difs)
    try:
        in_dif = abs(bi_in.cal_macd_metric(MACD_ALGO.DIF_PEAK, is_reverse=False))
        out_dif = abs(bi_out.cal_macd_metric(MACD_ALGO.DIF_PEAK, is_reverse=True))
    except Exception:
        return True
    ref = max(in_dif, out_dif, 1e-9)
    return min_abs_dif <= rel_thred * ref


def is_macd_divergence(bi_in, bi_out, macd_algo, divergence_rate, zs=None):
    """
    背驰判定统一入口 (支持复合口径)

    【原文出处】第24课《MACD对背弛的辅助判断》：缠师判背驰并非只看单一指标，
      而是"红绿柱面积 + 柱子高度(峰值) + 黄白线回抽零轴"综合判断。
    【算法实现思路】
      - 单一口径(area/peak/dif_peak/...): out_metric <= divergence_rate * in_metric 即背驰；
      - COMPOSITE(OR): 面积 或 峰值 任一衰竭即背驰(激进, 抓底多)；
      - COMPOSITE_AND: 面积 且 峰值 都衰竭才背驰(严格, 过滤假背驰)；
      - COMPOSITE_FULL: 缠师完整三要素 —— 黄白线回抽零轴(形态前提) 且 DIF峰值衰减
        且 (面积萎缩 或 柱高衰减)(力度确认)。最贴合原著"综合判断"。
      - divergence_rate > 100: 保送(强制背驰)，用于调试。

    参数:
      bi_in  : 进中枢的笔/段 (需实现 cal_macd_metric)
      bi_out : 出中枢的笔/段
      macd_algo: MACD_ALGO 枚举
      divergence_rate: 背驰阈值(默认0.9)
      zs: 所属中枢(COMPOSITE_FULL 用于黄白线回抽零轴检测; 为 None 时跳过该形态门槛)
    返回: (是否背驰: bool, out/in 比值: float|None)
    """
    def _ratio(in_m, out_m):
        return out_m / in_m if in_m else None

    if macd_algo in (MACD_ALGO.COMPOSITE, MACD_ALGO.COMPOSITE_AND):
        in_area = bi_in.cal_macd_metric(MACD_ALGO.AREA, is_reverse=False)
        out_area = bi_out.cal_macd_metric(MACD_ALGO.AREA, is_reverse=True)
        in_peak = bi_in.cal_macd_metric(MACD_ALGO.PEAK, is_reverse=False)
        out_peak = bi_out.cal_macd_metric(MACD_ALGO.PEAK, is_reverse=True)
        if divergence_rate > 100:  # 保送
            return True, _ratio(in_area, out_area)
        area_div = out_area <= divergence_rate * in_area
        peak_div = out_peak <= divergence_rate * in_peak
        # OR: 任一衰竭即背驰(激进,抓底多); AND: 两者都衰竭才背驰(严格,过滤假背驰)
        is_diver = (area_div or peak_div) if macd_algo == MACD_ALGO.COMPOSITE else (area_div and peak_div)
        return is_diver, _ratio(in_area, out_area)

    if macd_algo == MACD_ALGO.COMPOSITE_FULL:
        in_area = bi_in.cal_macd_metric(MACD_ALGO.AREA, is_reverse=False)
        out_area = bi_out.cal_macd_metric(MACD_ALGO.AREA, is_reverse=True)
        in_peak = bi_in.cal_macd_metric(MACD_ALGO.PEAK, is_reverse=False)
        out_peak = bi_out.cal_macd_metric(MACD_ALGO.PEAK, is_reverse=True)
        if divergence_rate > 100:  # 保送
            return True, _ratio(in_area, out_area)
        in_dif = abs(bi_in.cal_macd_metric(MACD_ALGO.DIF_PEAK, is_reverse=False))
        out_dif = abs(bi_out.cal_macd_metric(MACD_ALGO.DIF_PEAK, is_reverse=True))
        # 三要素
        zero_ok = _dif_pullback_zero(zs, bi_in, bi_out)      # ① 黄白线回抽零轴(形态)
        dif_div = out_dif <= divergence_rate * in_dif          # ② 黄白线峰值衰减
        area_div = out_area <= divergence_rate * in_area       # ③a 面积萎缩
        peak_div = out_peak <= divergence_rate * in_peak       # ③b 柱高衰减
        is_diver = zero_ok and dif_div and (area_div or peak_div)
        return is_diver, _ratio(in_area, out_area)

    in_metric = bi_in.cal_macd_metric(macd_algo, is_reverse=False)
    out_metric = bi_out.cal_macd_metric(macd_algo, is_reverse=True)
    if divergence_rate > 100:  # 保送
        return True, _ratio(in_metric, out_metric)
    return out_metric <= divergence_rate * in_metric, _ratio(in_metric, out_metric)


def cal_macd_slope(begin_klu, end_klu, up: bool) -> float:
    """笔/线段的价格斜率(按持续K线数归一)。Bi 与 Seg 共用同一口径。"""
    if up:
        return (end_klu.high - begin_klu.low)/end_klu.high/(end_klu.idx - begin_klu.idx + 1)
    return (begin_klu.high - end_klu.low)/begin_klu.high/(end_klu.idx - begin_klu.idx + 1)


def cal_macd_amp(begin_klu, end_klu, down: bool) -> float:
    """笔/线段的价格振幅。Bi 与 Seg 共用同一口径。"""
    if down:
        return (begin_klu.high-end_klu.low)/begin_klu.high
    return (end_klu.high-begin_klu.low)/begin_klu.low
