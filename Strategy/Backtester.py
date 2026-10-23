"""
缠论策略回测框架 — 多市场支持
- step_load 逐K线回放
- 集成 Common.market_capability: 印花税/佣金/T+1/lot size
- 完整绩效指标 (收益/夏普/回撤/胜率/盈亏比)
- 输出交易明细和统计报告
"""
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from Chan import CChan
from ChanConfig import CChanConfig, DEFAULT_ALGO_CONFIG
from Common.CEnum import DATA_SRC, KL_TYPE, AUTYPE
from Common.MarketCapability import (
    MARKET, MarketCapability, detect_market, get_market_capability,
)
from Strategy.ChanStrategy import (
    ChanStrategy, ChanNestedStrategy, StrategyConfig, TradeRecord,
)


@dataclass
class BacktestResult:
    """回测结果"""
    total_return: float = 0.0          # 总收益率
    annual_return: float = 0.0         # 年化收益率
    max_drawdown: float = 0.0          # 最大回撤
    sharpe_ratio: float = 0.0          # 夏普比率
    win_rate: float = 0.0              # 胜率
    profit_loss_ratio: float = 0.0     # 盈亏比
    total_trades: int = 0              # 总交易次数
    buy_trades: int = 0                # 做多开仓次数
    sell_trades: int = 0               # 做多平仓次数
    short_trades: int = 0              # 做空开仓次数
    cover_trades: int = 0              # 做空平仓次数
    total_cost: float = 0.0            # 总交易成本 (佣金+印花税+过户费)
    avg_holding_days: float = 0.0      # 平均持仓天数
    trade_history: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    initial_capital: float = 100000.0
    final_capital: float = 100000.0
    market: str = ""                   # 市场标识
    start_time: str = ""
    end_time: str = ""


class Backtester:
    """
    多市场回测引擎

    使用方式:
        bt = Backtester(
            code="AAPL",
            begin_time="2020-01-01",
            end_time="2024-01-01",
            data_src=DATA_SRC.US_STOCK,
            strategy_config=StrategyConfig(),
        )
        result = bt.run()
        bt.print_report(result)
    """

    def __init__(
        self,
        code: str,
        begin_time: str,
        end_time: Optional[str] = None,
        data_src: DATA_SRC = DATA_SRC.US_STOCK,
        lv_list: List[KL_TYPE] = None,
        chan_config: dict = None,
        strategy_config: StrategyConfig = None,
        initial_capital: float = 100000.0,
        market: Optional[MARKET] = None,
        commission_rate: Optional[float] = None,  # 显式指定则覆盖市场默认
        use_nested: bool = False,
        autype: AUTYPE = AUTYPE.NONE,
    ):
        self.code = code
        self.begin_time = begin_time
        self.end_time = end_time
        self.data_src = data_src
        self.lv_list = lv_list or [KL_TYPE.K_DAY]
        self.chan_config = chan_config or {}
        self.strategy_config = strategy_config or StrategyConfig()
        self.initial_capital = initial_capital
        self.use_nested = use_nested
        self.autype = autype
        # 因"一手 lot / 资金不足"被取整为 0 股而跳过的开仓次数(透明告警用)
        self.lot_skip_count = 0
        self.chan = None  # run() 后保存, 供 plot() 使用
        self.bsp_decisions = []  # run() 后保存: 结构买卖点成交/veto 决策
        # 取价级别: 优先用策略操作级别(多级别时信号来自该级别), 否则用最高级别
        _op_lv = getattr(self.strategy_config, "operating_lv", None)
        self.price_lv = _op_lv if _op_lv in self.lv_list else self.lv_list[0]

        # 市场能力: 显式指定 > 从 data_src+code 推断
        self.market = market or detect_market(data_src, code)
        # 拷贝一份能力描述, 允许调用方覆盖 commission_rate
        base_cap = get_market_capability(self.market)
        self.cap = MarketCapability(**{
            **base_cap.__dict__,
            **({"commission_rate": commission_rate} if commission_rate is not None else {}),
        })

    def run(self) -> BacktestResult:
        """执行回测 (多空双向 + 多市场规则)"""
        # 构建缠论配置
        config_dict = {
            "triger_step": True,
            "divergence_rate": self.strategy_config.divergence_rate,
            "min_zs_cnt": self.strategy_config.min_zs_cnt,
            **DEFAULT_ALGO_CONFIG,
        }
        config_dict.update(self.chan_config)

        chan_conf = CChanConfig(config_dict)

        chan = CChan(
            code=self.code,
            begin_time=self.begin_time,
            end_time=self.end_time,
            data_src=self.data_src,
            lv_list=self.lv_list,
            config=chan_conf,
            autype=self.autype,
        )
        self.chan = chan  # 保存最终结构, 供 plot() 画买卖点/成交标记

        # 创建策略 (注入市场能力, A股等市场自动禁做空)
        if self.use_nested and len(self.lv_list) > 1:
            strategy = ChanNestedStrategy(self.strategy_config, market_cap=self.cap)
        else:
            strategy = ChanStrategy(self.strategy_config, market_cap=self.cap)

        # 回测状态
        capital = self.initial_capital
        long_shares = 0.0
        short_shares = 0.0
        long_entry_price = 0.0
        short_entry_price = 0.0
        long_entry_date = None       # T+1 判定用
        short_entry_date = None
        equity_curve = []
        trade_pairs = []
        total_cost = 0.0
        snapshot = None
        curve_first_ts = None   # 权益曲线首/末快照时间戳，用于按真实日历跨度年化
        curve_last_ts = None

        for snapshot in chan.step_load():
            try:
                lv = self.price_lv
                kl_list = snapshot[lv]
                if len(kl_list) == 0 or len(kl_list[-1]) == 0:
                    continue
                current_price = kl_list[-1][-1].close
                current_date = kl_list[-1][-1].time
            except Exception:
                continue

            # 双向止损 (检测 → T+1 校验 → 执行 → apply_stop)
            stop_record = strategy.check_stop_loss(current_price)
            if stop_record:
                # 止损记录带上真实 bar 日期(原为 "STOP_LOSS"), 便于报告与画图定位
                stop_record.time = str(current_date)
            if stop_record and self._can_close(
                stop_record, current_date, long_entry_date, short_entry_date
            ):
                (capital, long_shares, short_shares, long_entry_price, short_entry_price,
                 long_entry_date, short_entry_date, trade_pairs, cost) = self._execute_trade(
                    stop_record, capital, long_shares, short_shares,
                    long_entry_price, short_entry_price,
                    long_entry_date, short_entry_date, trade_pairs, current_date,
                )
                total_cost += cost
                strategy.apply_stop(stop_record)
            # 若 T+1 阻挡, 不调用 apply_stop; 下一 K 线重新检测止损

            # 策略信号
            record = strategy.on_bar(snapshot)
            if record:
                if self._can_close(record, current_date, long_entry_date, short_entry_date):
                    (capital, long_shares, short_shares, long_entry_price, short_entry_price,
                     long_entry_date, short_entry_date, trade_pairs, cost) = self._execute_trade(
                        record, capital, long_shares, short_shares,
                        long_entry_price, short_entry_price,
                        long_entry_date, short_entry_date, trade_pairs, current_date,
                    )
                    total_cost += cost

            equity = capital + long_shares * current_price - short_shares * current_price
            equity_curve.append(equity)
            _ts = getattr(current_date, "ts", None)
            if _ts is not None:
                if curve_first_ts is None:
                    curve_first_ts = _ts
                curve_last_ts = _ts

        # 强制平仓
        if snapshot is not None:
            try:
                final_price = snapshot[self.price_lv][-1][-1].close
                if long_shares > 0:
                    cost = self._calc_cost(final_price, long_shares, "SELL")
                    capital += long_shares * final_price - cost
                    total_cost += cost
                    if long_entry_price > 0:
                        trade_pairs.append((final_price - long_entry_price) / long_entry_price)
                    long_shares = 0
                if short_shares > 0:
                    cost = self._calc_cost(final_price, short_shares, "COVER")
                    capital -= short_shares * final_price + cost
                    total_cost += cost
                    if short_entry_price > 0:
                        trade_pairs.append((short_entry_price - final_price) / short_entry_price)
                    short_shares = 0
            except Exception:
                pass

        final_capital = capital
        self.bsp_decisions = list(getattr(strategy, "bsp_decisions", []))

        curve_span_sec = (curve_last_ts - curve_first_ts) if (curve_first_ts is not None and curve_last_ts is not None) else None

        return self._calc_metrics(
            equity_curve, final_capital, strategy.trade_history,
            trade_pairs, total_cost, curve_span_sec,
        )

    def _can_close(self, record: TradeRecord, current_date, long_entry_date, short_entry_date) -> bool:
        """
        T+1 约束: A股当天买入不能当天卖出
        仅当平仓动作 (SELL/COVER) + 有 entry_date + t_plus_0=False + 同日时阻挡
        """
        if self.cap.t_plus_0:
            return True
        if record.action == "SELL" and long_entry_date is not None:
            if str(long_entry_date)[:10] == str(current_date)[:10]:
                return False
        if record.action == "COVER" and short_entry_date is not None:
            if str(short_entry_date)[:10] == str(current_date)[:10]:
                return False
        return True

    def _calc_cost(self, price: float, qty: float, direction: str) -> float:
        """按市场规则计算交易成本"""
        gross = price * qty
        commission = gross * self.cap.commission_rate
        # A 股最低 5 元佣金
        if self.cap.market == MARKET.CN:
            commission = max(commission, 5.0)
        # 印花税: A股卖出单边; 港股双边(买/卖/开空/回补全收)
        stamp = 0.0
        if self.cap.market == MARKET.CN:
            if direction == "SELL":
                stamp = gross * self.cap.stamp_tax
        elif self.cap.market == MARKET.HK:
            if direction in ("BUY", "SELL", "SHORT", "COVER"):
                stamp = gross * self.cap.stamp_tax
        # 过户费: 仅 A 股
        transfer = gross * self.cap.transfer_fee if self.cap.market == MARKET.CN else 0.0
        return commission + stamp + transfer

    def _round_qty(self, qty: float) -> float:
        """按 lot_size 取整 (A股/港股 100 股一手, 美股可碎股)"""
        if self.cap.allow_fractional or self.cap.lot_size <= 1:
            return qty
        lots = int(qty / self.cap.lot_size)
        return lots * self.cap.lot_size

    def _execute_trade(self, record, capital, long_shares, short_shares,
                       long_entry_price, short_entry_price,
                       long_entry_date, short_entry_date, trade_pairs, current_date):
        """
        执行交易 — 多空四向 + 市场规则
        """
        price = record.price
        total_value = capital + long_shares * price - short_shares * price
        cost = 0.0

        if record.action == "BUY":
            buy_value = total_value * record.position_ratio
            rate = self.cap.commission_rate + self.cap.stamp_tax + self.cap.transfer_fee
            est_shares = buy_value / (price * (1 + rate))
            actual_shares = self._round_qty(est_shares)
            if actual_shares > 0:
                cost = self._calc_cost(price, actual_shares, "BUY")
                capital -= actual_shares * price + cost
                if long_shares + actual_shares > 0:
                    long_entry_price = (
                        (long_entry_price * long_shares + price * actual_shares + cost)
                        / (long_shares + actual_shares)
                    )
                long_shares += actual_shares
                if long_entry_date is None:
                    long_entry_date = current_date
            elif est_shares > 0:
                self.lot_skip_count += 1  # 资金不足一手(如高价A股/港股), 本次开仓被跳过

        elif record.action == "SELL":
            sell_ratio = abs(record.position_ratio)
            sell_shares = long_shares if sell_ratio >= 0.999 else self._round_qty(long_shares * sell_ratio)
            if sell_shares > 0:
                cost = self._calc_cost(price, sell_shares, "SELL")
                capital += sell_shares * price - cost
                long_shares -= sell_shares
                if long_entry_price > 0:
                    pnl = (price - long_entry_price) / long_entry_price
                    trade_pairs.append(pnl)
                if long_shares < 0.001:
                    long_shares = 0.0
                    long_entry_price = 0.0
                    long_entry_date = None

        elif record.action == "SHORT":
            # 市场不支持做空则忽略 (策略层已 gate, 此处双保险)
            if not self.cap.support_short:
                return (capital, long_shares, short_shares, long_entry_price, short_entry_price,
                        long_entry_date, short_entry_date, trade_pairs, 0.0)
            short_value = total_value * record.position_ratio
            est_shares = short_value / price
            actual_shares = self._round_qty(est_shares)
            if actual_shares > 0:
                cost = self._calc_cost(price, actual_shares, "SHORT")
                capital += actual_shares * price - cost
                if short_shares + actual_shares > 0:
                    short_entry_price = (
                        (short_entry_price * short_shares + price * actual_shares)
                        / (short_shares + actual_shares)
                    )
                short_shares += actual_shares
                if short_entry_date is None:
                    short_entry_date = current_date
            elif est_shares > 0:
                self.lot_skip_count += 1  # 资金不足一手, 本次开空被跳过

        elif record.action == "COVER":
            cover_ratio = abs(record.position_ratio)
            cover_shares = short_shares if cover_ratio >= 0.999 else self._round_qty(short_shares * cover_ratio)
            if cover_shares > 0:
                cost = self._calc_cost(price, cover_shares, "COVER")
                capital -= cover_shares * price + cost
                short_shares -= cover_shares
                if short_entry_price > 0:
                    pnl = (short_entry_price - price) / short_entry_price
                    trade_pairs.append(pnl)
                if short_shares < 0.001:
                    short_shares = 0.0
                    short_entry_price = 0.0
                    short_entry_date = None

        return (capital, long_shares, short_shares, long_entry_price, short_entry_price,
                long_entry_date, short_entry_date, trade_pairs, cost)

    def _calc_metrics(self, equity_curve, final_capital, trade_history, trade_pairs, total_cost, curve_span_sec=None) -> BacktestResult:
        """计算绩效指标"""
        result = BacktestResult()
        result.initial_capital = self.initial_capital
        result.final_capital = final_capital
        result.trade_history = trade_history
        result.equity_curve = equity_curve
        result.total_trades = len(trade_history)
        result.buy_trades = sum(1 for t in trade_history if t.action == "BUY")
        result.sell_trades = sum(1 for t in trade_history if t.action == "SELL")
        result.short_trades = sum(1 for t in trade_history if t.action == "SHORT")
        result.cover_trades = sum(1 for t in trade_history if t.action == "COVER")
        result.total_cost = total_cost
        result.market = self.cap.name

        result.total_return = (final_capital - self.initial_capital) / self.initial_capital

        # 真实日历跨度 → 年数；单级别下每个权益点=一个交易日，多级别下点数≠交易日数，
        # 故一律按首末快照的真实时间跨度年化（拿不到跨度时才退回 len/252 近似）。
        years = (curve_span_sec / (365.25 * 24 * 3600)) if curve_span_sec and curve_span_sec > 0 else None

        if len(equity_curve) > 1:
            if years and years > 0:
                result.annual_return = (1 + result.total_return) ** (1 / years) - 1
            else:
                n_days = len(equity_curve)
                result.annual_return = (1 + result.total_return) ** (252 / max(n_days, 1)) - 1

        if equity_curve:
            arr = np.array(equity_curve)
            peak = np.maximum.accumulate(arr)
            drawdown = (peak - arr) / peak
            result.max_drawdown = float(np.max(drawdown))

        if len(equity_curve) > 2:
            returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
            # 年化因子按"每年多少个采样点"取，而非写死 252；单级别(点=交易日)时≈252，与旧值一致
            periods_per_year = (len(equity_curve) / years) if years and years > 0 else 252
            if np.std(returns) > 0:
                result.sharpe_ratio = float(np.mean(returns) / np.std(returns) * np.sqrt(periods_per_year))

        if trade_pairs:
            wins = [p for p in trade_pairs if p > 0]
            losses = [p for p in trade_pairs if p <= 0]
            result.win_rate = len(wins) / len(trade_pairs)
            if losses:
                avg_win = np.mean(wins) if wins else 0
                avg_loss = abs(np.mean(losses))
                result.profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

        return result

    def print_report(self, result: BacktestResult):
        """打印回测报告"""
        print("=" * 60)
        print(f"  缠论策略回测报告 — {self.code} [{self.cap.name}]")
        print(f"  区间: {self.begin_time} ~ {self.end_time or 'now'}")
        print(f"  做空: {'支持' if self.cap.support_short else '不支持'}"
              f" | T+0: {'是' if self.cap.t_plus_0 else '否 (T+1约束生效)'}"
              f" | Lot: {self.cap.lot_size}")
        print(f"  级别: {'>'.join(lv.name for lv in self.lv_list)}"
              f" | 取价级别: {self.price_lv.name}")
        print("=" * 60)
        print(f"  初始资金:     ${result.initial_capital:,.2f}")
        print(f"  最终资金:     ${result.final_capital:,.2f}")
        print(f"  总收益率:     {result.total_return*100:.2f}%")
        print(f"  年化收益率:   {result.annual_return*100:.2f}%")
        print(f"  最大回撤:     {result.max_drawdown*100:.2f}%")
        print(f"  夏普比率:     {result.sharpe_ratio:.2f}")
        print(f"  总交易成本:   {result.total_cost:,.2f}")
        print("-" * 60)
        print(f"  总交易信号:   {result.total_trades}")
        print(f"  做多开/平:    {result.buy_trades} / {result.sell_trades}")
        print(f"  做空开/平:    {result.short_trades} / {result.cover_trades}")
        print(f"  胜率:         {result.win_rate*100:.1f}%")
        print(f"  盈亏比:       {result.profit_loss_ratio:.2f}")
        if self.lot_skip_count > 0:
            print(f"  [提示] {self.lot_skip_count} 次开仓因资金不足一手(lot={self.cap.lot_size})被跳过;"
                  f" 高价标的请调高 --capital")
        print("=" * 60)

        if result.trade_history:
            print("\n  交易明细:")
            print(f"  {'时间':<20} {'操作':<6} {'方向':<6} {'价格':>10} {'类型':<8} {'仓位':>6}  原因")
            print("  " + "-" * 90)
            for t in result.trade_history:
                print(f"  {t.time:<20} {t.action:<6} {t.direction:<6} {t.price:>10.2f} {t.bsp_type:<8} "
                      f"{t.position_ratio*100:>5.1f}%  {t.reason}")

    # === 画图: 结构+买卖点+成交标记 / 资金曲线 ===

    @staticmethod
    def _setup_cjk_font() -> Optional[str]:
        """为 matplotlib 配置中文字体(否则中文标记/标题显示为方框)"""
        import matplotlib
        from matplotlib import font_manager
        candidates = ["Microsoft YaHei", "SimHei", "PingFang SC",
                      "Noto Sans CJK SC", "WenQuanYi Zen Hei", "Source Han Sans SC"]
        try:
            available = {f.name for f in font_manager.fontManager.ttflist}
        except Exception:
            return None
        for name in candidates:
            if name in available:
                matplotlib.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
                matplotlib.rcParams["axes.unicode_minus"] = False
                return name
        return None

    # 成交动作 → (标记文字, 箭头方向, 颜色)
    _MARKER_STYLE = {
        "BUY":   ("买", "up",   "green"),
        "SHORT": ("空", "down", "red"),
        "SELL":  ("平多", "down", "black"),
        "COVER": ("平空", "up",   "dimgray"),
        "STOP":  ("止损", "down", "magenta"),
    }

    def _valid_dates(self, lv) -> set:
        """取某级别所有 K 线日期字符串(to_str 格式), 用于过滤 marker 防越界 KeyError"""
        dates = set()
        try:
            for klu in self.chan[lv].klu_iter():
                dates.add(klu.time.to_str())
        except Exception:
            pass
        return dates

    def _build_trade_markers(self, result) -> dict:
        """把成交记录转成 CPlotDriver.draw_marker 需要的 {date: (text, up/down, color)}"""
        if self.chan is None:
            return {}
        valid = self._valid_dates(self.price_lv)
        markers = {}
        for t in result.trade_history:
            key = str(t.time)
            if key not in valid:
                continue  # 日期不在操作级别坐标轴上(如跨级别/停牌), 跳过防 KeyError
            if t.bsp_type == "STOP":
                text, pos, color = self._MARKER_STYLE["STOP"]
            else:
                text, pos, color = self._MARKER_STYLE.get(t.action, (t.action, "up", "blue"))
            # 开仓标记附带买卖点类型, 便于看清是哪类信号触发
            if t.action in ("BUY", "SHORT") and t.bsp_type:
                text = f"{text}·{t.bsp_type}"
            if key in markers:  # 同日多笔: 合并文字, 方向/颜色取先者
                old_text, old_pos, old_color = markers[key]
                markers[key] = (f"{old_text}/{text}", old_pos, old_color)
            else:
                markers[key] = (text, pos, color)
        return markers

    def _build_veto_markers(self) -> dict:
        """把未成交的结构买卖点(SKIP/VETO/HOLD/COOLDOWN)转成橙色 ×原因 标注"""
        if self.chan is None:
            return {}
        valid = self._valid_dates(self.price_lv)
        veto_outcomes = {"SKIP", "VETO", "HOLD", "COOLDOWN"}
        out = {}
        for d in self.bsp_decisions:
            if d.outcome not in veto_outcomes:
                continue
            key = str(d.time)
            if key not in valid:
                continue
            if d.outcome == "SKIP":
                tag = "×满仓"
            elif d.outcome == "HOLD":
                tag = "×持有"
            elif d.outcome == "COOLDOWN":
                tag = "×冷却"
            else:  # VETO
                if "级别" in d.reason:
                    tag = "×级别"
                elif "均线" in d.reason:
                    tag = "×均线"
                else:
                    tag = "×拦"
            if d.middle_yin:
                tag += "·中阴"
            pos = "up" if d.is_buy else "down"
            if key in out:
                out[key] = (out[key][0] + "/" + tag, out[key][1], "darkorange")
            else:
                out[key] = (tag, pos, "darkorange")
        return out

    def plot(self, result, out_prefix: Optional[str] = None, x_range: int = 0,
             figsize=(24, 10), dpi: int = 120):
        """
        画两张图并返回路径:
          1) {prefix}_trades.png : 缠论结构(K线/笔/线段/中枢/结构买卖点/MACD) + 实际成交标记
             多级别时每个级别一张子图, 成交标记只画在取价级别(操作级别)上;
          2) {prefix}_equity.png : 资金曲线 + 回撤附图。
        x_range=0 表示画全部K线; >0 只画最近 x_range 根。
        """
        if self.chan is None:
            raise RuntimeError("请先调用 run() 再 plot()")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from Plot.PlotDriver import CPlotDriver
        self._setup_cjk_font()

        code_safe = self.code.replace("/", "_").replace(".", "_")
        out_prefix = out_prefix or code_safe
        markers = self._build_trade_markers(result)
        # 叠加未成交结构点的 veto 标注(橙色 ×原因); 与成交标记同日则合并
        for k, v in self._build_veto_markers().items():
            if k in markers:
                markers[k] = (markers[k][0] + " | " + v[0], markers[k][1], markers[k][2])
            else:
                markers[k] = v

        # 每级别绘图配置; 仅操作级别开 marker(其余级别日期轴不同, 开了会 KeyError)
        xr = x_range if x_range and x_range > 0 else max(200, len(self.chan[self.price_lv]) + 10)
        plot_config = {}
        for lv in self.lv_list:
            cfg = {
                "plot_kline": True, "plot_kline_combine": True,
                "plot_bi": True, "plot_seg": True, "plot_zs": True,
                "plot_bsp": True, "plot_macd": True,
            }
            if lv == self.price_lv:
                cfg["plot_marker"] = True
            plot_config[lv] = cfg
        plot_para = {
            "figure": {"w": figsize[0], "h": figsize[1], "x_range": xr, "grid": "xy"},
            "marker": {"markers": markers},
        }
        driver = CPlotDriver(self.chan, plot_config=plot_config, plot_para=plot_para)
        trades_png = f"{out_prefix}_trades.png"
        driver.figure.savefig(trades_png, dpi=dpi, bbox_inches="tight")
        plt.close(driver.figure)

        equity_png = f"{out_prefix}_equity.png"
        self._plot_equity(result, equity_png, dpi=dpi)
        return trades_png, equity_png

    def _plot_equity(self, result, path: str, dpi: int = 120):
        """资金曲线 + 回撤附图"""
        eq = result.equity_curve
        if not eq or len(eq) < 2:
            return
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        self._setup_cjk_font()
        arr = np.array(eq, dtype=float)
        peak = np.maximum.accumulate(arr)
        dd = (peak - arr) / peak * 100.0
        x = np.arange(len(arr))

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(14, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
        )
        ax1.plot(x, arr, color="navy", lw=1.0, label="equity")
        ax1.axhline(result.initial_capital, color="gray", ls="--", lw=0.8)
        ax1.set_title(
            f"{self.code} 资金曲线  初始 {result.initial_capital:,.0f} → "
            f"最终 {result.final_capital:,.0f}  ({result.total_return*100:+.2f}%)  "
            f"夏普 {result.sharpe_ratio:.2f}  胜率 {result.win_rate*100:.1f}%"
        )
        ax1.set_ylabel("equity")
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc="upper left")

        ax2.fill_between(x, -dd, 0, color="firebrick", alpha=0.5)
        ax2.set_ylabel("drawdown %")
        ax2.set_xlabel("bar")
        ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        fig.savefig(path, dpi=dpi)
        plt.close(fig)

