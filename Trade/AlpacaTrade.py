"""
Alpaca Markets 美股交易执行器 — 继承 BaseTrader

API 文档: https://docs.alpaca.markets/
注册:     https://app.alpaca.markets/ (免费 Paper Trading)

环境变量:
    ALPACA_API_KEY    - API Key
    ALPACA_API_SECRET - API Secret
"""
import os
import time
from typing import Dict, List, Optional

from Trade.Base import BaseTrader, ChanTradeExecutor, OrderResult, TradeMode  # noqa: F401

# Alpaca SDK 是可选依赖, 仅在实盘/模拟盘交易时需要
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        LimitOrderRequest,
        MarketOrderRequest,
        ClosePositionRequest,
    )
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.data.historical import StockHistoricalDataClient
    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False


class AlpacaTrader(BaseTrader):
    """
    Alpaca 美股交易执行器

    使用方式:
        trader = AlpacaTrader(mode=TradeMode.PAPER)
        result = trader.buy("AAPL", notional=10000)
        result = trader.sell("AAPL", percentage=1.0)
        positions = trader.get_positions()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        mode: TradeMode = TradeMode.PAPER,
    ):
        super().__init__(mode=mode)
        if not _ALPACA_AVAILABLE:
            raise ImportError("alpaca-py 未安装。请执行: pip install alpaca-py")
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("ALPACA_API_SECRET", "")
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "请设置 ALPACA_API_KEY 和 ALPACA_API_SECRET 环境变量，"
                "或在构造函数中传入。注册: https://app.alpaca.markets/"
            )

        paper = (mode == TradeMode.PAPER)
        self.client = TradingClient(self.api_key, self.api_secret, paper=paper)
        self.data_client = StockHistoricalDataClient(self.api_key, self.api_secret)

        try:
            account = self.client.get_account()
            print(f"[Alpaca] 连接成功 | 模式={'Paper' if paper else 'LIVE'} | "
                  f"资金=${account.cash if hasattr(account, 'cash') else 'N/A'}")
        except Exception as e:
            raise ConnectionError(f"[Alpaca] 连接失败: {e}")

    # === BaseTrader 接口实现 ===

    def buy(self, symbol: str, qty: Optional[float] = None,
            notional: Optional[float] = None,
            limit_price: Optional[float] = None) -> OrderResult:
        try:
            if limit_price:
                order_req = LimitOrderRequest(
                    symbol=symbol, qty=qty, side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY, limit_price=limit_price,
                )
            else:
                order_req = MarketOrderRequest(
                    symbol=symbol, qty=qty, notional=notional,
                    side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                )
            order = self.client.submit_order(order_data=order_req)
            order = self._wait_for_fill(order.id)
            return self._to_result(order, fallback_qty=qty or 0)
        except Exception as e:
            return OrderResult(success=False, error_msg=str(e))

    def sell(self, symbol: str, qty: Optional[float] = None,
             percentage: Optional[float] = None,
             limit_price: Optional[float] = None) -> OrderResult:
        try:
            if percentage is not None:
                # Alpaca percentage 语义: 1–100 的百分数(调用方传 0–1 小数, 需 *100)
                pct = int(round(max(0.0, min(1.0, float(percentage))) * 100))
                order = self.client.close_position(
                    symbol,
                    close_position_requests=ClosePositionRequest(percentage=pct),
                )
                order = self._wait_for_fill(order.id)
                return self._to_result(order)
            if limit_price:
                order_req = LimitOrderRequest(
                    symbol=symbol, qty=qty, side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY, limit_price=limit_price,
                )
            else:
                order_req = MarketOrderRequest(
                    symbol=symbol, qty=qty, side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
            order = self.client.submit_order(order_data=order_req)
            order = self._wait_for_fill(order.id)
            return self._to_result(order, fallback_qty=qty or 0)
        except Exception as e:
            return OrderResult(success=False, error_msg=str(e))

    def get_positions(self) -> List[Dict]:
        try:
            positions = self.client.get_all_positions()
            return [{
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price) if p.current_price else 0,
                "unrealized_pnl": float(p.unrealized_pl) if p.unrealized_pl else 0,
                "unrealized_pnl_pct": float(p.unrealized_plpc) if p.unrealized_plpc else 0,
            } for p in positions]
        except Exception as e:
            print(f"[Alpaca] 获取持仓失败: {e}")
            return []

    def get_account_info(self) -> Dict:
        try:
            account = self.client.get_account()
            return {
                "cash": float(account.cash),
                "portfolio_value": float(account.portfolio_value),
                "buying_power": float(account.buying_power),
                "equity": float(account.equity),
                "status": account.status,
            }
        except Exception as e:
            print(f"[Alpaca] 获取账户失败: {e}")
            return {}

    def get_price(self, symbol: str) -> Optional[float]:
        try:
            from alpaca.data.requests import StockLatestTradeRequest
            request = StockLatestTradeRequest(symbol_or_symbols=symbol)
            trade = self.data_client.get_stock_latest_trade(request)
            if symbol in trade:
                return float(trade[symbol].price)
        except Exception:
            pass
        return None

    def _to_result(self, order, fallback_qty: float = 0.0) -> OrderResult:
        """把订单转成 OrderResult, 严格校验成交状态(拒单/撤单不得当成功)"""
        status = str(getattr(order, "status", ""))
        if status in ("filled", "partially_filled"):
            return OrderResult(
                success=True, order_id=str(order.id),
                filled_price=float(order.filled_avg_price) if order.filled_avg_price else 0,
                filled_qty=float(order.filled_qty) if order.filled_qty else (fallback_qty or 0),
            )
        return OrderResult(
            success=False, order_id=str(getattr(order, "id", "")),
            error_msg=f"订单未成交(status={status})",
        )

    def _wait_for_fill(self, order_id, timeout=10, interval=0.5):
        """等待订单成交"""
        start = time.time()
        while time.time() - start < timeout:
            order = self.client.get_order_by_id(str(order_id))
            if order.status in ("filled", "partially_filled", "cancelled", "rejected"):
                return order
            time.sleep(interval)
        return self.client.get_order_by_id(str(order_id))
