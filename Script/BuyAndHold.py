# -*- coding: utf-8 -*-
"""计算各标的 2015-01 至今的买入持有基准(价格涨幅)"""
import yfinance as yf

SYMS = [
    ("600519.SS", "qfq"), ("000001.SZ", "qfq"), ("601318.SS", "qfq"), ("600036.SS", "qfq"),
    ("9988.HK", "none"), ("1810.HK", "none"), ("0700.HK", "none"), ("9618.HK", "none"),
    ("SPY", "none"), ("QQQ", "none"), ("TSLA", "none"),
]

print(f"{'标的':<12} {'首日':<12} {'末日':<12} {'期初价':>10} {'期末价':>10} {'买入持有涨幅':>12}")
for sym, adj in SYMS:
    df = yf.Ticker(sym).history(start="2015-01-01", interval="1d", auto_adjust=(adj == "qfq"))
    if df.empty:
        print(f"{sym:<12} 无数据")
        continue
    first, last = float(df["Close"].iloc[0]), float(df["Close"].iloc[-1])
    ret = (last / first - 1) * 100
    print(f"{sym:<12} {str(df.index[0].date()):<12} {str(df.index[-1].date()):<12} {first:>10.2f} {last:>10.2f} {ret:>+11.1f}%")
