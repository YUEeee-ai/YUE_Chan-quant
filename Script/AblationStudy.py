"""
十层纪律逐项开关对照实验 (Ablation Study)
==========================================
对每个标的跑 N+1 次回测:
  - ALL_ON     : 十层纪律全开(基线)
  - NO_<layer> : 只关闭第 X 层, 其余九层全开 → 该层的边际贡献 = 结果 - 基线

输出:
  - CSV 明细 (每次回测一行: 收益/年化/回撤/夏普/胜率/盈亏比/交易数/成本)
  - Markdown 汇总 (每标的 × 每层的 Δ收益, 及跨标的平均边际贡献)

两种对照模式 (--mode):
  off  (默认): 基线=十层全开, 每次【只关一层】 → 测该层的边际(最后一道门)贡献
  only:        基线=十层全关, 每次【只开一层】 → 测该层的独立贡献
                (对互为替代的否决门, only 模式才能看出单独一层值多少;
                 off 模式下它们的边际贡献必然≈0, 见 RESEARCH.md 第十节)
  both:        两种都跑 (2 + 2×N 次/标的)

用法:
  # 真实数据(yfinance): 美/港/A 三市按代码后缀自动路由
  python Script/AblationStudy.py --symbols AAPL,MSFT,SPY --start 2022-01-01 --end 2024-06-30

  # A股(前复权, 自动禁做空/T+1/一手100股)
  python Script/AblationStudy.py --symbols 600519.SS,000001.SZ --autype qfq --start 2020-01-01

  # 三级联立(级别联立/表里关系/小转大等真正生效, 耗时显著增加)
  python Script/AblationStudy.py --symbols AAPL --lv month,week,day --start 2015-01-01

  # 只跑部分层 / 离线合成数据自检
  python Script/AblationStudy.py --symbols AAPL --layers level_linkage,ma,energy
  python Script/AblationStudy.py --offline --symbols SYNTH --start 2018-01-01

参数见 --help。注意: 每个(标的×配置)都独立重建缠论结构, 多级别+长区间会很慢。
"""
import argparse
import csv
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")  # 避免 Windows GBK 终端乱码
except Exception:
    pass

# 十层开关: key → (StrategyConfig 字段, 说明)
LAYERS = [
    ("level_linkage",   "use_level_linkage",        "①多级别联立/背驰归属"),
    ("decompose",       "use_same_level_decompose", "②同级别分解"),
    ("middle_yin",      "use_middle_yin",           "③中阴阶段"),
    ("ma",              "use_ma_filter",            "④均线强弱"),
    ("small_turn_big",  "use_small_turn_big",       "⑤小转大(44课)"),
    ("zs_oscillation",  "use_zs_oscillation",       "⑥中枢震荡(92课)"),
    ("rebound",         "use_rebound",              "⑦短线反弹(107课)"),
    ("inside_outside",  "use_inside_outside",       "⑧表里关系(91/93/99)"),
    ("fugue",           "use_fugue",                "⑨多重赋格(40课)"),
    ("energy",          "use_energy",               "⑩能量动力(104课)"),
]

_LV_MAP = {
    "year": "K_YEAR", "quarter": "K_QUARTER", "month": "K_MON", "week": "K_WEEK",
    "day": "K_DAY", "60m": "K_60M", "30m": "K_30M", "15m": "K_15M",
    "5m": "K_5M", "1m": "K_1M",
}
_SUB_LV_MAP = {  # 操作级别 → 区间套/小转大次级别
    "K_DAY": "K_30M", "K_WEEK": "K_DAY", "K_MON": "K_WEEK", "K_60M": "K_15M", "K_30M": "K_5M",
}
_DATA_SRC_MAP = {"yfinance": "US_STOCK", "us_stock": "US_STOCK", "bao_stock": "BAO_STOCK", "ccxt": "CCXT"}
_AUTYPE_MAP = {"none": "NONE", "qfq": "QFQ", "hfq": "HFQ"}


def _enum(mod, name):
    return getattr(mod, name)


def parse_lv(s: str):
    from Common import CEnum
    names = [x.strip().lower() for x in s.split(",") if x.strip()] or ["day"]
    return [_enum(CEnum.KL_TYPE, _LV_MAP[n]) for n in names]


def build_config(args, lv_list_full, operating_lv, nested_lv, off_layer: str = None,
                 on_layer: str = None, all_layers_off: bool = False):
    """默认 → 十层全开(基线); off_layer=X → 只关X;
    on_layer=X → 只开X(其余全关, 测独立贡献); all_layers_off=True → 十层全关(基线)"""
    from Strategy.ChanStrategy import StrategyConfig
    from Common import CEnum
    kw = dict(
        operating_lv=operating_lv,
        lv_list=lv_list_full,
        nested_lv=nested_lv,
        divergence_rate=args.div_rate,
        require_fx_confirm=not args.no_fx_confirm,
        enable_short=not args.no_short,
        energy_veto_only=getattr(args, "energy_veto_only", False),
    )
    for key, field, _desc in LAYERS:
        if all_layers_off:
            kw[field] = False
        elif on_layer is not None:
            kw[field] = (key == on_layer)
        else:
            kw[field] = not (off_layer == key)
    return StrategyConfig(**kw)


def run_one(args, symbol, lv_list_full, operating_lv, nested_lv, off_layer=None,
            on_layer=None, all_layers_off=False):
    """跑一次回测, 返回指标 dict; 失败返回 None"""
    from Strategy.Backtester import Backtester
    from Common import CEnum
    data_src = _enum(CEnum.DATA_SRC, _DATA_SRC_MAP[args.data_src])
    autype = _enum(CEnum.AUTYPE, _AUTYPE_MAP[args.autype])
    cfg = build_config(args, lv_list_full, operating_lv, nested_lv,
                       off_layer, on_layer, all_layers_off)
    t0 = time.time()
    try:
        bt = Backtester(
            code=symbol, begin_time=args.start, end_time=args.end or None,
            data_src=data_src, lv_list=lv_list_full,
            strategy_config=cfg, initial_capital=args.capital,
            use_nested=bool(nested_lv), autype=autype,
            chan_config=({"max_kl_misalgin_cnt": args.max_misalign}
                         if args.max_misalign is not None else None),
        )
        res = bt.run()
    except Exception as e:
        print(f"    [失败] {symbol} {off_layer or on_layer or 'BASE'}: {e}")
        return None
    dt = time.time() - t0
    if on_layer is not None:
        tag = f"ONLY_{on_layer}"
    elif off_layer is not None:
        tag = f"NO_{off_layer}"
    elif all_layers_off:
        tag = "ALL_OFF"
    else:
        tag = "ALL_ON"
    return dict(
        symbol=symbol, run=tag,
        total_return=res.total_return, annual_return=res.annual_return,
        max_drawdown=res.max_drawdown, sharpe_ratio=res.sharpe_ratio,
        win_rate=res.win_rate, profit_loss_ratio=res.profit_loss_ratio,
        total_trades=res.total_trades, total_cost=res.total_cost,
        seconds=round(dt, 1),
    )


def write_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def write_md(rows, path, layers_used):
    """汇总: 关层实验(Δ vs 全开) + 只开实验(Δ vs 全关) + 两组基线"""
    by_sym = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], {})[r["run"]] = r
    has_only = any(r["run"].startswith("ONLY_") for r in rows)
    has_off = any(r["run"].startswith("NO_") for r in rows)

    lines = ["# 十层纪律逐项开关对照实验", "",
             f"- 区间: {args_global.start} ~ {args_global.end or 'now'} | 本金: {args_global.capital:,.0f} | 级别: {args_global.lv}",
             f"- 关层实验 Δ = 关闭该层 − 十层全开(Δ<0 = 该层有边际贡献)",
             f"- 只开实验 Δ = 只开该层 − 十层全关(Δ>0 = 该层独立为正贡献)", ""]

    def _table(title, run_key, base_key, positive_good):
        lines.append(f"## {title}" + "")
        lines.append("")
        header = "| 标的 | " + " | ".join(k for k, _, _ in layers_used) + " |"
        sep = "|" + "---|" * (len(layers_used) + 1)
        lines.extend([header, sep])
        deltas = {k: [] for k, _, _ in layers_used}
        for sym, runs in by_sym.items():
            base = runs.get(base_key)
            if base is None:
                continue
            cells = []
            for k, _, _ in layers_used:
                r = runs.get(run_key(k))
                if r is None:
                    cells.append(" - ")
                    continue
                d = (r["total_return"] - base["total_return"]) * 100
                deltas[k].append(d)
                cells.append(f"{d:+.1f}")
            lines.append(f"| {sym} | " + " | ".join(cells) + " |")
        lines.extend(["", "| 层 | 说明 | 平均Δ | 改善/正贡献标的数 |", "|---|---|---|---|"])
        for k, _, desc in layers_used:
            ds = deltas[k]
            if not ds:
                continue
            avg = sum(ds) / len(ds)
            good = sum(1 for d in ds if (d > 0 if positive_good else d < 0))
            lines.append(f"| {k} | {desc} | {avg:+.2f} | {good}/{len(ds)} |")
        lines.append("")

    if has_off:
        _table("关层实验: 关闭某层对总收益的影响(Δ%)", lambda k: f"NO_{k}", "ALL_ON", positive_good=False)
    if has_only:
        _table("只开实验: 只开某层(其余全关)对总收益的影响(Δ%)", lambda k: f"ONLY_{k}", "ALL_OFF", positive_good=True)

    def _base_table(title, base_key):
        lines.append(f"## {title}", )
        lines.extend(["", "| 标的 | 总收益% | 年化% | 最大回撤% | 夏普 | 胜率% | 交易数 | 成本 | 耗时s |",
                         "|---|---|---|---|---|---|---|---|---|"])
        for sym, runs in by_sym.items():
            b = runs.get(base_key)
            if b:
                lines.append(f"| {sym} | {b['total_return']*100:.1f} | {b['annual_return']*100:.1f} | "
                             f"{b['max_drawdown']*100:.1f} | {b['sharpe_ratio']:.2f} | {b['win_rate']*100:.1f} | "
                             f"{b['total_trades']:.0f} | {b['total_cost']:.0f} | {b['seconds']} |")
        lines.append("")

    if has_off:
        _base_table("基线: 十层全开", "ALL_ON")
    if has_only:
        _base_table("基线: 十层全关(仅基础三类买卖点)", "ALL_OFF")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


args_global = None  # write_md 用


def main():
    global args_global
    p = argparse.ArgumentParser(description="十层纪律逐项开关对照实验")
    p.add_argument("--symbols", default="AAPL,MSFT,SPY,QQQ,TSLA,NVDA",
                   help="逗号分隔的标的池(美/港/A按后缀路由: AAPL / 0700.HK / 600519.SS / BTC/USDT)")
    p.add_argument("--start", default="2022-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--capital", type=float, default=100000)
    p.add_argument("--lv", default="day", help="联立级别,从大到小: month,week,day / week,day / day")
    p.add_argument("--nested", action="store_true", help="操作级别下挂次级别(区间套+小转大/表里关系真正生效)")
    p.add_argument("--no-short", action="store_true", help="全部标的强制仅做多")
    p.add_argument("--no-fx-confirm", action="store_true", help="关闭分型确认")
    p.add_argument("--div-rate", type=float, default=0.9)
    p.add_argument("--data-src", choices=list(_DATA_SRC_MAP.keys()), default="yfinance")
    p.add_argument("--autype", choices=list(_AUTYPE_MAP.keys()), default="none", help="A股建议 qfq")
    p.add_argument("--layers", default="all",
                   help="只跑这些层(逗号分隔key): " + ",".join(k for k, _, _ in LAYERS) + "; all=全部十层")
    p.add_argument("--mode", choices=["off", "only", "both"], default="off",
                   help="off=只关一层(边际贡献, 默认); only=只开一层(独立贡献); both=两种都跑")
    p.add_argument("--out", default="ablation_results.csv", help="CSV 明细输出路径")
    p.add_argument("--md", default="ablation_report.md", help="Markdown 汇总输出路径")
    p.add_argument("--offline", action="store_true", help="用合成数据自检(不联网, 标的名随意)")
    p.add_argument("--max-misalign", type=int, default=None,
                   help="放宽父子级别对齐容忍(默认2)。yfinance部分市场(如A股)月线按月末/"
                        "非交易日标注, 会产生个别零子K线月份, 设 100 可跳过这些已知坏月份")
    p.add_argument("--energy-veto-only", action="store_true",
                   help="⑩变体: 只否决追势开仓, 关闭许可性提前离场(需配合 --layers energy 才有效)")
    args = p.parse_args()
    args_global = args

    if args.offline:  # 离线: 打补丁换成合成数据源
        import Chan as ChanMod
        sys.path.insert(0, os.path.join(ROOT, "Script"))
        from SmokeOffline import SyntheticAPI
        ChanMod.GetStockAPI = lambda src: SyntheticAPI

    lv_list = parse_lv(args.lv)
    operating_lv = lv_list[-1]
    nested_lv = []
    lv_full = list(lv_list)
    if args.nested:
        from Common import CEnum
        sub_name = _SUB_LV_MAP.get(operating_lv.name)
        if sub_name:
            sub = _enum(CEnum.KL_TYPE, sub_name)
            if sub not in lv_full:
                lv_full.append(sub)
                nested_lv = [sub]

    if args.layers.strip().lower() == "all":
        layers_used = list(LAYERS)
    else:
        want = {x.strip() for x in args.layers.split(",") if x.strip()}
        layers_used = [x for x in LAYERS if x[0] in want]
        unknown = want - {x[0] for x in layers_used}
        if unknown:
            print(f"[警告] 未知层 key: {unknown}, 可选: {[x[0] for x in LAYERS]}")
    if not layers_used:
        print("没有可跑的层")
        return

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"标的 {len(symbols)} 只 × 配置 {len(layers_used) + 1} 个(基线 + 关层×{len(layers_used)})")
    print(f"级别: {'>'.join(lv.name for lv in lv_full)} | 操作级别: {operating_lv.name} | "
          f"区间套: {[x.name for x in nested_lv] or '无'}")

    rows = []
    for sym in symbols:
        print(f"\n=== {sym} ===")
        jobs = []  # (tag, off_layer, on_layer, all_layers_off)
        if args.mode in ("off", "both"):
            jobs.append(("ALL_ON", None, None, False))
            jobs += [(f"NO_{k}", k, None, False) for k, _, _ in layers_used]
        if args.mode in ("only", "both"):
            jobs.append(("ALL_OFF", None, None, True))
            jobs += [(f"ONLY_{k}", None, k, False) for k, _, _ in layers_used]
        for tag, off_l, on_l, all_off in jobs:
            r = run_one(args, sym, lv_full, operating_lv, nested_lv,
                        off_layer=off_l, on_layer=on_l, all_layers_off=all_off)
            if r:
                rows.append(r)
                print(f"    {tag:<18} 收益{r['total_return']*100:+8.1f}%  回撤{r['max_drawdown']*100:6.1f}%  "
                      f"夏普{r['sharpe_ratio']:5.2f}  交易{r['total_trades']:3.0f}  ({r['seconds']}s)")

    if not rows:
        print("没有任何成功回测")
        return
    write_csv(rows, args.out)
    write_md(rows, args.md, layers_used)
    print(f"\n[CSV 明细] {os.path.abspath(args.out)}")
    print(f"[MD 汇总]  {os.path.abspath(args.md)}")


if __name__ == "__main__":
    main()
