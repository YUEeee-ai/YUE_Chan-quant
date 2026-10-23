"""
两重表里关系 — 里级别走势与表级别结构的立体配合 (原著第91/93/99课)

【原文出处】《市场哲学的数学原理》(缠中说禅)：
  - 第91课《走势结构的两重表里关系1》: 任何级别的走势都有"表里两层"——
    本级别走势类型是"里"，构成它的次级别走势是"表"。里级别上涨由表级别的
    一段段上涨与回调拼接而成；表级别的阴线（回调）只是里级别上涨的组成部分，
    不构成里级别转折。判断表里关系就是判断"表级别的一段，是里级别的中继
    还是转折"。
  - 第93课: 以分型为表的辅助——"顶分型后能否成笔"决定了表级别阴线是
    中继还是转折的先行指标。
  - 第99课: 表里关系的操作化——里级别趋势未走完时，表级别的一切反向信号
    都按中继处理；只有里级别走势终完美 + 表级别背驰共振，才按转折处理。

【算法实现思路】
  给定 里级别 outside_lv（如周线）、表级别 inside_lv（如日线，通常=操作级别）:
    1. 里: 用中枢序列判定 outside_lv 的走势类型与是否终完美(复用 LevelLinkage
       的 LevelState 计算);
    2. 表: 对 inside_lv 做同级别分解, 取当前段方向与是否完美(复用
       SameLevelDecomposer);
    3. 关系判定(以持多视角):
       - relation='pullback'(表阴里阳): 里上涨未完美 + 表当前段为回调/下跌
         → 表级别卖点是中继 → 持有不卖出、不开逆势空;
       - relation='resonance'(表里同阳): 里上涨未完美 + 表当前段同向上涨
         → 共振强化持有;
       - relation='reversal_confirm'(转折确认): 里上涨已完美 + 表背驰
         → 允许离场/反手;
       - relation='undefined': 结构不足, 不施加意见。
  下跌方向完全镜像。输出 InsideOutsideState，作为独立于"级别归属"的又一条
  持有/离场判据（级别归属看"信号属于哪个级别"，表里关系看"两级结构当下
  如何配合"）。
"""
from dataclasses import dataclass
from typing import Optional

from Common.CEnum import KL_TYPE
from Trend.TrendAnalyzer import CTrendAnalyzer, ZoushiType
from Trend.TrendCommon import fetch_kl, require_valid_zs
from Trend.SameLevelDecompose import SameLevelDecomposer, current_piece


@dataclass
class InsideOutsideState:
    """两重表里关系状态"""
    inside_lv: Optional[KL_TYPE] = None     # 表级别(小)
    outside_lv: Optional[KL_TYPE] = None    # 里级别(大)
    outside_type: str = ""                  # 里级别走势类型(中文)
    outside_perfect: bool = False           # 里级别是否终完美
    inside_dir: str = ""                    # 表级别当前段方向 up/down/""
    inside_perfect: bool = False
    relation: str = "undefined"             # resonance/pullback/reversal_confirm/undefined
    allow_exit_long: bool = True
    allow_exit_short: bool = True
    allow_open_long: bool = True
    allow_open_short: bool = True
    reason: str = ""

    def __str__(self):
        if self.relation == "undefined":
            return f"表里关系:未成形({self.reason})"
        name = {"resonance": "表里共振", "pullback": "表阴里阳(中继)",
                "reversal_confirm": "转折确认"}.get(self.relation, self.relation)
        return (f"表里关系:{name} 里={self.outside_type}{'·完美' if self.outside_perfect else ''} "
                f"表={self.inside_dir or '?'} | {self.reason}")


class InsideOutsideAnalyzer:
    """两重表里关系分析器 (第91/93/99课)"""

    def __init__(self, min_trend_zs: int = 2):
        self.min_trend_zs = min_trend_zs
        self._decomposer = SameLevelDecomposer(min_trend_zs)

    def analyze(self, chan, inside_lv: KL_TYPE, outside_lv: KL_TYPE, bsp_conf) -> InsideOutsideState:
        st = InsideOutsideState(inside_lv=inside_lv, outside_lv=outside_lv)
        out_kl = fetch_kl(chan, outside_lv, st, missing_reason="里级别数据缺失")
        if out_kl is None:
            return st

        # --- 里: 走势类型 + 终完美 ---
        zs_seq = require_valid_zs(out_kl, st, empty_reason="里级别无有效中枢")
        if zs_seq is None:
            return st
        zoushi_type, _ = CTrendAnalyzer.classify_by_zs_list(out_kl.zs_list.zs_lst, self.min_trend_zs)
        st.outside_type = {
            ZoushiType.UP_TREND: "上涨趋势",
            ZoushiType.DOWN_TREND: "下跌趋势",
            ZoushiType.CONSOLIDATION: "盘整",
            ZoushiType.UNDEFINED: "未完成",
        }[zoushi_type]
        st.outside_perfect = CTrendAnalyzer.is_zoushi_perfect(out_kl.zs_list.zs_lst, bsp_conf)

        # --- 表: 同级别分解当前段 ---
        try:
            pieces = self._decomposer.decompose(chan, inside_lv, bsp_conf)
            cur = current_piece(pieces)
            if cur is not None:
                st.inside_dir = cur.direction
                st.inside_perfect = cur.is_perfect
        except Exception:
            st.reason = "表级别分解失败"
            return st

        # --- 关系判定 ---
        if zoushi_type == ZoushiType.UP_TREND and not st.outside_perfect:
            if st.inside_dir == "down":
                # 表阴里阳: 表级别回调是里级别上涨的中继
                st.relation = "pullback"
                st.allow_exit_long = False
                st.allow_open_short = False
                st.reason = "里级别上涨未完美, 表级别回调为中继, 持多不卖"
            elif st.inside_dir == "up":
                st.relation = "resonance"
                st.allow_exit_long = False
                st.reason = "里级别上涨 + 表级别上涨, 共振强化持有"
            else:
                st.reason = "表级别方向未定"
        elif zoushi_type == ZoushiType.DOWN_TREND and not st.outside_perfect:
            if st.inside_dir == "up":
                st.relation = "pullback"
                st.allow_exit_short = False
                st.allow_open_long = False
                st.reason = "里级别下跌未完美, 表级别反弹为中继, 持空不平"
            elif st.inside_dir == "down":
                st.relation = "resonance"
                st.allow_exit_short = False
                st.reason = "里级别下跌 + 表级别下跌, 共振强化持空"
            else:
                st.reason = "表级别方向未定"
        else:
            # 里级别已完美/盘整/未完成 → 以表级别自身完美为准
            if st.inside_perfect:
                st.relation = "reversal_confirm"
                st.reason = "里级别不阻挡 + 表级别背驰确认, 允许按表级别转折操作"
            else:
                st.reason = "里级别盘整/已完美, 表级别进行中, 不施加意见"
        return st
