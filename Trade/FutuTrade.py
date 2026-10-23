"""
Futu (富途) 交易执行器 — 港股/A股/美股

本模块提供基于 futu-api 的完整交易执行: 下单/查持仓/查账户/取价,
通过 BaseTrader 抽象接入 ChanTradeExecutor, 供 --mode live --broker futu 使用。

依赖:
    pip install futu-api
    运行 Futu OpenD 客户端 (https://www.futunn.com/download/openAPI)

环境变量 / 配置:
    FUTU_HOST         - OpenD 主机, 默认 127.0.0.1
    FUTU_PORT         - OpenD 端口, 默认 11111
    FUTU_PWD_MD5      - 交易密码 MD5
    FUTU_RSA_PATH     - RSA 鉴权文件路径 (可选)
    FUTU_ENV          - SIMULATE / REAL
"""
import os
from typing import Dict, List, Optional

from Trade.Base import BaseTrader, OrderResult, TradeMode

try:
    from futu import (
        OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm,
        RET_OK, OrderType, TrdSide, TimeInForce,
    )
    _FUTU_AVAILABLE = True
except ImportError:
    _FUTU_AVAILABLE = False


# code 前缀 → 富途市场
_CODE_TO_MARKET = {
    "HK.": TrdMarket.HK if _FUTU_AVAILABLE else "HK",
    "US.": TrdMarket.US if _FUTU_AVAILABLE else "US",
    "SH.": TrdMarket.CN if _FUTU_AVAILABLE else "CN",
    "SZ.": TrdMarket.CN if _FUTU_AVAILABLE else "CN",
}


def _detect_futu_market(code: str):
    """根据 code 前缀推断 Futu 市场"""
    for prefix, market in _CODE_TO_MARKET.items():
        if code.upper().startswith(prefix):
            return market
    return _CODE_TO_MARKET.get("HK.")


class FutuTrader(BaseTrader):
    """
    Futu 富途交易执行器 (港股/A股/美股)

    使用方式:
        trader = FutuTrader(mode=TradeMode.PAPER)  # PAPER → SIMULATE 模拟盘
        result = trader.buy("HK.00700", qty=100)
        result = trader.sell("HK.00700", qty=100)
        positions = trader.get_positions()

    覆盖 BaseTrader 五件套: buy / sell / get_positions / get_account_info / get_price,
    行情与交易走 OpenD 上下文(按市场缓存, 首次使用时自动解锁交易).
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        pwd_md5: Optional[str] = None,
        rsa_path: Optional[str] = None,
        mode: TradeMode = TradeMode.PAPER,
    ):
        super().__init__(mode=mode)
        if not _FUTU_AVAILABLE:
            raise ImportError(
                "futu-api 未安装。请执行: pip install futu-api "
                "并运行 Futu OpenD 客户端"
            )
        self.host = host or os.environ.get("FUTU_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("FUTU_PORT", "11111"))
        self.pwd_md5 = pwd_md5 or os.environ.get("FUTU_PWD_MD5", "")
        self.rsa_path = rsa_path or os.environ.get("FUTU_RSA_PATH", "")
        self.trd_env = TrdEnv.SIMULATE if mode == TradeMode.PAPER else TrdEnv.REAL

        # 各市场独立 TradeContext (Futu 要求)
        self._ctx: Dict[str, OpenSecTradeContext] = {}

    def _get_ctx(self, code: str) -> "OpenSecTradeContext":
        """按 code 前缀获取对应市场的交易上下文"""
        market = _detect_futu_market(code)
        key = str(market)
        if key not in self._ctx:
            self._ctx[key] = OpenSecTradeContext(
                filter_trdmarket=market,
                host=self.host, port=self.port,
                security_firm=SecurityFirm.FUTUSECURITIES,
            )
            if self.pwd_md5:
                rsa_data = ""
                if self.rsa_path and os.path.exists(self.rsa_path):
                    with open(self.rsa_path, "r") as f:
                        rsa_data = f.read()
                self._ctx[key].unlock_trade(self.pwd_md5, rsa_data)
        return self._ctx[key]

    # === BaseTrader 接口实现 ===

    def buy(self, symbol: str, qty: Optional[float] = None,
            notional: Optional[float] = None,
            limit_price: Optional[float] = None) -> OrderResult:
        if not _FUTU_AVAILABLE:
            return OrderResult(success=False, error_msg="futu-api not installed")
        try:
            ctx = self._get_ctx(symbol)
            price = limit_price or self.get_price(symbol)
            if price is None:
                return OrderResult(success=False, error_msg="无法获取价格")
            if qty is None and notional:
                qty = int(notional / price)
            ret, data = ctx.place_order(
                price=price, qty=int(qty), code=symbol,
                trd_side=TrdSide.BUY,
                order_type=OrderType.NORMAL if limit_price else OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
                trd_env=self.trd_env,
            )
            if ret == RET_OK:
                return OrderResult(
                    success=True,
                    order_id=str(data["order_id"].iloc[0]),
                    filled_price=price,
                    filled_qty=float(qty),
                )
            return OrderResult(success=False, error_msg=str(data))
        except Exception as e:
            return OrderResult(success=False, error_msg=str(e))

    def sell(self, symbol: str, qty: Optional[float] = None,
             percentage: Optional[float] = None,
             limit_price: Optional[float] = None) -> OrderResult:
        if not _FUTU_AVAILABLE:
            return OrderResult(success=False, error_msg="futu-api not installed")
        try:
            ctx = self._get_ctx(symbol)
            # Futu 不支持 close_position 语义, 需自己查持仓
            if percentage and not qty:
                positions = self.get_positions()
                for p in positions:
                    if p["symbol"] == symbol:
                        qty = int(abs(p["qty"]) * percentage)
                        break
            if not qty:
                return OrderResult(success=False, error_msg="无持仓或数量为0")
            price = limit_price or self.get_price(symbol)
            if price is None:
                return OrderResult(success=False, error_msg="无法获取价格")
            ret, data = ctx.place_order(
                price=price, qty=int(qty), code=symbol,
                trd_side=TrdSide.SELL,
                order_type=OrderType.NORMAL if limit_price else OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
                trd_env=self.trd_env,
            )
            if ret == RET_OK:
                return OrderResult(
                    success=True,
                    order_id=str(data["order_id"].iloc[0]),
                    filled_price=price,
                    filled_qty=float(qty),
                )
            return OrderResult(success=False, error_msg=str(data))
        except Exception as e:
            return OrderResult(success=False, error_msg=str(e))

    def get_positions(self) -> List[Dict]:
        if not _FUTU_AVAILABLE:
            return []
        result = []
        for ctx in self._ctx.values():
            try:
                ret, data = ctx.position_list_query(trd_env=self.trd_env)
                if ret == RET_OK:
                    for _, row in data.iterrows():
                        result.append({
                            "symbol": row["code"],
                            "qty": float(row["qty"]),
                            "avg_entry_price": float(row["cost_price"]),
                            "current_price": float(row.get("nominal_price", 0)),
                            "unrealized_pnl": float(row.get("pl_val", 0)),
                            "unrealized_pnl_pct": float(row.get("pl_ratio", 0)),
                        })
            except Exception as e:
                print(f"[Futu] 查询持仓失败: {e}")
        return result

    def get_account_info(self) -> Dict:
        if not _FUTU_AVAILABLE:
            return {}
        info: Dict = {}
        for market, ctx in self._ctx.items():
            try:
                ret, data = ctx.accinfo_query(trd_env=self.trd_env)
                if ret == RET_OK and len(data) > 0:
                    row = data.iloc[0]
                    info[market] = {
                        "cash": float(row.get("cash", 0)),
                        "power": float(row.get("power", 0)),
                        "total_assets": float(row.get("total_assets", 0)),
                        "market_val": float(row.get("market_val", 0)),
                    }
            except Exception as e:
                print(f"[Futu] 查询账户失败: {e}")
        return info

    def get_price(self, symbol: str) -> Optional[float]:
        """取最新价: 优先用持仓现价; 无持仓(新开仓)时查行情快照 last_price 兜底"""
        for p in self.get_positions():
            if p["symbol"] == symbol and p["current_price"] > 0:
                return p["current_price"]
        try:
            ctx = self._get_ctx(symbol)
            ret, data = ctx.get_market_snapshot([symbol])
            if ret == RET_OK and len(data) > 0:
                price = float(data.iloc[0].get("last_price", 0))
                if price > 0:
                    return price
        except Exception as e:
            print(f"[Futu] 行情快照取价失败 {symbol}: {e}")
        return None

    def close(self):
        """关闭所有交易上下文"""
        for ctx in self._ctx.values():
            try:
                ctx.close()
            except Exception:
                pass
        self._ctx.clear()
