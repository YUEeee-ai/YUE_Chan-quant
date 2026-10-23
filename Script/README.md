# Script —— 实验 / 自检脚本层

## 一、模块定位

`Script` 是**离线研究 / 质量保障层**：不联网也能验证"数据源 → 缠论计算 → 十层纪律 → 策略 → 回测
→ 绘图"整条链路是否健全，并对 `Strategy` 的**十层纪律**做逐项开关的**消融实验（Ablation Study）**、
逐笔成交导出、买入持有基准、以及 ⑩ 能量层的模式配置推荐。

它是**工程基础设施 + 研究脚本**，服务于把 `Trend` 十层纪律的有效性**量化验证**——每层到底值多少
个百分点，靠这里的脚本对照跑出证据。

## 二、对应缠论课程

**本层无直接原典对应。** 脚本本身不实现任何缠论判据，只是驱动已有的 `Strategy/Trend` 去做实验。
它验证的"十层纪律"（多级别联立、同级别分解、中阴阶段、均线强弱、小转大、中枢震荡、短线反弹、
两重表里、多重赋格、能量动力）各自的缠论课号出处**见 `Trend/README.md` 与根目录 `RESEARCH.md`**；
本层只负责"开关它们、跑回测、对比指标"。

## 三、书中关键原文

**本层无直接原典对应。** 需要引用缠论原文的是各纪律模块本身（`Trend/README`），
脚本层只呈现"某层开/关对收益/回撤/胜率的边际影响"这一实证结果，不涉及原典。

## 四、实现思路

### 4.1 SmokeOffline.py —— 离线冒烟 / 自检

**原理**：定义 `SyntheticAPI(CCommonStockApi)` 合成日线数据源——用 `random.Random(42)` **固定种子**
随机游走叠加"分段趋势"（涨/跌/涨/盘整 4 相循环，每 120 根换相），并在**段末（`i%120>100`）把 drift
×0.3 减速以制造背驰**，保证能长出笔/线段/中枢/买卖点。`patch_source()` 直接把
`Chan.GetStockAPI` 替换成返回 `SyntheticAPI` 的 lambda，从而**完全脱离真实行情**跑通全链路。
脚本 `sys.stdout.reconfigure(encoding="utf-8")` 防 Windows GBK 终端乱码。

按确定性检查串起 7 个测试（`__main__` 顺序执行）：

1. `test_market_routing`：`detect_market` 对 `AAPL/0700.HK/600519.SS/000001.SZ/600519/BTC/USDT`
   路由到 `US/HK/CN/CRYPTO`（含无后缀 6 位数字默认 A 股）——断言相等。
2. `test_attribution_logic`：手工构造 `MultiLevelContext + LevelState` 的 4 个分支——
   A 高级别上涨未完美→禁做空/不离场；B 周线已完美→背书放行；C 高级别下跌未完美→买点禁开仓（不接飞刀）；
   D 单级别退化→全放行。直接断言 `allow_short/allow_exit/allow_open/endorsed_by_higher`。
3. `test_small_turn_big_logic`：用极简桩（`_Bi/_ZS/_KLStub/_BSPStub`）验证第 44 课"小转大"三条件
   （大级别未背驰 + 次级别底背驰 + 结构破坏跌破后收回），并测两个反例（大级别已背驰→非小转大；
   未收回中枢→未确认）。
4. `test_rebound_logic`：验证第 107 课短线反弹——急跌窗口判定、目标位 `最低+(高点-最低)×0.618`、
   止损 `最低×0.98`、入场须在最低点之后；平稳走势→无窗口。
5. `test_trend_modules`：在真实合成 `chan` 上冒烟 4 个模块（级别联立/同级别分解/中阴/均线）。
   （注意：源文件中该函数**重复定义了两次**且内容完全相同，后者覆盖前者，行为一致——无害冗余。）
6. `test_new_modules_on_real_chan`：双级别（日线 + 60 分）合成 chan，冒烟 6 个新模块
   （小转大/中枢震荡/短线反弹/表里关系/多重赋格/能量），断言返回类型正确且有内容。
7. `test_backtest_and_plot`：`StrategyConfig` 默认 `use_energy=False`、`energy_veto_only=False` 校验；
   跑十层全开（⑩默认关）端到端回测，断言 `equity_curve>100`，调 `bt.plot()` 出两张 PNG 并检查文件 >5KB。
   全部通过打印 `SMOKE ALL PASS`。

### 4.2 AblationStudy.py —— 十层纪律逐项开关对照

**核心方法**：对每个标的跑 N+1 次回测，比较指标差异。`LAYERS` 列出十层 `key→StrategyConfig 字段→说明`。
两种模式（`--mode`）：

- `off`（默认）：基线 = **十层全开**，每次**只关一层**，`Δ = 关层 − 全开`（Δ<0 = 该层有正边际贡献，
  即"最后一道门"的价值）。
- `only`：基线 = **十层全关**（仅基础三类买卖点），每次**只开一层**，`Δ = 只开 − 全关`（独立正贡献）。
  文档明确：互为替代的否决门在 `off` 模式下边际必然≈0，只有 `only` 能看出单独一层值多少（见 RESEARCH 第十节）。
- `both`：两种都跑。

`build_config` 据 `off_layer/on_layer/all_layers_off` 逐层设 `kw[field]`；`run_one` 造 `Backtester`
跑一次并汇总成指标 dict（收益/年化/回撤/夏普/胜率/盈亏比/交易数/成本/耗时）。级别解析：
`parse_lv` + `_LV_MAP`；`--nested` 时据 `_SUB_LV_MAP`（操作级别→次级别）下挂一个更细级别，
让级别联立/表里关系/小转大真正生效。输出 `write_csv`（utf-8-sig 便于 Excel）+ `write_md`
（每标的×每层的 Δ 表 + 平均 Δ + 改善标的数 + 两组基线明细表）。

其它参数：`--symbols`（美/港/A/加密按后缀路由）、`--data-src`（yfinance/bao_stock/ccxt）、
`--autype`（A 股建议 qfq）、`--layers`（只跑部分层）、`--capital`、`--div-rate`、`--no-short`、
`--no-fx-confirm`、`--offline`（复用 `SmokeOffline.SyntheticAPI` 自检）。
`--max-misalign` 放宽父子级别 K 线对齐容忍：yfinance 部分市场（如 A 股月线按月末标注）会产生
零子 K 线月份，设较大值可跳过这些已知坏月份。`--energy-veto-only` 是 ⑩ 变体开关。
**坑**：每个 `(标的×配置)` 都独立重建缠论结构，多级别 + 长区间会很慢。

### 4.3 DumpTrades.py —— 逐笔成交导出（层间归因）

复用 `AblationStudy.build_config`，针对**单一 ⑩ 能量模式**（`--energy off/on/veto`）跑一次回测，
逐笔打印 `time / action / price / bsp_type / reason`，并显示总收益与笔数。用途：当消融表里某层
Δ 异常时，把成交明细导出来**人工归因**（哪笔被该层挡下/放行）。`--lv` 默认 `month,week,day`、
`--capital` 默认 300000、可透传 `--max-misalign`。

### 4.4 BuyAndHold.py —— 买入持有基准

最小脚本：对固定标的池（茅台/平安/招行、港股 9988/1810/0700/9618、SPY/QQQ/TSLA），
用 yfinance 取 2015-01 至今日线（A 股 `auto_adjust=True` 近似复权），打印首日/末日价格与**买入持有涨幅**。
作为策略回测的**对照基准**——缠论策略的收益须显著跑赢它才有意义。

### 4.5 EnergyModeAdvisor.py —— ⑩ 能量层模式配置助手

依据 RESEARCH 第十五节 11 标的实证，按标的**波动形态分型**推荐 ⑩ 用「关 / 仅否决 / 全开」：

- `calc_features`：从日线算 `ann_vol`（对数收益 std×√252）、`max_dd`（cummax 最大回撤）、
  `recovery`（自底部反弹幅度）、`total`（总涨幅）。
- `recommend`：阈值下三类完全可分（回判 11/11 与实证最优一致）——
  **深熊反转型**（`max_dd≤-65% & recovery≥60% & ann_vol≥32%`，如 TSLA/小米/阿里/腾讯）→ 推荐「仅否决」
  （保留顶部否决、放弃许可性提前离场；波动 ≥40% 时提示"全开在单边深熊底部有对冲价值"可作备选）；
  **稳定长牛型**（`total≥150% & ann_vol≤32%`，如 QQQ/SPY/茅台）→ 推荐「关」（全开曾让茅台 -695pp，
  若坚持须配 `--energy-veto-only`）；**其余**→ 默认「关」。
- `main`：打印特征表 + 每个标的的推荐、形态、依据，并直接给出对应的
  `python main_chan.py --mode backtest ...` 可复制命令。

### 4.6 requirements.txt

脚本运行依赖：`baostock / ipython / matplotlib / numpy / pandas / requests / yfinance / alpaca-py`
（离线冒烟只需 matplotlib/numpy；联网取数用到 yfinance/baostock；实盘相关才需 alpaca-py）。

## 五、文件清单

| 文件 | 用途 |
|------|------|
| `SmokeOffline.py` | 合成数据离线冒烟：市场路由 / 归属逻辑 / 小转大 / 反弹 / 十层真实 chan / 端到端回测+出图 |
| `AblationStudy.py` | 十层纪律逐项开关对照（off/only/both），输出 CSV 明细 + Markdown 汇总 |
| `DumpTrades.py` | 指定 ⑩ 模式下逐笔成交导出，供层间差异人工归因 |
| `BuyAndHold.py` | 各标的买入持有基准涨幅（策略对照组） |
| `EnergyModeAdvisor.py` | 按波动形态分型推荐 ⑩ 能量层的关/仅否决/全开配置 |
| `requirements.txt` | 脚本依赖清单 |

## 六、与其他模块的协作

- **驱动对象**：`Strategy.ChanStrategy.StrategyConfig`（十层开关）、`Strategy.Backtester`（跑回测/出图）、
  `Trend` 十模块（被冒烟与消融的实际分析器）。
- **数据来源**：`DataAPI`（真实 yfinance/baostock/ccxt）；`--offline` 复用 `SmokeOffline.SyntheticAPI`。
- **市场路由**：`Common.MarketCapability.detect_market`（冒烟断言其正确性）。
- **结论沉淀**：实验结果对应 `RESEARCH.md`（第十/十二/十五节等）与 `Trend/README.md` 的理论/实证叙述；
  `DumpTrades/AblationStudy` 产出的 CSV/MD 与 `SmokeOffline` 的 PNG 落在 `results/` 等工作目录。
- **典型顺序**：改纪律 → `SmokeOffline` 全绿 → `AblationStudy --mode both` 看每层贡献 →
  异常标的用 `DumpTrades` 归因 → `EnergyModeAdvisor` 给该标的推荐落地模式。
