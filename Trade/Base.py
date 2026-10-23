"""
交易执行器抽象基类 — 统一 Alpaca (美股) / Futu (港股/A股/美股) / 其他券商

设计原则:
1. Trader 只关心 "下单/查持仓/查账户" 底层能力
2. ChanTradeExecutor (通用桥接器) 把 TradeRecord 翻译成 Trader 调用, 并施加市场规则
3. 市场能力差异 (做空/T+1/lot size/仓位基数) 由 MarketCapability 描述, 执行器据此
   与 Backtester 保持一致的约束 (回测能跑的规则, 实盘执行器同样拦得住)
"""
import abc
import datetime
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional


class TradeMode(Enum):
    PAPER = auto()  # 模拟盘
    LIVE = auto()   # 实盘


@dataclass
class OrderResult:
    """下单结果"""
    success: bool
    order_id: str = ""
    filled_price: float = 0.0
    filled_qty: float = 0.0
    error_msg: str = ""


class BaseTrader(abc.ABC):
    """
    交易器抽象基类

    实现者需要提供 5 个方法:
    - buy(symbol, qty|notional, limit_price)  开多/平空
    - sell(symbol, qty|percentage, limit_price) 平多/开空
    - get_positions() → List[Dict]  查询持仓 (含负数量表示空头)
    - get_account_info() → Dict  查询账户资金/购买力
    - get_price(symbol) → Optional[float]  查询最新价
    """

    def __init__(self, mode: TradeMode = TradeMode.PAPER):
        self.mode = mode

    @abc.abstractmethod
    def buy(self, symbol: str, qty: Optional[float] = None,
            notional: Optional[float] = None,
            limit_price: Optional[float] = None) -> OrderResult:
        ...

    @abc.abstractmethod
    def sell(self, symbol: str, qty: Optional[float] = None,
             percentage: Optional[float] = None,
             limit_price: Optional[float] = None) -> OrderResult:
        ...

    @abc.abstractmethod
    def get_positions(self) -> List[Dict]:
        ...

    @abc.abstractmethod
    def get_account_info(self) -> Dict:
        ...

    def get_price(self, symbol: str) -> Optional[float]:
        return None


class ChanTradeExecutor:
    """
    缠论策略 → 交易器桥接 (与具体券商无关)

    将 ChanStrategy 产生的 TradeRecord 翻译成 BaseTrader 调用:
      BUY   → trader.buy(notional)     开多
      SELL  → trader.sell(percentage)  平多
      SHORT → trader.sell(qty)         开空 (负持仓)
      COVER → trader.buy(qty)          平空 (买回)

    市场规则 (与 Backtester 对齐, 由 market_cap: MarketCapability 描述):
      - 做空能力: 市场不支持做空(如 A 股零售)时, SHORT/COVER 一律拒单;
      - lot 取整: 不允许碎股时按 lot_size 向下取整到整手, 不足一手则跳过;
      - T+1:  非 T+0 市场记录建仓自然日, 当日开、当日平被拒绝(次日才可平);
      - 仓位: 优先用账户总权益动态 sizing, 拿不到再退回固定 max_position_value。

    使用方式:
        executor = ChanTradeExecutor(
            trader, symbol="AAPL", max_position_value=100000, market_cap=cap)
        for snapshot in chan.step_load():
            stop = strategy.check_stop_loss(price)
            if stop and executor.execute(stop):
                strategy.apply_stop(stop)
            rec = strategy.on_bar(snapshot)
            if rec:
                executor.execute(rec)
    """

    def __init__(
        self,
        trader: BaseTrader,
        symbol: str,
        max_position_value: float = 50000.0,
        dry_run: bool = True,
        market_cap=None,
    ):
        self.trader = trader
        self.symbol = symbol.upper() if isinstance(symbol, str) else symbol
        self.max_position_value = max_position_value
        self.dry_run = dry_run
        # 市场能力 (None = 不施加额外规则, 兼容旧调用)
        self.cap = market_cap
        # T+1 建仓自然日跟踪 (方向 → date)
        self._open_date: Dict[str, datetime.date] = {}

    # === 市场规则辅助 ===

    @property
    def _support_short(self) -> bool:
        return (self.cap is None) or self.cap.support_short

    @property
    def _t_plus_0(self) -> bool:
        return (self.cap is None) or self.cap.t_plus_0

    def _round_qty(self, qty: float) -> float:
        """按 lot_size 取整 (不允许碎股时向下取整到整手)"""
        if self.cap is None or self.cap.allow_fractional or self.cap.lot_size <= 1:
            return qty
        lots = int(qty // self.cap.lot_size)
        return lots * self.cap.lot_size

    def _buying_power(self) -> float:
        """动态仓位基数: 账户总权益优先, 拿不到再退回 max_position_value"""
        try:
            info = self.trader.get_account_info() or {}
            pv = float(info.get("portfolio_value", 0) or info.get("equity", 0) or 0)
            if pv > 0:
                return pv
        except Exception:
            pass
        return self.max_position_value

    def _held_qty(self) -> float:
        """查询当前该标的持仓数量 (正=多头, 负=空头, 未知=0)"""
        try:
            for p in self.trader.get_positions():
                if p.get("symbol", "").upper() == self.symbol:
                    return float(p.get("qty", 0))
        except Exception:
            pass
        return 0.0

    def _today(self) -> datetime.date:
        return datetime.date.today()

    def _t1_block(self, direction: str) -> bool:
        """T+1: 非 T+0 市场且该方向建仓发生在今天 → 禁止当日平 (True=应拒绝)"""
        if self._t_plus_0:
            return False
        return self._open_date.get(direction) == self._today()

    def execute(self, record) -> bool:
        """执行交易信号 (多空四向)"""
        if record.action == "BUY":
            return self._exec_buy(record)
        elif record.action == "SELL":
            return self._exec_sell(record)
        elif record.action == "SHORT":
            return self._exec_short(record)
        elif record.action == "COVER":
            return self._exec_cover(record)
        return False

    def _exec_buy(self, record) -> bool:
        buy_value = self._buying_power() * record.position_ratio
        if buy_value < 1:
            return False
        held = self._held_qty()
        est_qty = buy_value / record.price if record.price > 0 else 0
        est_qty = self._round_qty(est_qty)
        if self.dry_run:
            print(f"[DRY-RUN] BUY(LONG) {self.symbol} ${buy_value:.2f} ~{est_qty:.0f}股 "
                  f"@ ~{record.price:.2f} | {record.bsp_type} | {record.reason}")
            if held <= 0.001:
                self._open_date["LONG"] = self._today()
            return True
        if est_qty < 1:
            print(f"[SKIP] BUY {self.symbol}: 资金不足一手")
            return False
        result = self.trader.buy(self.symbol, qty=float(est_qty))
        if result.success and held <= 0.001:
            self._open_date["LONG"] = self._today()
        self._log_result("BUY(LONG)", result)
        return result.success

    def _exec_sell(self, record) -> bool:
        sell_pct = min(1.0, abs(record.position_ratio))
        if not self._t_plus_0 and self._t1_block("LONG"):
            print(f"[T+1 BLOCK] SELL {self.symbol}: 今日建仓不可当日平")
            return False
        if self.dry_run:
            print(f"[DRY-RUN] SELL(CLOSE_LONG) {self.symbol} {sell_pct*100:.0f}%持仓 "
                  f"@ ~{record.price:.2f} | {record.bsp_type} | {record.reason}")
            if sell_pct >= 0.999:
                self._open_date.pop("LONG", None)
            return True
        result = self.trader.sell(self.symbol, percentage=sell_pct)
        if result.success and sell_pct >= 0.999:
            self._open_date.pop("LONG", None)
        self._log_result("SELL(CLOSE_LONG)", result)
        return result.success

    def _exec_short(self, record) -> bool:
        if not self._support_short:
            print(f"[GATE] SHORT {self.symbol}: 市场不支持做空, 已拒绝")
            return False
        short_value = self._buying_power() * record.position_ratio
        if short_value < 1:
            return False
        held = self._held_qty()
        est_qty = short_value / record.price if record.price > 0 else 0
        est_qty = self._round_qty(est_qty)
        if est_qty < 1:
            print(f"[SKIP] SHORT {self.symbol}: 资金不足一手")
            return False
        if self.dry_run:
            print(f"[DRY-RUN] SHORT {self.symbol} ~{est_qty:.0f}股 (${short_value:.2f}) "
                  f"@ ~{record.price:.2f} | {record.bsp_type} | {record.reason}")
            if held >= -0.001:
                self._open_date["SHORT"] = self._today()
            return True
        result = self.trader.sell(self.symbol, qty=float(est_qty))
        if result.success and held >= -0.001:
            self._open_date["SHORT"] = self._today()
        self._log_result("SHORT", result)
        return result.success

    def _exec_cover(self, record) -> bool:
        if not self._support_short:
            print(f"[GATE] COVER {self.symbol}: 市场不支持做空, 已拒绝")
            return False
        if not self._t_plus_0 and self._t1_block("SHORT"):
            print(f"[T+1 BLOCK] COVER {self.symbol}: 今日开空不可当日回补")
            return False
        cover_pct = min(1.0, abs(record.position_ratio))
        if self.dry_run:
            print(f"[DRY-RUN] COVER(CLOSE_SHORT) {self.symbol} {cover_pct*100:.0f}%空头 "
                  f"@ ~{record.price:.2f} | {record.bsp_type} | {record.reason}")
            if cover_pct >= 0.999:
                self._open_date.pop("SHORT", None)
            return True
        # 查询当前空头数量, BUY 回补
        held = self._held_qty()
        short_qty = abs(held) if held < 0 else 0.0
        if short_qty <= 0:
            print(f"[SKIP] COVER {self.symbol}: 无空头持仓可平")
            return False
        buy_qty = self._round_qty(short_qty * cover_pct)
        if buy_qty < 1:
            print(f"[SKIP] COVER {self.symbol}: 回补不足一手")
            return False
        result = self.trader.buy(self.symbol, qty=float(buy_qty))
        if result.success and cover_pct >= 0.999:
            self._open_date.pop("SHORT", None)
        self._log_result("COVER(CLOSE_SHORT)", result)
        return result.success

    def _log_result(self, tag: str, result: OrderResult):
        if result.success:
            print(f"[FILLED] {tag} {self.symbol} "
                  f"{result.filled_qty:.2f}股 @ ${result.filled_price:.2f}")
        else:
            print(f"[FAILED] {tag} {self.symbol}: {result.error_msg}")
