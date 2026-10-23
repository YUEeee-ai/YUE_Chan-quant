"""
市场能力抽象层 — 统一管理 A股/港股/美股/加密货币 的交易规则差异

不同市场关键差异：
- 做空支持: A股零售账户不支持做空, 港股/美股/加密货币支持
- T+0/T+1: A股 T+1 当日买入不能卖出; 港股/美股 T+0
- 印花税: A股 卖出 0.1%(2023.08 后单边), 港股 0.1%, 美股 0
- 佣金: A股 万 1-万 3, 港股 万 5-千 2.7, 美股 0 (Alpaca/IB 大多免佣)
- 过户费: A股 万 0.1 (仅沪市, 深市已免除), 港股无, 美股无
- 最小交易单位: A股 100 股 (1 手), 港股 视个股 (100/500/1000/2000), 美股 1 股
- 碎股: A股/港股 不允许, 美股 允许

使用:
    from Common.MarketCapability import get_market_capability, MARKET
    cap = get_market_capability(MARKET.US)
    if cap.support_short:
        ...
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class MARKET(Enum):
    CN = "cn"        # A股 (Shanghai + Shenzhen)
    HK = "hk"        # 港股
    US = "us"        # 美股
    CRYPTO = "crypto" # 加密货币


@dataclass
class MarketCapability:
    """市场交易能力描述"""
    name: str
    market: 'MARKET'             # 市场枚举 (费率分支据此判定, 避免依赖中文 name)
    support_short: bool          # 是否支持做空
    t_plus_0: bool               # 是否 T+0 (True=T+0 当天可平, False=T+1)
    stamp_tax: float             # 印花税率 (单边, 卖出时收)
    commission_rate: float       # 券商佣金率 (单边)
    transfer_fee: float          # 过户费率 (单边, 仅沪市 A 股)
    lot_size: int                # 一手股数
    allow_fractional: bool       # 是否允许碎股
    price_limit_rate: float      # 涨跌停幅度 (0 表示无限制)
    currency: str                # 货币符号


# 各市场默认能力表
# 数据来源: 2024 年规则, 若规则变化需要更新
DEFAULT_CAPABILITIES: Dict[MARKET, MarketCapability] = {
    MARKET.CN: MarketCapability(
        name="A股",
        market=MARKET.CN,
        support_short=False,      # 融券做空需专门账户, 默认关闭
        t_plus_0=False,            # T+1
        stamp_tax=0.0005,          # 印花税 0.05% 单边 (2023.08 从 0.1% 减半)
        commission_rate=0.00025,   # 万 2.5 单边 (主流券商最低)
        transfer_fee=0.00001,      # 沪市过户费万 0.1
        lot_size=100,               # 一手 100 股
        allow_fractional=False,
        price_limit_rate=0.10,      # 主板 ±10% (科创板/创业板 ±20%)
        currency="CNY",
    ),
    MARKET.HK: MarketCapability(
        name="港股",
        market=MARKET.HK,
        support_short=True,         # 支持卖空 (指定可空股票)
        t_plus_0=True,
        stamp_tax=0.001,            # 印花税 0.1% 双边
        commission_rate=0.0003,     # 万 3 单边 (Futu/富途 0.03%)
        transfer_fee=0.00002,       # 交收费 0.002%
        lot_size=100,               # 大部分港股一手 100/500/1000/2000, 视个股
        allow_fractional=False,
        price_limit_rate=0.0,       # 无涨跌停
        currency="HKD",
    ),
    MARKET.US: MarketCapability(
        name="美股",
        market=MARKET.US,
        support_short=True,         # Alpaca/IB 支持做空
        t_plus_0=True,
        stamp_tax=0.0,               # 美股无印花税
        commission_rate=0.0005,      # Alpaca 无最低消费时约 0.0005 (含 SEC/FINRA fee)
        transfer_fee=0.0,
        lot_size=1,                   # 最小 1 股
        allow_fractional=True,        # Alpaca 支持碎股
        price_limit_rate=0.0,
        currency="USD",
    ),
    MARKET.CRYPTO: MarketCapability(
        name="加密货币",
        market=MARKET.CRYPTO,
        support_short=True,           # 合约 / 杠杆支持做空
        t_plus_0=True,
        stamp_tax=0.0,
        commission_rate=0.001,        # 现货 maker/taker 约 0.1%
        transfer_fee=0.0,
        lot_size=1,
        allow_fractional=True,
        price_limit_rate=0.0,
        currency="USDT",
    ),
}


# DATA_SRC → MARKET 映射
from Common.CEnum import DATA_SRC

DATA_SRC_TO_MARKET: Dict[DATA_SRC, MARKET] = {
    DATA_SRC.BAO_STOCK: MARKET.CN,
    DATA_SRC.CCXT: MARKET.CRYPTO,
    DATA_SRC.US_STOCK: MARKET.US,
    # Futu/AkShare 需要根据 code 前缀动态判断
}


def detect_market(data_src: DATA_SRC, code: str) -> MARKET:
    """
    根据数据源和股票代码推断市场:
    - BaoStock: 一定是 A 股 (sz./sh.)
    - ccxt: 加密货币 (BTC/USDT)
    - US_STOCK (yfinance): 可取美/港/A股, 按代码后缀判断 ——
        *.HK → 港股; *.SS/*.SZ/*.SH (或 6 位数字) → A股; 其余 → 美股
    - Futu/AkShare: 根据 code 前缀 (HK./US./SZ./SH.)
    """
    code_upper = (code or "").upper()

    # 加密货币: 形如 BTC/USDT
    if data_src == DATA_SRC.CCXT or "/" in code:
        return MARKET.CRYPTO
    # BaoStock: 固定 A 股
    if data_src == DATA_SRC.BAO_STOCK:
        return MARKET.CN

    # yfinance 后缀路由 (美/港/A 三市统一取数)
    if code_upper.endswith(".HK"):
        return MARKET.HK
    if code_upper.endswith((".SS", ".SZ", ".SH")):
        return MARKET.CN
    # Futu 风格前缀路由
    if code_upper.startswith("HK."):
        return MARKET.HK
    if code_upper.startswith("US."):
        return MARKET.US
    if code_upper.startswith(("SZ.", "SH.")):
        return MARKET.CN
    # 纯 6 位数字 → A 股代码
    head = code_upper.split(".")[0]
    if head.isdigit() and len(head) == 6:
        return MARKET.CN
    # 纯字母 ticker(无点/斜杠) → 美股
    if "." not in code and code.isalpha():
        return MARKET.US
    # 默认美股
    return MARKET.US



def get_market_capability(market: MARKET) -> MarketCapability:
    """获取市场能力描述"""
    return DEFAULT_CAPABILITIES[market]
