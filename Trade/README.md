# Trade —— 交易执行抽象 / 券商适配（Alpaca、Futu）

## 一、模块定位

`Trade` 是**实盘/模拟盘执行层**：把 `Strategy.ChanStrategy` 产出的 `TradeRecord`（`BUY/SELL/SHORT/COVER`）
翻译成真实券商的下单动作，并在下单前后施加与回测器**完全一致**的市场规则（做空能力、T+1、
lot 取整、仓位基数）。核心思想是"**回测能跑的规则，实盘执行器同样拦得住**"。

组成：

- `Base.py`：券商无关的抽象层——`BaseTrader`（五件套底层能力）、`ChanTradeExecutor`
  （TradeRecord→券商调用的桥接器，市场规则在此）、`TradeMode`、`OrderResult`。
- `AlpacaTrade.py`：`AlpacaTrader`，美股（alpaca-py SDK），Paper/Live 双模。
- `FutuTrade.py`：`FutuTrader`，港股/A 股/美股（futu-api + OpenD 客户端），按市场缓存交易上下文。

本层是**工程基础设施**——把策略信号落到券商接口、统一多市场风控，缠论原典对其**没有直接对应课**。
仅在"止损 / 仓位 / 资金管理"的**理念**层面与第 26、31 课相关，故少量引用（见下）。

## 二、对应缠论课程

**无直接原典对应，服务于"交易执行/风控落地"层。** 间接关联的理念课：

- 第 26 课《市场风险如何回避》：交易前提（钱要长期无压力）、"唯一需要控制的是量"、
  卖点卖错无所谓而买点须谨慎（对应执行器对追高/资金不足一手的拒绝）。
- 第 31 课《资金管理的最稳固基础》：仓位基数、绝不往上加码、永远保持警觉
  （对应 `_buying_power` 动态 sizing、开仓前的资金/一手校验与告警）。

## 三、书中关键原文

> "市场的唯一风险就是你投入的钱在后面的时刻不能用相应的凭证换成更多的钱，除此之外，一切的风险都是狗屁风险。"
>
> "只要有卖点，就要卖出，只要有买点就要买入，唯一需要控制的，就是量。"
>
> "任何交易的钱，最好是无限期的，如果真有什么限期，也是足够长的，这是投资中极为关键的一点。"

——《教你炒股票26：市场风险如何回避》

> "如果判断不准确，那卖点卖错了无所谓，这么多股票还怕找不到好的？但买点一定要谨慎，宁愿筹码少了，也不能追高买回来。"

——《教你炒股票26：市场风险如何回避》（2007-01-31 补充原则第 3 条）

> "资金，必须长期无压力。"
>
> "买股票，宁愿不断跌不断买，也绝对不往上加码。"
>
> "永远保持最大的警觉，这是资金管理最大的、最重要的一点，没有这一点，一切管理都是无用的。"

——《教你炒股票31：资金管理的最稳固基础》

缠师本人对机械止损其实有保留，第 26 课读后感里写道"本ID反对斩仓、止蚀之类的玩意"。本框架的做空保护性止损（见 Strategy `stop_loss_short`）是一项工程风控权衡：空头亏损理论无限，单边行情里须防穿仓，与"多头靠卖点离场"的非对称设计配合使用。

## 四、实现思路

### 4.1 BaseTrader：券商"五件套"抽象

`BaseTrader` 是 `abc.ABC`，构造参数 `mode: TradeMode`（`PAPER` 模拟盘 / `LIVE` 实盘）。实现者须提供 5 个方法：

- `buy(symbol, qty=None, notional=None, limit_price=None)`：开多 / 平空（买回）。可给数量或名义金额。
- `sell(symbol, qty=None, percentage=None, limit_price=None)`：平多 / 开空。`percentage` 表"按持仓比例平"。
- `get_positions() → List[Dict]`：持仓查询，约定 `qty` **负数表示空头**，字段还含
  `symbol/avg_entry_price/current_price/unrealized_pnl/unrealized_pnl_pct`。
- `get_account_info() → Dict`：账户资金/购买力。
- `get_price(symbol) → Optional[float]`：最新价（基类默认返回 `None`，子类覆写）。

统一返回结构 `OrderResult(success, order_id, filled_price, filled_qty, error_msg)`。

### 4.2 ChanTradeExecutor：TradeRecord → 券商调用 + 市场规则

桥接器（与具体券商无关），构造参数 `trader / symbol / max_position_value=50000 /
dry_run=True / market_cap=None`。语义映射（对齐回测器的四向）：

- `BUY → trader.buy(qty)`（用 `_buying_power * position_ratio` 折算股数）；
- `SELL → trader.sell(percentage)`（按比例平多）；
- `SHORT → trader.sell(qty)`（开空，产生负持仓）；
- `COVER → trader.buy(qty)`（按空头持仓量买回）。

`market_cap`（`Common.MarketCapability.MarketCapability`，`None` 时不施加额外规则、兼容旧调用）
驱动的三条硬约束：

1. **做空门控**（`_support_short`）：市场不支持做空（如 A 股零售）时，`_exec_short/_exec_cover`
   打印 `[GATE]` 并**直接拒单返回 False**。
2. **T+1**（`_t_plus_0` / `_t1_block` / `_open_date`）：非 T+0 市场用 `_open_date[direction]` 记录
   建仓自然日；`SELL`/`COVER` 若命中"今日建仓当日平"则打印 `[T+1 BLOCK]` 拒单。全平时清除记录。
3. **lot 取整**（`_round_qty`）：`allow_fractional` 或 `lot_size<=1` 时不取整（美股碎股），否则
   `qty // lot_size * lot_size` 向下取整到整手；**不足一手则 `[SKIP]` 拒绝**（对齐 26 课"宁愿筹码少了"）。

仓位基数 `_buying_power`：**优先取账户总权益**（`portfolio_value`/`equity`，对应 31 课动态 sizing），
拿不到再退回固定 `max_position_value`。`_held_qty` 查当前该标的持仓（用于判断是否新建仓、
以及 COVER 的实际空头量）。`dry_run=True` 时只打印 `[DRY-RUN]` 计划、不真正下单（供冒烟/自检）。
`execute(record)` 按 `record.action` 分派，成功后 `_log_result` 打印 `[FILLED]/[FAILED]`。

推荐用法与 `Backtester` 主循环同构：先 `strategy.check_stop_loss` → 可执行才 `executor.execute(stop)` +
`strategy.apply_stop`；再 `strategy.on_bar` → `executor.execute(rec)`，确保执行层与策略层状态一致。

### 4.3 AlpacaTrader（美股）

- 可选依赖 `alpaca-py`，导入失败置 `_ALPACA_AVAILABLE=False`；构造时缺 key/secret 抛 `ValueError`，
  读环境变量 `ALPACA_API_KEY / ALPACA_API_SECRET`。`mode==PAPER` → `TradingClient(paper=True)`，并
  建 `StockHistoricalDataClient`；构造即 `get_account()` 探活，失败抛 `ConnectionError`。
- `buy/sell`：有 `limit_price` 走 `LimitOrderRequest`（`TimeInForce.DAY`），否则 `MarketOrderRequest`
  （buy 支持 `notional` 名义下单）。下单后 `_wait_for_fill` 轮询（默认 timeout=10s、interval=0.5s），
  直到 `filled/partially_filled/cancelled/rejected`。
- **percentage 语义坑**：调用方传 0–1 小数，Alpaca `close_position` 要 1–100 百分数，故内部 `*100` 取整
  （`_exec_sell` 传的是 `percentage`）。
- `_to_result` **严格校验状态**：只有 `filled/partially_filled` 才算 `success=True`，拒单/撤单归为失败——
  防止把未成交订单当成功导致策略/账户状态错配。
- `get_positions/get_account_info` 做了单位转换与异常兜底（失败打印并返回 `[]/{}`）。

### 4.4 FutuTrader（港股 / A 股 / 美股）

- 可选依赖 `futu-api`，并需本地运行 **Futu OpenD** 客户端。读环境变量
  `FUTU_HOST(127.0.0.1) / FUTU_PORT(11111) / FUTU_PWD_MD5 / FUTU_RSA_PATH / FUTU_ENV`；
  `mode==PAPER → TrdEnv.SIMULATE`，`LIVE → REAL`。
- **按市场缓存上下文**：`_CODE_TO_MARKET` 依据 code 前缀（`HK./US./SH./SZ.`）路由 `TrdMarket`；
  `_get_ctx(code)` 懒建 `OpenSecTradeContext`，有 `pwd_md5` 时（可带 RSA 文件）`unlock_trade`。
- `buy/sell`：`place_order`，`limit_price` → `OrderType.NORMAL` 否则 `OrderType.MARKET`，
  `TimeInForce.DAY`。`buy` 若只给 `notional` 则 `qty=int(notional/price)`。
- **无 close_position 语义的坑**：Futu 不支持按百分比平仓，`sell(percentage)` 需**自己查持仓**换算成
  `qty=int(abs(p['qty'])*percentage)`；`get_price` 优先用持仓现价，**无持仓（新开仓）时用
  `get_market_snapshot` 的 `last_price` 兜底**（否则拿不到价会拒单）。
- `get_positions/get_account_info` 遍历所有已建市场上下文聚合；`close()` 统一关闭并清空 `_ctx`，防句柄泄漏。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `__init__.py` | 包声明（`# Trade package`） |
| `Base.py` | `TradeMode`、`OrderResult`、`BaseTrader`（抽象五件套）、`ChanTradeExecutor`（桥接 + 市场规则） |
| `AlpacaTrade.py` | `AlpacaTrader`（美股，alpaca-py） |
| `FutuTrade.py` | `FutuTrader`（港/A/美股，futu-api + OpenD） |

## 六、与其他模块的协作

- **上游**：`Strategy.ChanStrategy` 产出 `TradeRecord`；`Strategy.Backtester` 与本层**共享同一套市场规则语义**
  （做空/ T+1 / lot / 成本），回测与实盘用同一路径保证一致。
- **市场规则来源**：`Common.MarketCapability`（`MarketCapability.support_short/t_plus_0/allow_fractional/lot_size`）
  注入 `ChanTradeExecutor`，是执行层所有门控的数据来源。
- **券商 SDK**：`alpaca-py` / `futu-api` 均为**可选依赖**，缺失时降级为导入守卫或错误返回，
  不影响纯回测（无实盘环境也能跑策略研究）。
- **配置入口**：实盘通常在 `MainChan.py` 经 `--mode live --broker alpaca|futu` 组装
  `Trader + ChanTradeExecutor + CChan.step_load` 的循环（详见 `quick_guide.md`）。
