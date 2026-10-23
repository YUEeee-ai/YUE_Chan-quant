"""
离线冒烟/调试脚本 — 不联网验证策略引擎与十层级别纪律
=====================================================
用途: 在没有行情网络/不想等真实数据时, 用合成数据快速确认
      "数据源→缠论计算→十层纪律→策略→回测→画图" 整条链路没坏。

合成数据: 种子随机游走 + 分段趋势(涨/跌/涨/盘整循环) + 段末减速(制造背驰),
          保证能长出笔/线段/中枢/买卖点, 供各 Trend 分析模块与回测消费。

包含的确定性检查:
  1. detect_market 对 美/港/A/加密 代码后缀的路由
  2. MultiLevelContext.attribute_reversal 跨级别背驰归属的 4 个分支
  3. 四个 Trend 模块对真实计算出的 chan 的冒烟
  4. 新增六个模块(小转大/中枢震荡/短线反弹/表里关系/多重赋格/能量动力)的逻辑单测+真实chan冒烟
  5. Backtester 端到端回测(十层全开) + plot() 出两张图

运行:
    python Script/SmokeOffline.py
"""
import sys
import os
import random

# 仓库根目录(本文件在 Script/ 下, 上一级即根)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")  # 避免 Windows GBK 终端乱码
except Exception:
    pass

import Chan as ChanMod
from Common.CEnum import DATA_SRC, KL_TYPE, AUTYPE, DATA_FIELD
from Common.CTime import CTime
from KLine.KLineUnit import CKLine_Unit
from DataAPI.CommonStockAPI import CCommonStockApi
from Common.MarketCapability import detect_market, MARKET


class SyntheticAPI(CCommonStockApi):
    """合成日线数据源(替代真实行情, 供离线调试)"""
    is_connect = None

    def __init__(self, code, k_type=KL_TYPE.K_DAY, begin_date=None, end_date=None, autype=AUTYPE.QFQ):
        super().__init__(code, k_type, begin_date, end_date, autype)

    def SetBasciInfo(self):
        self.name = "SYNTH"
        self.is_stock = True

    def get_kl_data(self):
        rnd = random.Random(42)
        price = 100.0
        y, m, d = 2018, 1, 2
        for i in range(900):
            phase = (i // 120) % 4
            drift = {0: 0.004, 1: -0.004, 2: 0.005, 3: 0.0}[phase]
            if i % 120 > 100:  # 段末减速 → 制造背驰
                drift *= 0.3
            price = max(5.0, price * (1 + drift + rnd.gauss(0, 0.012)))
            o = price * (1 + rnd.gauss(0, 0.003))
            c = price
            h = max(o, c) * (1 + abs(rnd.gauss(0, 0.004)))
            l = min(o, c) * (1 - abs(rnd.gauss(0, 0.004)))
            d += 1
            if d > 28:
                d, m = 1, m + 1
            if m > 12:
                m, y = 1, y + 1
            yield CKLine_Unit({
                DATA_FIELD.FIELD_TIME: CTime(y, m, d, 0, 0),
                DATA_FIELD.FIELD_OPEN: o, DATA_FIELD.FIELD_HIGH: h,
                DATA_FIELD.FIELD_LOW: l, DATA_FIELD.FIELD_CLOSE: c,
                DATA_FIELD.FIELD_VOLUME: 1e6,
            }, autofix=True)

    @classmethod
    def do_init(cls):
        pass

    @classmethod
    def do_close(cls):
        pass


def patch_source():
    """把数据源替换为合成源(不联网)"""
    ChanMod.GetStockAPI = lambda src: SyntheticAPI


def test_market_routing():
    cases = {"AAPL": MARKET.US, "0700.HK": MARKET.HK, "600519.SS": MARKET.CN,
             "000001.SZ": MARKET.CN, "600519": MARKET.CN, "BTC/USDT": MARKET.CRYPTO}
    for code, expect in cases.items():
        src = DATA_SRC.CCXT if "/" in code else DATA_SRC.US_STOCK
        got = detect_market(src, code)
        assert got == expect, f"{code}: 期望{expect} 实得{got}"
        print(f"[market] {code:<12} -> {got.value}")


def test_attribution_logic():
    from Trend.LevelLinkage import MultiLevelContext, LevelState
    from Trend.TrendAnalyzer import ZoushiType

    def make(states):
        ctx = MultiLevelContext([KL_TYPE.K_MON, KL_TYPE.K_WEEK, KL_TYPE.K_DAY], KL_TYPE.K_DAY, 2)
        ctx.states = states
        return ctx

    # A: 高级别上涨未完美 → 日线卖点=次级别回调(禁做空/不离场)
    a = make({KL_TYPE.K_DAY: LevelState(KL_TYPE.K_DAY, ZoushiType.UP_TREND, True, 2),
              KL_TYPE.K_WEEK: LevelState(KL_TYPE.K_WEEK, ZoushiType.UP_TREND, False, 3),
              KL_TYPE.K_MON: LevelState(KL_TYPE.K_MON, ZoushiType.UP_TREND, False, 2)}).attribute_reversal(False)
    assert not a.allow_short and not a.allow_exit
    print(f"[attribution A] 高级别上涨未完 -> 做空={a.allow_short} 离场={a.allow_exit}")

    # B: 高级别上涨已完美 → 背书放行
    b = make({KL_TYPE.K_DAY: LevelState(KL_TYPE.K_DAY, ZoushiType.UP_TREND, True, 2),
              KL_TYPE.K_WEEK: LevelState(KL_TYPE.K_WEEK, ZoushiType.UP_TREND, True, 3),
              KL_TYPE.K_MON: LevelState(KL_TYPE.K_MON, ZoushiType.CONSOLIDATION, False, 1)}).attribute_reversal(False)
    assert b.allow_short and b.allow_exit
    print(f"[attribution B] 周线已完美 -> 背书={b.endorsed_by_higher} 做空={b.allow_short}")

    # C: 高级别下跌未完美 → 日线买点禁开仓(不接飞刀)
    c = make({KL_TYPE.K_DAY: LevelState(KL_TYPE.K_DAY, ZoushiType.DOWN_TREND, True, 2),
              KL_TYPE.K_WEEK: LevelState(KL_TYPE.K_WEEK, ZoushiType.DOWN_TREND, False, 3),
              KL_TYPE.K_MON: LevelState(KL_TYPE.K_MON, ZoushiType.DOWN_TREND, False, 2)}).attribute_reversal(True)
    assert not c.allow_open
    print(f"[attribution C] 高级别下跌未完 -> 买点开仓={c.allow_open}")

    # D: 单级别退化 → 全放行
    d = MultiLevelContext([KL_TYPE.K_DAY], KL_TYPE.K_DAY, 2)
    d.states = {KL_TYPE.K_DAY: LevelState(KL_TYPE.K_DAY, ZoushiType.UP_TREND, True, 2)}
    d = d.attribute_reversal(False)
    assert d.allow_short and d.allow_exit
    print("[attribution D] 单级别退化 -> 全放行")


def test_trend_modules():
    from Chan import CChan
    from ChanConfig import CChanConfig
    from Trend.LevelLinkage import MultiLevelContext
    from Trend.SameLevelDecompose import SameLevelDecomposer, holding_signal
    from Trend.MiddleYin import MiddleYinDetector
    from Trend.MATrend import MATrendEvaluator

    conf = CChanConfig({"triger_step": False, "macd_algo": "composite_full",
                        "divergence_rate": 0.9, "min_zs_cnt": 1, "seg_algo": "chan",
                        "bs_type": "1,1p,2,2s,3a,3b"})
    chan = CChan(code="SYNTH", begin_time="2018-01-01", data_src=DATA_SRC.US_STOCK,
                 lv_list=[KL_TYPE.K_DAY], config=conf, autype=AUTYPE.NONE)
    bsp_conf = chan.conf.bs_point_conf.GetBSConfig(False)

    ml = MultiLevelContext([KL_TYPE.K_DAY], KL_TYPE.K_DAY, 2).update(chan, bsp_conf)
    print(f"[level-linkage] 操作级别={ml.state(KL_TYPE.K_DAY)}")
    pieces = SameLevelDecomposer(2).decompose(chan, KL_TYPE.K_DAY, bsp_conf)
    print(f"[decompose] 段数={len(pieces)} 末段={pieces[-1]} 持多={holding_signal(pieces, True)}")
    print(f"[middle-yin] {MiddleYinDetector().detect(chan, KL_TYPE.K_DAY, 30)}")
    ma = MATrendEvaluator(5, 10, 20).evaluate(chan, KL_TYPE.K_DAY)
    print(f"[ma-trend] {ma}")
    assert pieces and ma.enough_data
    return chan


def test_trend_modules():
    from Chan import CChan
    from ChanConfig import CChanConfig
    from Trend.LevelLinkage import MultiLevelContext
    from Trend.SameLevelDecompose import SameLevelDecomposer, holding_signal
    from Trend.MiddleYin import MiddleYinDetector
    from Trend.MATrend import MATrendEvaluator

    conf = CChanConfig({"triger_step": False, "macd_algo": "composite_full",
                        "divergence_rate": 0.9, "min_zs_cnt": 1, "seg_algo": "chan",
                        "bs_type": "1,1p,2,2s,3a,3b"})
    chan = CChan(code="SYNTH", begin_time="2018-01-01", data_src=DATA_SRC.US_STOCK,
                 lv_list=[KL_TYPE.K_DAY], config=conf, autype=AUTYPE.NONE)
    bsp_conf = chan.conf.bs_point_conf.GetBSConfig(False)

    ml = MultiLevelContext([KL_TYPE.K_DAY], KL_TYPE.K_DAY, 2).update(chan, bsp_conf)
    print(f"[level-linkage] 操作级别={ml.state(KL_TYPE.K_DAY)}")
    pieces = SameLevelDecomposer(2).decompose(chan, KL_TYPE.K_DAY, bsp_conf)
    print(f"[decompose] 段数={len(pieces)} 末段={pieces[-1]} 持多={holding_signal(pieces, True)}")
    print(f"[middle-yin] {MiddleYinDetector().detect(chan, KL_TYPE.K_DAY, 30)}")
    ma = MATrendEvaluator(5, 10, 20).evaluate(chan, KL_TYPE.K_DAY)
    print(f"[ma-trend] {ma}")
    assert pieces and ma.enough_data
    return chan


# ---- 新增六模块逻辑单测用的极简桩对象 ----

class _T:
    def __init__(self, ts):
        self.ts = ts


class _Klu:
    def __init__(self, ts, close=0.0, low=None, idx=0):
        self.time = _T(ts)
        self.close = close
        self.low = close if low is None else low
        self.idx = idx


class _Bi:
    def __init__(self, lo, hi, ts):
        self._lo, self._hi, self._ts = lo, hi, ts

    def _low(self):
        return self._lo

    def _high(self):
        return self._hi

    def is_down(self):
        return True

    def is_divergence(self, conf):
        return (False, None)

    def get_end_klu(self):
        return _Klu(self._ts)


class _BiDivergent(_Bi):
    def is_divergence(self, conf):
        return (True, 0.5)


class _ZS:
    def __init__(self, low, high, begin_ts, bi_out=None):
        self.low, self.high = low, high
        self.begin = _Klu(begin_ts)
        self.bi_out = bi_out

    def is_one_bi_zs(self):
        return False

    def is_divergence(self, conf):
        if self.bi_out is None:
            return (False, None)
        return self.bi_out.is_divergence(conf)


class _KLStub:
    """chan[lv] 的最小桩: 中枢列表 + 笔列表 + 最后一根K线"""

    def __init__(self, zs_lst, bis, last_close, bsps=()):
        self.zs_list = type("Z", (), {"zs_lst": zs_lst})
        self.bi_list = type("B", (), {"bi_list": bis})
        self.bs_point_lst = type("P", (), {"lst": list(bsps)})
        self._last = [_Klu(9999, last_close)]

    def __getitem__(self, i):
        return self._last

    def __len__(self):
        return len(self._last)


class _BSPStub:
    def __init__(self, is_buy, ts, lo):
        from Common.CEnum import BSP_TYPE
        self.type = [BSP_TYPE.T1]
        self.is_buy = is_buy
        self.klu = _Klu(ts, idx=ts)
        self.bi = _Bi(lo, lo + 5, ts)


def test_small_turn_big_logic():
    """小转大(第44课)三条件: 大级别未背驰 + 次级别背驰 + 结构破坏(跌破后收回)"""
    from Trend.SmallTurnBig import SmallTurnBigDetector

    # 正向: 大级别中枢[100,110], 无背驰; 次级别底背驰@96; 大级别笔曾跌破100后收回105
    large = _KLStub([_ZS(100, 110, 100, bi_out=_Bi(96, 105, 210))],
                    [_Bi(96, 108, 200)], last_close=105)
    sub = _KLStub([], [], 105, bsps=[_BSPStub(True, 150, 96)])
    chan = {KL_TYPE.K_DAY: large, KL_TYPE.K_30M: sub}

    det = SmallTurnBigDetector()
    buy = det.detect_buy(chan, KL_TYPE.K_DAY, KL_TYPE.K_30M, None)
    assert buy.active and buy.sub_divergence_count == 1, str(buy)
    print(f"[small-turn-big] 正向确认: {buy}")

    # 反向1: 大级别自身已背驰 → 常规一类转折, 不算小转大
    large2 = _KLStub([_ZS(100, 110, 100, bi_out=_BiDivergent(96, 105, 210))],
                     [_Bi(96, 108, 200)], last_close=105)
    chan2 = {KL_TYPE.K_DAY: large2, KL_TYPE.K_30M: sub}
    buy2 = det.detect_buy(chan2, KL_TYPE.K_DAY, KL_TYPE.K_30M, None)
    assert not buy2.active
    print(f"[small-turn-big] 大级别已背驰 → 非小转大: {buy2.reason}")

    # 反向2: 价格未收回中枢(仍 < 100) → 未确认
    large3 = _KLStub([_ZS(100, 110, 100, bi_out=_Bi(96, 105, 210))],
                     [_Bi(96, 108, 200)], last_close=98)
    chan3 = {KL_TYPE.K_DAY: large3, KL_TYPE.K_30M: sub}
    buy3 = det.detect_buy(chan3, KL_TYPE.K_DAY, KL_TYPE.K_30M, None)
    assert not buy3.active
    print(f"[small-turn-big] 未收回中枢 → 未确认: {buy3.reason}")


def test_rebound_logic():
    """短线反弹(第107课): 急跌窗口 + 目标/止损位计算 + 入场须在最低位之后"""
    from Trend.ReboundTrader import ReboundPlanner

    class _Klc(list):
        """合并K线桩: 支持 [-1].close / [-1].idx / 迭代 klu.low"""
        pass

    class _Kl(list):
        pass

    closes = [100.0] * 12 + [90.0, 85.0, 82.0, 80.0]
    kl = _Kl([_Klc([_Klu(i, c, low=c * 0.99, idx=i)]) for i, c in enumerate(closes)])
    kl.zs_list = type("Z", (), {"zs_lst": []})()   # 无中枢 → 目标位用0.618回撤
    chan = {KL_TYPE.K_DAY: kl}

    planner = ReboundPlanner(drop_window=20, drop_pct=12.0)
    plan = planner.plan(chan, KL_TYPE.K_DAY)
    assert plan.setup, str(plan)
    # 目标 = 最低 + (高点-最低)×0.618; 止损 = 最低×0.98
    expect_low = min(c * 0.99 for c in closes)
    assert abs(plan.stop_price - expect_low * 0.98) < 1e-6
    assert abs(plan.target_price - (expect_low + (100.0 - expect_low) * 0.618)) < 1e-6
    # 最低点之前(idx 5)的买点不允许, 之后允许
    assert not planner.entry_allowed(plan, _BSPStub(True, 5, 99))
    assert planner.entry_allowed(plan, _BSPStub(True, 18, expect_low))
    print(f"[rebound] 急跌计划: {plan}")

    # 反向: 平稳走势(无急跌) → 无窗口
    flat = _Kl([_Klc([_Klu(i, 100.0, low=99.0, idx=i)]) for i in range(20)])
    flat.zs_list = type("Z", (), {"zs_lst": []})()
    plan2 = planner.plan({KL_TYPE.K_DAY: flat}, KL_TYPE.K_DAY)
    assert not plan2.setup
    print(f"[rebound] 无急跌 → 无窗口: {plan2.reason}")


def test_new_modules_on_real_chan():
    """在真实计算出的 chan 上冒烟六个新模块(构造双级别: 日线+60分)"""
    from Chan import CChan
    from ChanConfig import CChanConfig
    from Trend.SmallTurnBig import SmallTurnBigDetector, SmallTurnBigState
    from Trend.ZSOscillation import ZSOscillationMonitor, ZSOscillationState
    from Trend.ReboundTrader import ReboundPlanner, ReboundPlan
    from Trend.InsideOutside import InsideOutsideAnalyzer, InsideOutsideState
    from Trend.FugueDecompose import FugueDecomposer, FugueState
    from Trend.EnergyDynamics import EnergyEvaluator, EnergyState

    conf = CChanConfig({"triger_step": False, "macd_algo": "composite_full",
                        "divergence_rate": 0.9, "min_zs_cnt": 1, "seg_algo": "chan",
                        "bs_type": "1,1p,2,2s,3a,3b"})
    chan = CChan(code="SYNTH2", begin_time="2018-01-01", data_src=DATA_SRC.US_STOCK,
                 lv_list=[KL_TYPE.K_DAY, KL_TYPE.K_60M], config=conf, autype=AUTYPE.NONE)
    bsp_conf = chan.conf.bs_point_conf.GetBSConfig(False)

    stb = SmallTurnBigDetector().detect_buy(chan, KL_TYPE.K_DAY, KL_TYPE.K_60M, bsp_conf)
    assert isinstance(stb, SmallTurnBigState)
    print(f"[small-turn-big] {stb}")
    osc = ZSOscillationMonitor().detect(chan, KL_TYPE.K_DAY)
    assert isinstance(osc, ZSOscillationState)
    print(f"[zs-oscillation] {osc}")
    rb = ReboundPlanner().plan(chan, KL_TYPE.K_DAY)
    assert isinstance(rb, ReboundPlan)
    print(f"[rebound] {rb}")
    io = InsideOutsideAnalyzer().analyze(chan, KL_TYPE.K_60M, KL_TYPE.K_DAY, bsp_conf)
    assert isinstance(io, InsideOutsideState)
    print(f"[inside-outside] {io}")
    fug = FugueDecomposer().decompose(chan, [KL_TYPE.K_DAY, KL_TYPE.K_60M], bsp_conf)
    assert isinstance(fug, FugueState) and fug.voices, str(fug)
    print(f"[fugue] {fug}")
    en = EnergyEvaluator().evaluate(chan, KL_TYPE.K_DAY)
    assert isinstance(en, EnergyState) and en.last_ratio is not None
    print(f"[energy] {en}")


def test_backtest_and_plot():
    from Strategy.Backtester import Backtester
    from Strategy.ChanStrategy import StrategyConfig
    # ⑩ 默认关闭 + 仅否决变体开关接线
    _dft = StrategyConfig()
    assert _dft.use_energy is False and _dft.energy_veto_only is False
    _vo = StrategyConfig(use_energy=True, energy_veto_only=True)
    assert _vo.use_energy is True and _vo.energy_veto_only is True
    print("[energy-veto-only] 开关接线 OK (默认关, 变体可独立开启)")
    cfg = StrategyConfig(operating_lv=KL_TYPE.K_DAY, lv_list=[KL_TYPE.K_DAY])  # ①~⑨默认开, ⑩默认关
    bt = Backtester(code="SYNTH", begin_time="2018-01-01", data_src=DATA_SRC.US_STOCK,
                    lv_list=[KL_TYPE.K_DAY], strategy_config=cfg, autype=AUTYPE.NONE)
    res = bt.run()
    assert len(res.equity_curve) > 100
    print(f"[backtest] trades={res.total_trades} ret={res.total_return*100:.2f}% win={res.win_rate*100:.1f}%")
    trades_png, equity_png = bt.plot(res, out_prefix=os.path.join("results", "smoke_synth"))
    for p in (trades_png, equity_png):
        assert os.path.exists(p) and os.path.getsize(p) > 5000, f"图未生成: {p}"
        print(f"[plot] {p} ({os.path.getsize(p)//1024} KB)")


if __name__ == "__main__":
    patch_source()
    print("=" * 56)
    test_market_routing()
    print("-" * 56)
    test_attribution_logic()
    print("-" * 56)
    test_small_turn_big_logic()
    print("-" * 56)
    test_rebound_logic()
    print("-" * 56)
    test_trend_modules()
    print("-" * 56)
    test_new_modules_on_real_chan()
    print("-" * 56)
    test_backtest_and_plot()
    print("=" * 56)
    print("SMOKE ALL PASS")
