"""
缠论多市场量化交易 — 主入口
====================================
严格遵循《市场哲学的数学原理》(缠中说禅) 的操作规则, 并叠加十层"级别/走势"纪律:
  ① 日→周→月多级别联立 + 跨级别背驰归属        ⑥ 中枢震荡监视器(高抛低吸, 第92课)
  ② 同级别分解                                  ⑦ 短线反弹(急跌抢反弹, 第107课)
  ③ 中阴阶段                                    ⑧ 两重表里关系(第91/93/99课)
  ④ 均线强弱 / 轮动辅助                         ⑨ 多重赋格(多级别同步分解, 第40课)
  ⑤ 小转大(小级别背驰引发大级别转折, 第44课)     ⑩ 能量动力结构(第104课)
十层均可独立开关(--no-xxx), 互不影响, 可做逐项对照实验。

支持市场(统一走 yfinance, 按代码后缀路由市场规则):
    美股  AAPL / MSFT / SPY        (支持做空, T+0)
    港股  0700.HK / 9988.HK        (支持做空, T+0, 双边印花税)
    A股   600519.SS / 000001.SZ    (禁做空, T+1, 一手100股)
    加密  BTC/USDT (ccxt)          (支持做空, T+0)

模式:
    analyze   — 结构分析: 缠论结构 + 多级别走势 + 同级别分解 + 中阴 + 均线强弱
    backtest  — 回测: 多空双向 + 市场规则 + 十层级别纪律
    rotate    — 轮动: 在候选池里按走势强弱排序, 选出最强标的
    live      — 实盘/模拟盘 (根据 --broker 选择 Alpaca/Futu)

示例:
    python main_chan.py --mode analyze  --symbol AAPL --lv month,week,day
    python main_chan.py --mode backtest --symbol 0700.HK --start 2019-01-01 --end 2024-12-31
    python main_chan.py --mode backtest --symbol 600519.SS --start 2020-01-01
    python main_chan.py --mode rotate   --symbols AAPL,MSFT,NVDA,0700.HK,600519.SS
    python main_chan.py --mode live     --symbol AAPL --broker alpaca --paper
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Chan import CChan
from ChanConfig import CChanConfig, DEFAULT_ALGO_CONFIG
from Common.CEnum import AUTYPE, DATA_SRC, KL_TYPE
from Common.MarketCapability import (
    MARKET, detect_market, get_market_capability,
)
from Strategy.ChanStrategy import ChanStrategy, ChanNestedStrategy, StrategyConfig
from Strategy.Backtester import Backtester
from Trend.SameLevelDecompose import SameLevelDecomposer, current_piece
from Trend.MiddleYin import MiddleYinDetector
from Trend.MATrend import MATrendEvaluator
from Trend.LevelLinkage import MultiLevelContext


# CLI 参数 → 内部枚举
_MARKET_MAP = {
    "cn": MARKET.CN, "hk": MARKET.HK, "us": MARKET.US, "crypto": MARKET.CRYPTO,
}
_DATA_SRC_MAP = {
    "yfinance": DATA_SRC.US_STOCK,   # 美/港/A 三市统一取数(推荐)
    "us_stock": DATA_SRC.US_STOCK,   # 兼容旧名
    "bao_stock": DATA_SRC.BAO_STOCK,
    "ccxt": DATA_SRC.CCXT,
}
_AUTYPE_MAP = {"none": AUTYPE.NONE, "qfq": AUTYPE.QFQ, "hfq": AUTYPE.HFQ}

# CLI 级别字符串 → KL_TYPE (日→周→月 层级)
_LV_MAP = {
    "year": KL_TYPE.K_YEAR, "quarter": KL_TYPE.K_QUARTER, "month": KL_TYPE.K_MON,
    "week": KL_TYPE.K_WEEK, "day": KL_TYPE.K_DAY, "60m": KL_TYPE.K_60M,
    "30m": KL_TYPE.K_30M, "15m": KL_TYPE.K_15M, "5m": KL_TYPE.K_5M, "1m": KL_TYPE.K_1M,
}
# 区间套: 操作级别 → 默认次级别(精确入场)
_SUB_LV_MAP = {
    KL_TYPE.K_DAY: KL_TYPE.K_30M,
    KL_TYPE.K_WEEK: KL_TYPE.K_DAY,
    KL_TYPE.K_MON: KL_TYPE.K_WEEK,
    KL_TYPE.K_60M: KL_TYPE.K_15M,
    KL_TYPE.K_30M: KL_TYPE.K_5M,
}


def _resolve_levels(args):
    """
    解析 --lv (逗号分隔, 从大到小), 返回 (lv_list_full, operating_lv, nested_lv)
      --lv month,week,day → 结构级别[月,周,日], 操作级别=日
      叠加 --nested 时, 在操作级别之下再挂一个次级别(如日→30分)用于区间套精确入场。
    """
    names = [s.strip().lower() for s in args.lv.split(",") if s.strip()]
    if not names:
        names = ["day"]
    struct_lv = [_LV_MAP[n] for n in names]        # 必须从大到小
    operating_lv = struct_lv[-1]                    # 最小结构级别 = 信号级别
    nested_lv = []
    lv_list_full = list(struct_lv)
    if args.nested:
        sub = _SUB_LV_MAP.get(operating_lv)
        if sub is not None and sub not in lv_list_full:
            lv_list_full.append(sub)
            nested_lv = [sub]
    return lv_list_full, operating_lv, nested_lv


def _resolve(args):
    """根据 CLI 参数解析 (data_src, market, capability)"""
    data_src = _DATA_SRC_MAP[args.data_src]
    market = _MARKET_MAP[args.market] if args.market else detect_market(data_src, args.symbol)
    cap = get_market_capability(market)
    return data_src, market, cap


def _build_strategy_config(args, cap, operating_lv, lv_list_full, nested_lv) -> StrategyConfig:
    """根据 CLI + 市场能力构建策略配置(含十层级别纪律开关)"""
    # A 股等不支持做空的市场: 强制 enable_short=False
    enable_short = (not args.no_short) and cap.support_short
    return StrategyConfig(
        operating_lv=operating_lv,
        lv_list=lv_list_full,
        nested_lv=nested_lv,
        min_trend_zs=2,
        divergence_rate=args.div_rate,
        position_l1=0.3,
        position_l2=0.4,
        position_l3=0.3,
        stop_buffer=0.02,
        require_fx_confirm=not args.no_fx_confirm,
        enable_short=enable_short,
        only_trend_bsp1=not args.loose,
        cooldown_bars=5,
        # ① 多级别联立 + 跨级别背驰归属
        use_level_linkage=not args.no_level_linkage,
        # ② 同级别分解
        use_same_level_decompose=not args.no_decompose,
        # ③ 中阴阶段
        use_middle_yin=not args.no_middle_yin,
        middle_yin_scale=args.middle_yin_scale,
        middle_yin_max_bars=args.middle_yin_max_bars,
        # ④ 均线强弱
        use_ma_filter=not args.no_ma,
        ma_short=args.ma_short, ma_mid=args.ma_mid, ma_long=args.ma_long,
        # ⑤ 小转大 (第44课)
        use_small_turn_big=not args.no_small_turn_big,
        small_turn_big_scale=args.stb_scale,
        # ⑥ 中枢震荡监视器 (第92课)
        use_zs_oscillation=not args.no_zs_oscillation,
        zs_osc_scale=args.zs_osc_scale,
        # ⑦ 短线反弹 (第107课)
        use_rebound=not args.no_rebound,
        rebound_scale=args.rebound_scale,
        rebound_drop_pct=args.rebound_drop_pct,
        rebound_window=args.rebound_window,
        # ⑧ 两重表里关系 (第91/93/99课)
        use_inside_outside=not args.no_inside_outside,
        # ⑨ 多重赋格 (第40课)
        use_fugue=not args.no_fugue,
        fugue_boost=args.fugue_boost,
        # ⑩ 能量动力结构 (第104课, 默认关闭, RESEARCH 第十二节)
        use_energy=args.use_energy,
        energy_decay=args.energy_decay,
        energy_veto_only=args.energy_veto_only,
    )


def _chan_config_dict(args, triger_step: bool) -> dict:
    return {
        "triger_step": triger_step,
        "divergence_rate": args.div_rate,
        "min_zs_cnt": 1,
        "max_kl_misalgin_cnt": args.max_misalign,
        **DEFAULT_ALGO_CONFIG,
    }


def _to_futu_code(symbol: str) -> str:
    """统一 yfinance 后缀风格代码 → 富途前缀风格代码 (run_live --broker futu 用)"""
    s = (symbol or "").upper()
    if s.endswith(".HK"):
        return "HK." + s[:-3].zfill(5)
    if s.endswith(".SS") or s.endswith(".SH"):
        return "SH." + s[:-3]
    if s.endswith(".SZ"):
        return "SZ." + s[:-3]
    if "." not in s and "/" not in s and s.isalpha():
        return "US." + s
    return s  # 已是前缀风格 / 加密交易对等, 原样返回


def _dormant_layer_warning(strategy_config, lv_list_full):
    """⑤小转大/⑧表里关系/①级别联立 依赖多级别: 单级别运行时它们休眠, 给出提示"""
    if len(lv_list_full) >= 2:
        return
    dormant = []
    if getattr(strategy_config, "use_level_linkage", False):
        dormant.append("①级别联立")
    if getattr(strategy_config, "use_small_turn_big", False):
        dormant.append("⑤小转大")
    if getattr(strategy_config, "use_inside_outside", False):
        dormant.append("⑧表里关系")
    if getattr(strategy_config, "use_fugue", False):
        dormant.append("⑨多重赋格(单声部退化)")
    if dormant:
        print(f"  [提示] 当前仅单级别({'>'.join(lv.name for lv in lv_list_full)}), "
              f"以下级别纪律休眠: {', '.join(dormant)}; 用 --lv week,day 传多级别方可生效\n")


def run_backtest(args):
    data_src, market, cap = _resolve(args)
    lv_list_full, operating_lv, nested_lv = _resolve_levels(args)
    strategy_config = _build_strategy_config(args, cap, operating_lv, lv_list_full, nested_lv)

    print(f"\n{'='*60}")
    print(f"  缠论策略回测 | {args.symbol} [{cap.name}]")
    print(f"  区间: {args.start} ~ {args.end or 'now'}")
    print(f"  级别: {'>'.join(lv.name for lv in lv_list_full)} | 操作级别: {operating_lv.name}")
    print(f"  做空: {'ON (多空对称)' if strategy_config.enable_short else 'OFF (' + ('市场不支持' if not cap.support_short else '用户禁用') + ')'}")
    print(f"  T+0: {'是' if cap.t_plus_0 else '否 (T+1约束生效)'} | Lot: {cap.lot_size} | 佣金: {cap.commission_rate*10000:.2f}bp")
    layers = [n for n, on in [("级别联立", strategy_config.use_level_linkage),
                              ("同级别分解", strategy_config.use_same_level_decompose),
                              ("中阴", strategy_config.use_middle_yin),
                              ("均线", strategy_config.use_ma_filter),
                              ("小转大", strategy_config.use_small_turn_big),
                              ("中枢震荡", strategy_config.use_zs_oscillation),
                              ("短线反弹", strategy_config.use_rebound),
                              ("表里关系", strategy_config.use_inside_outside),
                              ("多重赋格", strategy_config.use_fugue),
                              ("能量动力", strategy_config.use_energy)] if on]
    print(f"  启用纪律: {' + '.join(layers) if layers else '(仅基础三类买卖点)'}")
    print(f"{'='*60}\n")

    _dormant_layer_warning(strategy_config, lv_list_full)

    bt = Backtester(
        code=args.symbol,
        begin_time=args.start,
        end_time=args.end,
        data_src=data_src,
        lv_list=lv_list_full,
        chan_config={"max_kl_misalgin_cnt": args.max_misalign},
        strategy_config=strategy_config,
        initial_capital=args.capital,
        market=market,
        autype=_AUTYPE_MAP[args.autype],
        use_nested=bool(nested_lv),
    )
    result = bt.run()
    bt.print_report(result)

    if args.plot:
        trades_png, equity_png = bt.plot(result, x_range=args.plot_x_range)
        print(f"\n[图表已保存] 结构+成交标记: {trades_png}")
        print(f"[图表已保存] 资金曲线+回撤: {equity_png}")


def run_analyze(args):
    data_src, market, cap = _resolve(args)
    lv_list_full, operating_lv, nested_lv = _resolve_levels(args)
    autype = AUTYPE.NONE if (args.autype == "none" and market == MARKET.US) else _AUTYPE_MAP[args.autype]

    print(f"\n{'='*60}")
    print(f"  缠论结构分析 | {args.symbol} [{cap.name}]")
    print(f"  级别: {'>'.join(lv.name for lv in lv_list_full)} | 操作级别: {operating_lv.name}")
    print(f"{'='*60}\n")

    conf = CChanConfig(_chan_config_dict(args, triger_step=False))
    chan = CChan(
        code=args.symbol, begin_time=args.start, end_time=args.end,
        data_src=data_src, lv_list=lv_list_full, config=conf, autype=autype,
    )

    # 操作级别结构
    kl = chan[operating_lv]
    print(f"[操作级别 {operating_lv.name}]")
    print(f"  合并K线: {len(kl)} | 笔: {len(kl.bi_list)} | 线段: {len(kl.seg_list)}")
    print(f"  笔中枢: {len(kl.zs_list.zs_lst)} | 段中枢: {len(kl.segzs_list.zs_lst)}")
    bsp_list = sorted(kl.bs_point_lst.lst, key=lambda x: x.klu.time)
    print(f"  买卖点: {len(bsp_list)}  最近5个:")
    for bsp in bsp_list[-5:]:
        direction = "买" if bsp.is_buy else "卖"
        print(f"    {bsp.klu.time} | {direction} | 类型={bsp.type2str()} | 价={bsp.klu.close:.2f}")

    # ① 多级别联立 + 跨级别背驰归属
    bsp_conf = chan.conf.bs_point_conf.GetBSConfig(False)
    ml = MultiLevelContext(lv_list_full, operating_lv, 2).update(chan, bsp_conf)
    print(f"\n[① 多级别联立]")
    for lv in lv_list_full:
        st = ml.state(lv)
        if st is not None:
            print(f"    {st}")
    if ml.higher_levels():
        for is_buy, tag in ((True, "买点(看涨反转)"), (False, "卖点(看跌反转)")):
            attr = ml.attribute_reversal(is_buy)
            print(f"    {tag} 归属 → 级别={attr.effective_lv.name} 背书={attr.endorsed_by_higher} "
                  f"离场={attr.allow_exit} 开仓={attr.allow_open} 做空={attr.allow_short} | {attr.reason}")

    # ② 同级别分解
    pieces = SameLevelDecomposer(2).decompose(chan, operating_lv, bsp_conf)
    print(f"\n[② 同级别分解] 共 {len(pieces)} 段, 最近5段:")
    for p in pieces[-5:]:
        print(f"    {p} {p.begin_time or ''} ~ {p.end_time or ''}")
    cur = current_piece(pieces)
    if cur is not None:
        print(f"    当前段: {cur} → {'已完成(边界可操作)' if cur.is_perfect else '进行中(顺势持有)'}")

    # ③ 中阴阶段
    myin = MiddleYinDetector().detect(chan, operating_lv, max_bars=args.middle_yin_max_bars)
    print(f"\n[③ 中阴阶段] {myin}")

    # ④ 均线强弱
    ma = MATrendEvaluator(args.ma_short, args.ma_mid, args.ma_long).evaluate(chan, operating_lv)
    print(f"[④ 均线强弱] {ma}")

    # ⑤ 小转大 (第44课): 父级别+次级别(--nested 下挂次级别后生效)
    from Trend.SmallTurnBig import SmallTurnBigDetector
    op_idx = len(lv_list_full) - 1 - len(nested_lv)
    parent_lv = lv_list_full[op_idx - 1] if op_idx >= 1 else None
    sub_lv = nested_lv[0] if nested_lv else None
    if parent_lv is not None and sub_lv is not None:
        bsp_conf_buy = chan.conf.bs_point_conf.GetBSConfig(True)
        det = SmallTurnBigDetector()
        print(f"\n[⑤ 小转大] 大级别={parent_lv.name} 次级别={sub_lv.name}")
        print(f"    向上: {det.detect_buy(chan, parent_lv, sub_lv, bsp_conf_buy)}")
        print(f"    向下: {det.detect_sell(chan, parent_lv, sub_lv, bsp_conf)}")
    else:
        print("\n[⑤ 小转大] 需 --lv 提供父级别 + --nested 下挂次级别(如 --lv week,day --nested)")

    # ⑥ 中枢震荡监视器 (第92课)
    from Trend.ZSOscillation import ZSOscillationMonitor
    print(f"[⑥ 中枢震荡] {ZSOscillationMonitor().detect(chan, operating_lv)}")

    # ⑦ 短线反弹 (第107课)
    from Trend.ReboundTrader import ReboundPlanner
    print(f"[⑦ 短线反弹] {ReboundPlanner(drop_window=args.rebound_window, drop_pct=args.rebound_drop_pct).plan(chan, operating_lv)}")

    # ⑧ 两重表里关系 (第91/93/99课)
    from Trend.InsideOutside import InsideOutsideAnalyzer
    if parent_lv is not None:
        io = InsideOutsideAnalyzer().analyze(chan, operating_lv, parent_lv, bsp_conf)
        print(f"[⑧ 表里关系] {io}")
    else:
        print("[⑧ 表里关系] 需 --lv 提供里级别(如 --lv week,day)")

    # ⑨ 多重赋格 (第40课)
    from Trend.FugueDecompose import FugueDecomposer
    print(f"[⑨ 多重赋格] {FugueDecomposer().decompose(chan, lv_list_full, bsp_conf)}")

    # ⑩ 能量动力 (第104课)
    from Trend.EnergyDynamics import EnergyEvaluator
    print(f"[⑩ 能量动力] {EnergyEvaluator(args.energy_decay).evaluate(chan, operating_lv)}")

    if args.plot:
        from Plot.PlotDriver import CPlotDriver
        plot_config = {
            "plot_kline": True, "plot_kline_combine": True,
            "plot_bi": True, "plot_seg": True, "plot_zs": True,
            "plot_macd": True, "plot_bsp": True,
        }
        plot_para = {"figure": {"x_range": 200}}
        plot_driver = CPlotDriver(chan, plot_config=plot_config, plot_para=plot_para)
        fname = f"{args.symbol.replace('/', '_').replace('.', '_')}_chan.png"
        plot_driver.figure.savefig(fname, dpi=150, bbox_inches='tight')
        print(f"\n[图表已保存: {fname}]")


def run_rotate(args):
    """④ 轮动: 在候选池里按走势强弱排序"""
    from Strategy.Rotation import fetch_closes, rank_pool

    data_src = _DATA_SRC_MAP[args.data_src]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("[rotate] 请用 --symbols 提供候选池, 如 --symbols AAPL,MSFT,0700.HK")
        return

    print(f"\n{'='*60}")
    print(f"  轮动强弱排序 | 候选 {len(symbols)} 只 | 窗口 {args.rotate_window} 根")
    print(f"  区间: {args.start} ~ {args.end or 'now'}")
    print(f"{'='*60}")

    price_map = {}
    for sym in symbols:
        closes = fetch_closes(sym, data_src, args.start, args.end, lv=KL_TYPE.K_DAY)
        if closes:
            price_map[sym] = closes
        else:
            print(f"  [跳过] {sym}: 无数据")

    if not price_map:
        print("[rotate] 没有任何标的取到数据")
        return

    ranked = rank_pool(price_map, window=args.rotate_window)
    print(f"\n  {'排名':<4}{'代码':<14}{'市场':<8}{'强弱分':>10}{'区间涨幅':>12}")
    print("  " + "-" * 52)
    for i, (sym, score) in enumerate(ranked, 1):
        mkt = get_market_capability(detect_market(data_src, sym)).name
        closes = price_map[sym]
        w = min(args.rotate_window, len(closes) - 1)
        chg = (closes[-1] / closes[-(w + 1)] - 1) * 100 if w >= 1 else 0.0
        print(f"  {i:<4}{sym:<14}{mkt:<8}{score:>10.3f}{chg:>11.1f}%")
    top = [s for s, _ in ranked[:args.rotate_top]]
    print(f"\n  最强 {args.rotate_top} 只: {', '.join(top)}")


def run_live(args):
    data_src, market, cap = _resolve(args)
    lv_list_full, operating_lv, nested_lv = _resolve_levels(args)
    strategy_config = _build_strategy_config(args, cap, operating_lv, lv_list_full, nested_lv)

    print(f"\n{'='*60}")
    print(f"  缠论实盘交易 | {args.symbol} [{cap.name}] | "
          f"{'模拟盘' if args.paper else '⚠️ 实盘'} | 券商: {args.broker}")
    print(f"{'='*60}\n")

    _dormant_layer_warning(strategy_config, lv_list_full)

    from Trade.Base import ChanTradeExecutor, TradeMode
    mode = TradeMode.PAPER if args.paper else TradeMode.LIVE

    # 数据侧统一用 yfinance 风格 args.symbol; 交易侧按券商代码格式转换
    if args.broker == "alpaca":
        from Trade.AlpacaTrade import AlpacaTrader
        trader = AlpacaTrader(mode=mode)
        trade_symbol = args.symbol
    elif args.broker == "futu":
        from Trade.FutuTrade import FutuTrader
        trader = FutuTrader(mode=mode)
        trade_symbol = _to_futu_code(args.symbol)
        if trade_symbol != args.symbol:
            print(f"[代码路由] {args.symbol} → 富途格式 {trade_symbol}")
    else:
        raise ValueError(f"未知 broker: {args.broker}")

    autype = AUTYPE.NONE if market == MARKET.US else AUTYPE.QFQ
    chan = CChan(
        code=args.symbol, begin_time=args.start, end_time=None,
        data_src=data_src, lv_list=lv_list_full, config=CChanConfig(_chan_config_dict(args, True)),
        autype=autype,
    )

    if nested_lv and len(lv_list_full) > 1:
        strategy = ChanNestedStrategy(strategy_config, market_cap=cap)
    else:
        strategy = ChanStrategy(strategy_config, market_cap=cap)

    executor = ChanTradeExecutor(
        trader=trader, symbol=trade_symbol,
        max_position_value=args.capital, dry_run=args.dry_run,
        market_cap=cap,
    )

    print("[START] 开始逐K线分析...")
    for snapshot in chan.step_load():
        try:
            current_price = snapshot[operating_lv][-1][-1].close
        except Exception:
            continue
        stop = strategy.check_stop_loss(current_price)
        if stop and executor.execute(stop):
            strategy.apply_stop(stop)
        record = strategy.on_bar(snapshot)
        if record:
            executor.execute(record)

    print("\n[END] 分析完成")
    positions = trader.get_positions()
    print(f"[持仓] {positions if positions else '空仓'}")


def main():
    parser = argparse.ArgumentParser(
        description="缠论多市场量化交易 — A股/港股/美股/加密货币",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 结构分析(多级别 + 十层纪律)
  python main_chan.py --mode analyze --symbol AAPL --lv month,week,day
  python main_chan.py --mode analyze --symbol 0700.HK --lv week,day

  # 回测(任意市场任意区间, 自动识别市场规则)
  python main_chan.py --mode backtest --symbol AAPL --start 2022-01-01 --end 2024-12-31
  python main_chan.py --mode backtest --symbol 0700.HK --start 2019-01-01
  python main_chan.py --mode backtest --symbol 600519.SS --start 2020-01-01
  python main_chan.py --mode backtest --symbol AAPL --lv month,week,day   # 三级联立
  python main_chan.py --mode backtest --symbol NVDA --no-short            # 强制仅做多

  # 轮动(候选池强弱排序)
  python main_chan.py --mode rotate --symbols AAPL,MSFT,NVDA,0700.HK,600519.SS

  # 实盘
  python main_chan.py --mode live --symbol AAPL --broker alpaca --paper
        """
    )
    parser.add_argument("--mode", choices=["backtest", "live", "analyze", "rotate"], default="analyze")
    parser.add_argument("--symbol", "-s", type=str, default="AAPL",
                        help="代码 (AAPL / 0700.HK / 600519.SS / sz.000001 / BTC/USDT)")
    parser.add_argument("--symbols", type=str, default="",
                        help="轮动候选池(逗号分隔), 仅 rotate 模式")
    parser.add_argument("--data-src", choices=list(_DATA_SRC_MAP.keys()), default="yfinance",
                        help="数据源 (yfinance=美/港/A股 / bao_stock=A股 / ccxt=加密)")
    parser.add_argument("--market", choices=list(_MARKET_MAP.keys()), default=None,
                        help="市场(默认按代码后缀自动检测: cn/hk/us/crypto)")
    parser.add_argument("--autype", choices=list(_AUTYPE_MAP.keys()), default="none",
                        help="复权 (none/qfq前复权/hfq后复权)")
    parser.add_argument("--broker", choices=["alpaca", "futu"], default="alpaca",
                        help="券商 (仅 live 模式)")
    parser.add_argument("--lv", type=str, default="day",
                        help="联立级别(逗号,从大到小): month,week,day / week,day / day")
    parser.add_argument("--start", type=str, default="2020-01-01")
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--capital", type=float, default=100000)
    parser.add_argument("--div-rate", type=float, default=0.9)
    parser.add_argument("--max-misalign", type=int, default=2,
                        help="多级别对齐容差: 允许'次级别找不到K线'的最大次数(默认2; 港股/A股月周日历错位多时可调大, 如 200)")
    parser.add_argument("--nested", action="store_true", help="启用区间套(操作级别下挂次级别精确定位)")
    parser.add_argument("--loose", action="store_true", help="宽松模式(允许盘整背驰产生一类)")
    parser.add_argument("--no-short", action="store_true", help="禁用做空(A股默认禁用)")
    parser.add_argument("--no-fx-confirm", action="store_true", help="关闭分型确认(BSP即刻入场)")
    # 前四层纪律开关(⑤~⑩见下方新增六层开关)
    parser.add_argument("--no-level-linkage", action="store_true", help="关闭①多级别联立/背驰归属")
    parser.add_argument("--no-decompose", action="store_true", help="关闭②同级别分解")
    parser.add_argument("--no-middle-yin", action="store_true", help="关闭③中阴阶段降权")
    parser.add_argument("--no-ma", action="store_true", help="关闭④均线强弱门控")
    parser.add_argument("--middle-yin-scale", type=float, default=0.5, help="中阴期新开仓缩放(0~1)")
    parser.add_argument("--middle-yin-max-bars", type=int, default=30, help="中阴最长时限(K线数)")
    parser.add_argument("--ma-short", type=int, default=5)
    parser.add_argument("--ma-mid", type=int, default=10)
    parser.add_argument("--ma-long", type=int, default=20)
    # 新增六层开关 (默认全开, 均可独立关闭做对照)
    parser.add_argument("--no-small-turn-big", action="store_true", help="关闭⑤小转大(第44课)放行")
    parser.add_argument("--no-zs-oscillation", action="store_true", help="关闭⑥中枢震荡高抛低吸(第92课)")
    parser.add_argument("--no-rebound", action="store_true", help="关闭⑦短线反弹(第107课)")
    parser.add_argument("--no-inside-outside", action="store_true", help="关闭⑧两重表里关系(第91/93/99课)")
    parser.add_argument("--no-fugue", action="store_true", help="关闭⑨多重赋格(第40课)")
    parser.add_argument("--use-energy", action="store_true", help="开启⑩能量动力结构(第104课, 默认关闭; 开启时可配 --energy-veto-only)")
    parser.add_argument("--stb-scale", type=float, default=0.3, help="⑤小转大早期反转仓缩放")
    parser.add_argument("--zs-osc-scale", type=float, default=0.3, help="⑥中枢震荡低吸高抛仓位缩放")
    parser.add_argument("--rebound-scale", type=float, default=0.2, help="⑦短线反弹仓位比例")
    parser.add_argument("--rebound-drop-pct", type=float, default=12.0, help="⑦急跌阈值(窗口内回落%%)")
    parser.add_argument("--rebound-window", type=int, default=20, help="⑦急跌观察窗口(K线数)")
    parser.add_argument("--fugue-boost", type=float, default=1.25, help="⑨声部齐奏时的仓位加权")
    parser.add_argument("--energy-decay", type=float, default=0.8, help="⑩能量背驰阈值(进出能量比)")
    parser.add_argument("--energy-veto-only", action="store_true", help="⑩变体: 只否决追势开仓, 不允许提前离场(更贴原作, 需配合--use-energy类开关开启⑩)")
    # 轮动
    parser.add_argument("--rotate-window", type=int, default=60, help="轮动强弱窗口(交易日)")
    parser.add_argument("--rotate-top", type=int, default=3, help="轮动选出最强N只")
    # 实盘
    parser.add_argument("--paper", action="store_true", help="模拟盘 (live 模式)")
    parser.add_argument("--dry-run", action="store_true", help="只打印不下单 (live 模式)")
    parser.add_argument("--plot", action="store_true", help="画图 (analyze: 结构图 / backtest: 结构+成交标记+资金曲线)")
    parser.add_argument("--plot-x-range", type=int, default=0,
                        help="backtest 画图只显示最近N根K线(0=全部)")

    args = parser.parse_args()

    if args.mode == "backtest":
        run_backtest(args)
    elif args.mode == "live":
        run_live(args)
    elif args.mode == "rotate":
        run_rotate(args)
    elif args.mode == "analyze":
        run_analyze(args)


if __name__ == "__main__":
    main()
