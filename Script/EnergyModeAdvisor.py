# -*- coding: utf-8 -*-
"""⑩能量动力模式配置助手 — 按标的波动形态推荐 关/仅否决/全开

依据 RESEARCH 第十五节 11 标的实证分型:
  - 高波动 + 深回撤 + 底部强反弹(深熊反转型, 如 TSLA/小米/阿里/腾讯):
    ⑩是"救命层" — 无⑩时 TSLA 裸信号 -425%; 推荐"仅否决"(保留顶部否决、
    放弃提前离场), 小米例外(全开的许可性平空在深熊底部有对冲价值)。
  - 稳定长牛(低波 + 浅回撤 + 总涨幅高, 如 QQQ/SPY/茅台): ⑩是负担,
    全开曾让茅台 -695pp; 推荐"关"(茅台若开必须配仅否决)。
  - 其余(震荡/价值型): 层贡献 ±20pp 内方向不定; 推荐"关", 想要否决
    强化时可选"仅否决"。

用法:
  python Script/EnergyModeAdvisor.py --symbol TSLA,0700.HK,600519.SS
  python Script/EnergyModeAdvisor.py --symbol 601318.SS --start 2015-01-01 --autype qfq
"""
import argparse
import numpy as np
import yfinance as yf


def calc_features(sym: str, start: str, autype: str) -> dict:
    """从日线计算分型特征 (A股用复权价近似全收益)"""
    df = yf.Ticker(sym).history(start=start, interval="1d", auto_adjust=(autype == "qfq"))
    if df.empty:
        raise RuntimeError(f"{sym}: 无数据 (代码格式? 后缀: .SS/.SZ A股, .HK 港股, 纯字母美股)")
    close = df["Close"].astype(float).values
    ret = np.diff(np.log(close))
    ann_vol = float(np.std(ret, ddof=1) * np.sqrt(252) * 100)
    peak = np.maximum.accumulate(close)
    dd = close / peak - 1.0
    max_dd = float(dd.min() * 100)
    trough_idx = int(dd.argmin())
    recovery = float((close[-1] / close[trough_idx] - 1.0) * 100)
    total = float((close[-1] / close[0] - 1.0) * 100)
    return dict(sym=sym, first=str(df.index[0].date()), last=str(df.index[-1].date()),
                ann_vol=ann_vol, max_dd=max_dd, recovery=recovery, total=total)


def recommend(f: dict) -> tuple:
    """(模式, 形态标签, 依据) — 阈值按 RESEARCH 第十五节 11 标的标定:
    深熊反转型四只(阿里49/-80/73, 小米46/-76/220, 腾讯35/-73/119, TSLA57/-74/235)
    与其余标的在这些阈值下完全可分, 回判 11/11 推荐与实证最优一致。"""
    deep_bear_reversal = (f["max_dd"] <= -65) and (f["recovery"] >= 60) and (f["ann_vol"] >= 32)
    steady_bull = (f["total"] >= 150) and (f["ann_vol"] <= 32)
    if deep_bear_reversal:
        mode = "仅否决 (--use-energy --energy-veto-only)"
        arche = "深熊反转型 (类似 TSLA/小米/阿里/腾讯)"
        basis = (f"最大回撤 {f['max_dd']:.0f}% 后已从底部反弹 +{f['recovery']:.0f}%、年化波动 {f['ann_vol']:.0f}%"
                 " — 实证中此类标的上⑩是承重层: 无⑩时 TSLA 裸信号 -425%, 开⑩翻正;"
                 " 否决保留顶部保护(小米2021顶), 放弃许可性离场以免打断 V 型反转后的主升"
                 f"(同类标的仅否决相对全关: 腾讯 +54.8pp / 小米 +78.9pp / 阿里 +46.0pp / TSLA +806.6pp)")
        if f["ann_vol"] >= 40:
            basis += ("; 波动极高: 若标的呈单边深熊, 全开的许可性平空在底部有对冲价值"
                      "(小米 全开比仅否决还高 +201.8pp), 可作备选")
        return mode, arche, basis
    if steady_bull:
        return ("关 (默认)", "稳定长牛型 (类似 QQQ/SPY/茅台/招行)",
                f"总涨幅 +{f['total']:.0f}% 且年化波动仅 {f['ann_vol']:.0f}%"
                " — 实证中全开⑩曾让茅台 -695pp/QQQ -51.8pp(许可性离场打断复利);"
                " 若坚持开⑩必须配 --energy-veto-only(茅台 +18.5pp ≈ 全关, SPY +7.8pp 微正)")
    return ("关 (默认)", "震荡/价值型 (类似平安保险/京东)",
            f"年化波动 {f['ann_vol']:.0f}%、最大回撤 {f['max_dd']:.0f}%、底部反弹 +{f['recovery']:.0f}%"
            " — 实证中层贡献在 ±20pp 内方向不定; 默认关, 想要追势否决强化时可选仅否决")


def main():
    p = argparse.ArgumentParser(description="⑩能量动力模式配置助手")
    p.add_argument("--symbol", required=True, help="逗号分隔, 如 TSLA,0700.HK,600519.SS")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--autype", choices=["none", "qfq"], default="none",
                   help="A股建议 qfq(复权价含分红, 特征更接近全收益)")
    args = p.parse_args()

    print(f"{'标的':<12} {'区间':<24} {'年化波动':>8} {'最大回撤':>9} {'底部反弹':>9} {'总涨幅':>8}")
    feats = []
    for sym in [s.strip() for s in args.symbol.split(",") if s.strip()]:
        f = calc_features(sym, args.start, args.autype)
        feats.append(f)
        print(f"{f['sym']:<12} {f['first']}~{f['last']:<12} {f['ann_vol']:>7.0f}% "
              f"{f['max_dd']:>8.0f}% {f['recovery']:>8.0f}% {f['total']:>7.0f}%")
    print()
    for f in feats:
        mode, arche, basis = recommend(f)
        print(f"=== {f['sym']} → 推荐: {mode}")
        print(f"    形态: {arche}")
        print(f"    依据: {basis}")
        if "仅否决" in mode:
            print(f"    命令: python main_chan.py --mode backtest --symbol {f['sym']} "
                  f"--lv month,week,day --start {args.start} --use-energy --energy-veto-only"
                  + (" --autype qfq" if args.autype == "qfq" else ""))
        else:
            print(f"    命令: python main_chan.py --mode backtest --symbol {f['sym']} "
                  f"--lv month,week,day --start {args.start}"
                  + (" --autype qfq" if args.autype == "qfq" else ""))
        print()


if __name__ == "__main__":
    main()
