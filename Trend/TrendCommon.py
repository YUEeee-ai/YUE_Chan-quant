# -*- coding: utf-8 -*-
"""Trend 分析器共用小工具: 级别数据存取 + 有效中枢过滤

各分析器(EnergyDynamics/ZSOscillation/ReboundTrader/InsideOutside 等)的
入口都有同一组前置检查 —— 取级别 KLine、过滤单笔中枢、空结果写 reason。
收敛到这里, 新增分析器直接复用。
"""


def fetch_kl(chan, lv, state, missing_reason: str = "级别数据缺失"):
    """取某级别 KLine 列表; 级别缺失时写 state.reason 并返回 None"""
    try:
        return chan[lv]
    except Exception:
        state.reason = missing_reason
        return None


def valid_zs_list(kl) -> list:
    """过滤掉单笔中枢后的有效中枢序列"""
    return [z for z in kl.zs_list.zs_lst if not z.is_one_bi_zs()]


def require_valid_zs(kl, state, empty_reason: str = "无有效中枢"):
    """有效中枢序列; 为空时写 state.reason 并返回 None"""
    zs = valid_zs_list(kl)
    if not zs:
        state.reason = empty_reason
        return None
    return zs
