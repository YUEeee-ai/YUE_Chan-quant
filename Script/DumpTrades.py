# -*- coding: utf-8 -*-
"""导出指定标的在指定⑩模式下的逐笔成交, 用于层间差异归因
用法: python Script/DumpTrades.py --symbol 1810.HK [--energy {off,on,veto}]
"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Script"))
from AblationStudy import build_config, _enum, _DATA_SRC_MAP, _AUTYPE_MAP, _LV_MAP  # noqa
from Strategy.Backtester import Backtester
from Common import CEnum


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--energy", choices=["off", "on", "veto"], default="veto")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--capital", type=float, default=300000)
    p.add_argument("--lv", default="month,week,day")
    p.add_argument("--autype", default="none")
    p.add_argument("--max-misalign", type=int, default=None)
    args = p.parse_args()

    ns = argparse.Namespace(symbols=args.symbol, start=args.start, capital=args.capital,
                            lv=args.lv, autype=args.autype, no_short=False,
                            no_fx_confirm=False, div_rate=0.9, max_misalign=args.max_misalign,
                            energy_veto_only=(args.energy == "veto"))
    lv_names = [x.strip().lower() for x in args.lv.split(",") if x.strip()]
    lv_list_full = [_enum(CEnum.KL_TYPE, _LV_MAP[n]) for n in lv_names]
    cfg = build_config(ns, lv_list_full, lv_list_full[-1], None,
                       off_layer=("energy" if args.energy == "off" else None))
    bt = Backtester(
        code=args.symbol, begin_time=args.start, end_time=None,
        data_src=_enum(CEnum.DATA_SRC, _DATA_SRC_MAP["yfinance"]),
        lv_list=lv_list_full, strategy_config=cfg, initial_capital=args.capital,
        use_nested=False, autype=_enum(CEnum.AUTYPE, _AUTYPE_MAP[args.autype]),
        chan_config=({"max_kl_misalgin_cnt": args.max_misalign}
                     if args.max_misalign is not None else None),
    )
    res = bt.run()
    tag = {"off": "⑩关", "on": "⑩全开", "veto": "⑩仅否决"}[args.energy]
    print(f"=== {args.symbol} {tag}: 总收益 {res.total_return*100:+.1f}%  笔数 {res.total_trades}")
    for tr in res.trade_history:
        print(f"   {tr.time}  {tr.action:<5} @{tr.price:8.2f}  {tr.bsp_type:<8} {tr.reason[:48]}")


if __name__ == "__main__":
    main()
