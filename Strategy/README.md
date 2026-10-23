# Strategy —— 缠论策略 / 回测 / 轮动

## 一、模块定位

`Strategy` 是缠论分析结果的**落地层**：把底层（`KLine/Bi/Seg/ZS/BuySellPoint/Trend`）算出的
三类买卖点与走势状态，翻译成可执行的 `BUY / SELL / SHORT / COVER` 信号，并在多市场约束
（佣金、印花税、T+1、一手 lot）下完成逐 K 线回测、绩效统计与轮动排序。

本包三个核心文件：

- `ChanStrategy.py`：策略引擎 `ChanStrategy`（单级别 + 十层纪律门控）与
  `ChanNestedStrategy`（区间套精确定位），以及 `StrategyConfig`（所有开关/参数）、
  `TradeRecord`（单笔成交）、`BspDecision`（结构点去向，供回测图 veto 标注）。
- `Backtester.py`：多市场回测引擎 `Backtester` + 结果数据类 `BacktestResult`，负责资金/持仓
  记账、交易成本、T+1 校验、量取整、绩效指标、成交/否决标记绘图。
- `Rotation.py`：候选池强弱打分与排序（服务于 106 课"均线轮动/板块强弱指标"理念），
  与单标的缠论结构买卖点正交。

## 二、对应缠论课程

本层是缠论理论到交易动作的转换层，有明确原典对应：

- **第 21 课《缠中说禅买卖点的完备性》**：三类买卖点 100% 安全、买卖点完备性定理、
  区间套精确定位的理论基础（`ChanStrategy` 三类买卖点分派、`ChanNestedStrategy`）。
- **第 73 课《市场获利机会的绝对分类》**：中枢上移与中枢震荡两类获利模式
  （`_handle_bsp3` 趋势追入、`ZSOscillationMonitor` 震荡高抛低吸对应此思路）。
- **第 106 课《均线、轮动与缠中说禅板块强弱指标》**：均线分类强弱、板块轮动
  （`Rotation.py` 打分排序、`StrategyConfig` 的均线强弱门控 `use_ma_filter`）。
- **第 31 课《资金管理的最稳固基础》**：仓位与风险的资金管理原则（分档建仓、
  不逆势加码、防穿仓止损理念的出处）。
- **第 45 课《持股与持币，两种最基本的操作》**："等待被理论绝对保证的买卖点"、
  趋势持有到卖点才离场（`hold_trend_until_perfect`、`_should_exit_long/short`）。

十层纪律各自的详细课号出处见 `Trend/README.md` 与 `RESEARCH.md`；本层负责把这些纪律
以"门控 + 缩放 + 加权"的方式接入买卖点分派流程。

## 三、书中关键原文

### 买卖点完备性与三类买卖点（第 21 课）

> "市场交易，归根结底就是买卖点的把握，买卖点的完备性就是理论的完备性，因此，对这个问题必须进行一个概括性的论述。"
>
> "只有在下跌确立后的中枢下方才可能出现买点。这就是第一类买点。"
>
> "第二类买点是和第一类买点紧密相连的，因为出现第一类买点后，必然只会出现盘整与上涨的走势类型，而第一买点出现后的第二段次级别走势低点就构成第二类买点，根据走势必完美的原则，其后必然有第三段向上的次级别走势出现，因此该买点也是绝对安全的。"
>
> "第三类买点是中枢扩张或新生产生的。中枢扩张导致一个更大级别的中枢，而中枢新生，就形成一个上涨的趋势，这就是第三类买点后必然出现的两种情况。"
>
> "对卖点的分析是一样的，归纳起来，就有缠中说禅买卖点的完备性定理：市场必然产生赢利的买卖点，只有第一、二、三类。"
>
> "相同的分析，可以证明缠中说禅升跌完备性定理：市场中的任何向上与下跌，都必然从三类缠中说禅买卖点中的某一类开始以及结束。"

——《教你炒股票21：缠中说禅买卖点分析的完备性》

### 获利机会的绝对分类（第 73 课）

> "任何市场的获利机会，在本ID理论下，都有一个最明确的分类，用本ID理论的语言来说，只有两种：中枢上移与中枢震荡。"
>
> "在你的操作级别下，中枢上移中，是不存在着任何理论上短差机会的，除非这种上移结束进入新中枢的形成与震荡。而中枢震荡，就是短差的理论天堂。"

——《教你炒股票73：市场获利机会的绝对分类》

### 均线分类与板块轮动（第 106 课）

> "分类的原则是本次反弹目前为止未曾攻克的最小周期均线，因此，8条均线就可以分成9类，最差的一类当然就是完全在所有均线下那种。"
>
> "要判别一板块的强弱很简单，就是把类别数平均一下，越大越强，而这个平均类别数，可以叫缠中说禅板块强弱指标。"
>
> "最强的板块属于领涨板块，该板块的动态就十分关键了……其轮动的次序与节奏就一目了然了，根据这并配合具体股票的走势分析来，轮动操作当然就极为简单了。"

——《教你炒股票106：均线、轮动与缠中说禅板块强弱指标》

### 资金管理与风险（第 31 课）

> "资金，必须长期无压力。"
>
> "不能把自己放置在一个危险的境地，所谓背水一战、置之死地而后生，都不是资本市场应该采取的态度。这样的态度，可能一时成功，但最终必然失败。"
>
> "买股票，宁愿不断跌不断买，也绝对不往上加码。"
>
> "永远保持最大的警觉，这是资金管理最大的、最重要的一点，没有这一点，一切管理都是无用的。"

——《教你炒股票31：资金管理的最稳固基础》

### 持股与持币 = 等待（第 45 课）

> "假设你是按30分钟级别操作的，那么，在一个30分钟的买点买入后，就进入一个持股的操作中……在这个卖点到来之前，你就只在持股这唯一的操作里。当这个30分钟的卖点出现时，卖出，然后就进入持币的操作里，直到一个30分钟的买点出现。持股与持币，归根结底就是一种等待，等待那个被理论绝对保证的买卖点。所有股票的操作，归根结底，只有两个字：等待。"
>
> "一切虽然不可以预测，但一切走势类型的可能结构与类型，却是可以分类的，每一类之间都有着明确的界限，因此，你唯一需要的，就是观察市场当下的走势，让市场去选择可能的结构与类型，然后根据市场的选择来选择。"

——《教你炒股票45：持股与持币，两种最基本的操作。》

## 四、实现思路

### 4.1 核心数据结构

- **`TradeRecord`**：一笔交易记录。字段 `action` 取 `BUY/SELL/SHORT/COVER`；
  `position_ratio` **正=开仓、负=平仓**（回测器据此算股数）；`bsp_type` 记录触发的
  买卖点标签（如 `T1(趋势)`、`T2`、`T3`、`RB(107课)`、`STOP`）；`stop_loss` 为结构化止损价；
  `direction` 区分 `LONG/SHORT/""`。
- **`BspDecision`**：每个**结构买卖点**的最终去向（`TRADE/PENDING/OPEN_*/EXIT_*/SKIP/VETO/HOLD/COOLDOWN`）
  与未成交原因 `reason`、当时是否处于中阴阶段 `middle_yin`。专门供 `Backtester` 在回测图上把
  "被哪一层纪律挡下"标注成橙色 `×原因`。
- **`PositionState`**（枚举）：`EMPTY / LONG_PARTIAL / LONG_FULL / SHORT_PARTIAL / SHORT_FULL`，
  由 `position_state` 属性依据 `long_ratio`/`short_ratio` 派生（阈值 0.001 视为空、0.7 视为重仓）。
- **`StrategyConfig`**：策略总开关表（见 4.4 详解）。

### 4.2 ChanStrategy：三类买卖点 → 四向信号的分派

入口是 `on_bar(chan)`，每根 K 线调用一次，流程为：

1. `self._bar_count += 1`，先 `_refresh_context(chan)` 刷新十层走势分析上下文（见 4.3）。
2. 优先处理 **⑦ 短线反弹持仓** `_manage_rebound_pos`（到目标/止损机械离场，先于买卖点）。
3. 若有 `_pending_signal`（等分型确认的挂单），调 `_try_confirm_pending`；超过 10 根 K 线未确认则丢弃。
4. 从**操作级别**取买卖点列表 `chan[operating_lv].bs_point_lst.lst`（多级别安全：不要求单级别 `get_bsp()`），
   按时间排序，筛出 `klu.idx > _last_bsp_idx` 的新点逐个处理。
5. 每个新点先 `_diagnose_bsp`（只读诊断），再据冷却期与 `_process_bsp` 的结果生成 `BspDecision`，
   若产生 `TradeRecord` 立即返回。

`_process_bsp` 按 `BSP_TYPE` 分派到三个 handler（多空完全对称）：

- **`_handle_bsp1`（一类 / 背驰）**：
  - 盘整背驰 `T1P` 在 `only_trend_bsp1=True` 严格模式下默认被丢弃（除非处于中枢震荡高/低抛区）。
  - 用 `_get_zoushi` 取所属线段的走势状态，非 T1P 的一类买/卖点要求前置走势类型方向匹配
    （买点须 `DOWN_TREND/CONSOLIDATION`，卖点须 `UP_TREND/CONSOLIDATION`），否则放弃。
  - 持空遇买点 → `_should_exit_short` 通过才平空（默认不反手，除非 `flip_long`）；
    空仓遇买点 → 若在急跌反弹窗口走 `_open_rebound_long`，否则按 `position_l1` 开多。对称处理卖点侧。
- **`_handle_bsp2`（二类 / 回调确认）**：持空平空、轻仓加仓（`position_l2`）、空仓直接开仓
  （`position_l1 + position_l2`）。二类"比一类更安全"，空仓即可建较大仓。
- **`_handle_bsp3`（三类 / 中枢突破）**：趋势追入，目标补到满仓
  （`l1+l2+l3-已有`），是第 73 课"中枢上移"顺势模式的主要执行入口。

四个执行原语：`_open_long / _open_short`（受门控 + 缩放，见 4.3）、`_close_long_signal /
_close_short_signal`（平多/平空）、`_execute_flip`（反手：一个信号内先平旧再开新，默认关闭）。
若 `require_fx_confirm=True`，开仓不立即成交，而是写入 `_pending_signal`，等最近 1~3 根合并 K 线
出现对应 `FX_TYPE.BOTTOM/TOP` 分型才在 `_try_confirm_pending` 中以最新价入场（落实"不预测、等确认"）。

### 4.3 十层纪律门控（`_can_short` / `_can_open_long`）

每次开仓前都过一层"级别/走势"纪律，各层独立开关、可追溯 veto 原因（`_veto_short_reason` /
`_veto_open_long_reason` 生成 `BspDecision.reason`）。`_refresh_context` 每根 K 线刷新以下分析器（`Trend` 包提供）：

- **① 多级别联立 + 跨级别背驰归属**（`use_level_linkage`）：`MultiLevelContext.attribute_reversal`
  返回 `ReversalAttribution`；若 `allow_short/allow_open/allow_exit` 为假，则小级别背驰被判定为
  高级别走势中的次级别回调，禁止逆势开仓 / 趋势持有不离场。
- **② 同级别分解**（`use_same_level_decompose`）：`SameLevelDecomposer.decompose` + `holding_signal`
  决定当前同级别走势未完美时是否持有（不被次级别波动洗出）。
- **③ 中阴阶段**（`use_middle_yin`）：`MiddleYinDetector` 命中时对新开仓按 `middle_yin_scale` 降权。
- **④ 均线强弱**（`use_ma_filter`）：`MATrendEvaluator` 多头排列时 `ma_veto_short_in_bull` 禁逆势做空，
  空头排列时 `ma_veto_long_in_bear`（默认关，保留抄背驰底）禁逆势做多。
- **⑤ 小转大**（`use_small_turn_big`）：`SmallTurnBigDetector` 确认时放行早期反转仓并按 `small_turn_big_scale` 缩放。
- **⑥ 中枢震荡**（`use_zs_oscillation`）：`ZSOscillationMonitor` 在高/低抛区放行盘整背驰区间单，按 `zs_osc_scale` 缩放。
- **⑦ 短线反弹**（`use_rebound`）：`ReboundPlanner` 急跌后抢反弹，独立小仓位（`rebound_scale`）+ 目标/止损机械离场，刻意绕过趋势门控。
- **⑧ 两重表里关系**（`use_inside_outside`）：`InsideOutsideAnalyzer` 判 `pullback`（中继，持/禁开）与 `reversal_confirm`（放行）。
- **⑨ 多重赋格**（`use_fugue`）：`FugueDecomposer` 多级别同向齐奏加权 `fugue_boost`，反向共识禁开。
- **⑩ 能量动力**（`use_energy`，默认关）：`EnergyEvaluator` 能量背驰作许可性离场/否决追势；
  因独立贡献为负（RESEARCH 第十二节）默认关闭，`energy_veto_only` 变体只保留否决开仓。

放行时通过 `self._open_scale` 传递仓位缩放，`_scale_middle_yin` / `_fugue_boost_ratio` 逐级调整 `ratio`；
若最终 `ratio <= 0.001` 则不开仓。做空还叠加 `_energy_down_side`（能量背驰落在下跌侧还是上涨侧）判断。

### 4.4 趋势持有与止损（多空非对称）

- `_should_exit_long / _should_exit_short`（对应第 45 课"等待卖点"）：`hold_trend_until_perfect=True` 时，
  只有反转信号获级别背书、且操作级当前走势类型已完美才离场；关闭时退化为旧结构判据
  （中枢新生 `_trend_continuing_on_operating_lv`、`ZoushiState.is_perfect`）。
- **止损非对称**：`stop_loss_long` 默认 `False`（多头最大亏损 100%、卖点终会出现 → 让利润奔跑，靠卖点离场）；
  `stop_loss_short` 默认 `True`（空头亏损理论无限，单边行情防穿仓）。止损位 = 笔低/笔高 ∓ `stop_buffer`
  （`_calc_long_stop` / `_calc_short_stop`）。`check_stop_loss` **只检测不改状态**，由调用方（回测器）
  在确认 T+1 允许后调 `apply_stop` 提交，并触发 `cooldown_bars` 冷却，防连续止损。

### 4.5 ChanNestedStrategy：真·区间套 `_nested_locate`

`ChanNestedStrategy` 包裹 `ChanStrategy`（`base_strategy`），仅重写 `on_bar`：基础策略产出开仓
信号后，若动作是 `BUY/SHORT` 且配置了 `nested_lv` 且联立级别 > 1，调 `_nested_locate` 精确定位：

1. `_get_high_bsp` 取高级别最后一个同向买卖点，其 `bi` 即"父背驰段"；`_bsp_window` 取其时间窗 `[w_lo, w_hi]`。
2. 依次下钻每个次级别 `sub_lv`：在该级别 `bs_point_lst` 里**倒序**找方向一致、且 `klu.time.ts`
   落进当前窗的最后一个背驰 BSP。
3. 命中则用该子 BSP 的 `bi` 时间跨度**收紧窗口**，把 `precise_price/time` 更新为该子点，递归到更低级别——即"层层夹逼"。
4. 最深命中点价格作为成交 `record.price`，级别路径以 `+区间套[K_xxx@日期→...]` 追加到 `bsp_level`。
   若某级别无子背驰则保持上一层结果继续试更低级别；无父背驰段时退化为原价。

其余接口（`trade_history`、`bsp_decisions`、`check_stop_loss`、`apply_stop`、`short_enabled`）均委托给 `base_strategy`。

### 4.6 Backtester：多市场回测引擎

**构造**：`code / begin_time / end_time / data_src / lv_list / chan_config / strategy_config /
initial_capital / market / commission_rate / use_nested / autype`。市场能力优先级：**显式 `market` >
`detect_market(data_src, code)`**；再 `get_market_capability(market)` 取能力表，允许用 `commission_rate` 覆盖。
取价级别 `price_lv`：优先用 `operating_lv`（多级别时信号来自该级别），否则用 `lv_list[0]`。

**run() 主循环**：`CChan(step_load=True)` 逐 K 线 `for snapshot in chan.step_load()`：
1. 从 `snapshot[price_lv]` 取最新 close/date。
2. `strategy.check_stop_loss(price)` → 命中则把 `stop_record.time` 改成真实 bar 日期，经 `_can_close`
   T+1 校验后 `_execute_trade` 执行并 `strategy.apply_stop`；**若被 T+1 阻挡则不调 apply_stop，下一根重检**。
3. `record = strategy.on_bar(snapshot)` → 经 `_can_close` 后 `_execute_trade`。
4. 记录净值 `equity = capital + long_shares*price - short_shares*price`。
循环结束后按最终价对残留多/空仓**强制平仓**，收尾计算指标；`self.chan`、`self.bsp_decisions`
（从策略取回）保存供 `plot()`。

**`_execute_trade`（四向 + 市场规则）**：
- `BUY`：按 `total_value * position_ratio` 折算可买股数（预留费率），`_round_qty` 取整到 lot；
  不足一手则跳过并 `lot_skip_count += 1`（透明告警，非静默）；加权平均更新 `long_entry_price`，
  首次建仓记 `long_entry_date`（T+1 用）。
- `SELL`：`position_ratio>=0.999` 全平，否则按比例取整平多，回填 `trade_pairs`（收益率）与清仓复位。
- `SHORT`：市场 `support_short=False` 时**双保险直接忽略**（策略层已 gate）；成交逻辑对称 BUY。
- `COVER`：对称 SELL，`pnl=(short_entry-price)/short_entry`。

**成本与量**：`_calc_cost` 按市场收取——佣金 `commission_rate`（**A 股最低 5 元**）；印花税仅
**A 股卖出单边**、**港股买卖/开空/回补双边全收**；过户费仅 A 股 `transfer_fee`。`_round_qty` 在
`allow_fractional` 或 `lot_size<=1` 时不取整（美股碎股），否则按 `lot_size` 向下取整（A/港股 100 股一手）。

**指标 `_calc_metrics`**：总收益、年化（`(1+r)^(252/n)-1`）、最大回撤（cummax）、夏普
（`mean/std*√252`）、胜率、盈亏比（均盈/均亏），并分 `BUY/SELL/SHORT/COVER` 计数。
`print_report` 打印市场能力（做空/T+0/lot）、级别、资金、指标、交易明细；有 `lot_skip_count` 时提示调高 `--capital`。

**绘图 `plot`**：配 CJK 字体（`_setup_cjk_font` 在候选字体列表里选第一个可用），`_build_trade_markers`
把成交转成 `{日期:(文字,up/down,颜色)}`（开仓标记附买卖点类型、同日合并），`_build_veto_markers`
把 `SKIP/HOLD/COOLDOWN/VETO` 转成橙色 `×原因`（中阴阶段附 `·中阴`），交给 `Plot.CPlotDriver`
的 `draw_marker`；多级别时只在操作级别开 marker（其余级别日期轴不同，防 `KeyError`，用 `_valid_dates` 过滤）。
另 `_plot_equity` 画资金曲线 + 回撤附图。输出 `{prefix}_trades.png` 与 `{prefix}_equity.png`。

### 4.7 Rotation：候选池强弱排序

- `strength_score(closes, window=60)`：动量 `close[-1]/close[-(w+1)]-1` + `0.5*均线偏离`
  + `5*均线斜率` + `0.1*类夏普`（日收益均值/波动惩罚大起大落）。不足 5 根返回 0。
- `rank_pool`：对 `{symbol: closes}` 逐个打分降序；`select_strongest(top_n, min_score)` 选最强 N 只。
- `fetch_closes(symbol, data_src, ...)`：用 `Chan.GetStockAPI` 直接取某级别收盘价序列（默认日线、
  `AUTYPE.QFQ` 前复权），失败**打印到 stderr 并返回 []**（不静默，便于追溯被剔除标的）。
- 定位：先用轮动排出强弱，再对靠前标的跑缠论策略；与单标的结构买卖点正交（对应 106 课"板块强弱指标/轮动节奏"）。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `__init__.py` | 包声明（`# Strategy package`） |
| `ChanStrategy.py` | `ChanStrategy`、`ChanNestedStrategy`、`StrategyConfig`、`TradeRecord`、`BspDecision`、`PositionState`、`TrendType` |
| `Backtester.py` | `Backtester`（多市场回测引擎）、`BacktestResult`（绩效结果） |
| `Rotation.py` | `strength_score`、`rank_pool`、`select_strongest`、`fetch_closes`（轮动辅助） |

## 六、与其他模块的协作

- **上游结构**：`Chan.CChan`（`step_load` 逐 K 回放、多级别 `chan[lv]`、`bs_point_lst`）、
  `BuySellPoint.BSPoint.CBS_Point`（`is_buy/type/type2str/bi/klu`）、`Common.CEnum`（`BSP_TYPE/FX_TYPE/KL_TYPE`）。
- **纪律分析器**：`Trend` 包（十个分析器 + `MultiLevelContext/ReversalAttribution/holding_signal` 等）
  是 `_refresh_context` 与门控的直接依赖。
- **市场规则**：`Common.MarketCapability`（`detect_market/get_market_capability/MarketCapability`）
  被 `Backtester` 与 `ChanStrategy`（`market_cap.support_short`）共享，决定做空/T+1/印花税/lot。
- **数据**：`Chan.GetStockAPI` → `DataAPI` 各数据源，供 `Rotation.fetch_closes` 与 `CChan` 取 K 线。
- **绘图**：`Plot.CPlotDriver` 供 `Backtester.plot` 画结构 + 买卖点 + 成交/veto 标记。
- **下游执行**：`Trade` 包把同一套 `TradeRecord` 语义落到真实券商下单；`Script` 包用本层策略
  做离线冒烟与十层纪律消融实验。配置默认值可对照 `ChanConfig.py` / `MainChan.py`。
