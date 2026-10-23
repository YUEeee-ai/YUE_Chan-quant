# 快速上手指南

这份指南回答四个问题：**怎么跑起来 → 怎么取缠论元素自己写策略 → 怎么接自己的数据源 → 怎么调试验证**。只讲"怎么做"和"入口在哪"，设计原理见 [README](./README.md)，实验结论见 [RESEARCH.md](./RESEARCH.md)。

- [1. 十分钟跑通（CLI）](#1-十分钟跑通cli)
- [2. 在 Python 里取缠论元素](#2-在-python-里取缠论元素)
- [3. 走势分析层 Trend/（十层纪律）](#3-走势分析层-trend十层纪律)
- [4. 策略与回测（Python API）](#4-策略与回测python-api)
- [5. 接入自定义数据源](#5-接入自定义数据源)
- [6. 调试与自检](#6-调试与自检)

---

## 1. 十分钟跑通（CLI）

安装依赖（最低 python3.11）：

```bash
pip install -r Script/requirements.txt
```

四个模式覆盖全部功能，行情默认走 yfinance（美/港/A 一个库全搞定）：

```bash
# ① 结构诊断: 打印分型/笔/线段/中枢/买卖点 + 十层纪律逐层判定, 不交易
python MainChan.py --mode analyze --symbol AAPL --lv month,week,day --start 2015-01-01

# ② 回测: 自动按代码后缀施加市场规则(A股禁做空+T+1 / 港股印花税 / 美股碎股), 出绩效报告
python MainChan.py --mode backtest --symbol 0700.HK --lv month,week,day --start 2015-01-01 --plot

# ③ 轮动: 候选池按走势强弱排序, 选最强 N 只
python MainChan.py --mode rotate --symbols AAPL,MSFT,NVDA,0700.HK --start 2023-01-01

# ④ 实盘/模拟盘: alpaca(美股) / futu(港A美), --paper 模拟 --dry-run 只打印不下单
python MainChan.py --mode live --symbol AAPL --broker alpaca --paper --dry-run
```

**常用开关速查**（完整列表 `python MainChan.py --help`）：

| 目的 | 参数 |
|------|------|
| A股前复权 | `--autype qfq`（A股回测必加，否则除权缺口会被当成暴跌） |
| 多级别联立（月>周>日） | `--lv month,week,day`（最小级别=操作级别；建议 start 给 8~10 年，让高级别长够中枢） |
| 区间套（操作级下挂次级别精确入场） | `--nested` |
| 关某层纪律做对照 | `--no-level-linkage` / `--no-decompose` / `--no-middle-yin` / `--no-ma` / `--no-small-turn-big` / `--no-zs-oscillation` / `--no-rebound` / `--no-inside-outside` / `--no-fugue` |
| 开启⑩能量动力（默认关） | `--use-energy`，只否决追势不开许可性离场再加 `--energy-veto-only` |
| 仅做多 | `--no-short` |
| 选股/容错 | 高价股开仓被跳过→调高 `--capital`；月线对齐报错→加 `--max-misalign 100` |
| 新票不知道⑩该不该开 | `python Script/EnergyModeAdvisor.py --symbol 代码 --autype qfq` |

---

## 2. 在 Python 里取缠论元素

不想用现成策略、要自己组装逻辑时，所有缠论元素从这里取：

```python
from Chan import CChan
from ChanConfig import CChanConfig
from Common.CEnum import KL_TYPE, DATA_SRC, AUTYPE

chan = CChan(code="AAPL", begin_time="2015-01-01", data_src=DATA_SRC.US_STOCK,
             lv_list=[KL_TYPE.K_MON, KL_TYPE.K_WEEK, KL_TYPE.K_DAY],
             config=CChanConfig({"macd_algo": "composite_full"}),   # 背驰三要素口径(默认即此)
             autype=AUTYPE.NONE)
kl = chan[KL_TYPE.K_DAY]      # = chan.kl_datas[KL_TYPE.K_DAY], CKLine_List, 一切元素的入口
```

`CKLine_List`（即上面的 `kl`）的关键成员：

| 成员 | 类型 | 内容 |
|------|------|------|
| `lst` | `List[CKLine]` | 合并 K 线（缠论计算的基本粒子） |
| `bi_list` | `CBiList` | 笔 |
| `seg_list` | `CSegListComm` | 线段 |
| `zs_list` | `CZSList` | 中枢 |
| `bs_point_lst` | `CBSPointList` | 三类买卖点（策略的主要输入） |
| `segseg_list` / `segzs_list` / `seg_bs_point_lst` | 同构 | 段层级的中枢/买卖点（大部分人不需要） |

**合并 K 线 `CKLine`**：`idx`（序号）、`lst`（内部单根 K 线列表）、`fx`（分型）、`dir`（方向）、`high`/`low`、`pre`/`next`。
单根 K 线 `CKLine_Unit`：`time`/`open`/`high`/`low`/`close`、`klc`（所属合并K线）、`sub_kl_list`（次级别 K 线）、`sup_kl`（父级别 K 线）。

**笔 `CBi`**（`bi_list.lst` 或遍历 `bi_list`）：`idx`、`dir`（方向）、`is_sure`（是否已确认）、`klc_lst`（全部合并K线）、`seg_idx`/`parent_seg`（所属线段）、`pre`/`next`。
常用函数：`_high()`/`_low()`、`get_begin_klu()`/`get_end_klu()`（注意：下降笔的 begin 取的是首个合并 K 线里 high 最大的那根，不是时间最早那根）、`get_begin_val()`/`get_end_val()`（起止价格）。

**线段 `CSeg`**（`seg_list.lst`）：`idx`、`start_bi`/`end_bi`、`is_sure`、`dir`、`bi_list`（段内笔）、`zs_lst`（段内中枢）。函数与 CBi 同名。

**中枢 `CZS`**（`zs_list.lst`）：`low`/`high`（区间）、`peak_high`/`peak_low`（段内极值）、`begin`/`end`（起止K线）、`begin_bi`/`end_bi`（中枢内第一/最后一笔）、`bi_in`（进中枢笔）、`bi_out`（出中枢笔，可能不存在）、`sub_zs_lst`（合并出的子中枢）。

**买卖点 `CBS_Point`**（`bs_point_lst.lst`）：`is_buy`、`type`（`List[BSP_TYPE]`，一个点可同时是 2/3 类）、`bi`（所属笔，买点一定在某笔末尾）、`klu`（所在 K 线）。

> 画图核对是发现"笔/段/中枢/买卖点算错漏算"的最快方式：`--plot` 出的结构图上叠加了成交标记，对照红色 b1/b2/s2 标注即可。

---

## 3. 走势分析层 Trend/（十层纪律）

十层纪律不是黑盒——每层都是一个"输入 `chan[lv]` 中枢序列 → 输出状态对象"的独立分析器，可以单独拿出来用：

| 分析器 | 一句话用途 | 入口调用 |
|--------|-----------|---------|
| `TrendAnalyzer` | 走势类型状态机（盘整/趋势/未完成）+ 终完美 + 中枢演化 | `chan[lv]` 中枢序列 |
| `LevelLinkage.MultiLevelContext` | ① 日→周→月联立，卖点是否被高级别背书 | `.update(chan, bsp_conf)` → `.attribute_reversal(is_buy=False)` |
| `SameLevelDecompose.SameLevelDecomposer` | ② 同级别分解出当前段，决定持有 | `.decompose(chan, lv, bsp_conf)` → `holding_signal(pieces, is_long)` |
| `MiddleYin.MiddleYinDetector` | ③ 中阴阶段识别 | `detect(...)` |
| `MATrend.MATrendEvaluator` | ④ 均线多头/空头排列强弱 | `evaluate(chan, lv)` |
| `SmallTurnBig.SmallTurnBigDetector` | ⑤ 小转大三条件识别 | `detect_buy/detect_sell(chan, large_lv, sub_lv, bsp_conf)` |
| `ZSOscillation.ZSOscillationMonitor` | ⑥ 中枢震荡低吸/高抛区 | `.detect(chan, lv)` |
| `ReboundTrader.ReboundPlanner` | ⑦ 急跌后短线反弹计划（目标/止损） | `.plan(chan, lv)` + `.entry_allowed(plan, bsp)` |
| `InsideOutside.InsideOutsideAnalyzer` | ⑧ 表里关系（里走势×表当前段） | `.analyze(chan, inside_lv, outside_lv, bsp_conf)` |
| `FugueDecompose.FugueDecomposer` | ⑨ 多级别声部齐奏/冲突 | `.decompose(chan, lv_list, bsp_conf)` |
| `EnergyDynamics.EnergyEvaluator` | ⑩ MACD 能量比与背驰 | `.evaluate(chan, lv)` |

最小可用示例（判断"日线这个卖点会不会只是周/月线上涨中的回调"）：

```python
from Trend.LevelLinkage import MultiLevelContext
bsp_conf = chan.conf.bs_point_conf.GetBSConfig(False)
ml = MultiLevelContext([KL_TYPE.K_MON, KL_TYPE.K_WEEK, KL_TYPE.K_DAY], KL_TYPE.K_DAY, 2).update(chan, bsp_conf)
print(ml.attribute_reversal(is_buy=False).reason)   # 高级别上涨未完 → 归属为次级别回调, 别急着卖
```

要加自己的"第⑪层"：照 `MATrend.py` 的范式在 `Trend/` 下写分析器，挂到 `ChanStrategy._refresh_context`，加一个 `use_xxx` 开关——参考现有十层的写法即可。

---

## 4. 策略与回测（Python API）

CLI 内部就是这两件东西，可以直接在 Python 里用：

```python
from Strategy.Backtester import Backtester
from Strategy.ChanStrategy import StrategyConfig
from Common.CEnum import KL_TYPE, DATA_SRC, AUTYPE

bt = Backtester(code="AAPL", begin_time="2022-01-01", end_time="2024-12-31",
                data_src=DATA_SRC.US_STOCK,
                lv_list=[KL_TYPE.K_WEEK, KL_TYPE.K_DAY],
                strategy_config=StrategyConfig(operating_lv=KL_TYPE.K_DAY,
                                               lv_list=[KL_TYPE.K_WEEK, KL_TYPE.K_DAY]),
                autype=AUTYPE.NONE)
result = bt.run()            # BacktestResult: 总收益/回撤/夏普/胜率/逐笔 trade_history
bt.print_report(result)
bt.plot(result)              # 生成 结构+成交标记图 / 资金曲线图
```

**回放原理**（想自己写策略引擎时需要）：`CChanConfig` 打开 `triger_step=True` 后，`CChan.step_load()` 变成生成器——每喂一根 K 线返回一次全级别快照（内部只重算不确定部分），`ChanStrategy.on_bar(snapshot)` 在快照上产信号；`Backtester` 在其上叠加多空四向撮合与市场规则（佣金/印花税/T+1/lot）。

**实盘喂 K 线**：拿到新 K 线后调用 `CChan.trigger_load(inp)`，`inp` 格式 `Dict[KL_TYPE, List[CKLine_Unit]]`；现成入口 `MainChan.py --mode live`。

**写自己的策略**：继承 `ChanStrategy`，重写 `_handle_bsp1/2/3`（每类买卖点怎么处理）、`_can_open_long`/`_can_short`（开仓门控）、`_should_exit_long/short`（离场放行）——十层纪律就是通过这几个钩子接入的，可参考每个方法里的注释。

---

## 5. 接入自定义数据源

参考 `DataAPI/BaoStockAPI.py`，继承 `CCommonStockApi`，实现一个生成器方法即可：

```python
from DataAPI.CommonStockAPI import CCommonStockApi
from KLine.KLineUnit import CKLine_Unit

class CMySource(CCommonStockApi):
    def __init__(self, code, k_type=KL_TYPE.K_DAY, begin_date=None, end_date=None, autype=AUTYPE.QFQ):
        super().__init__(code, k_type, begin_date, end_date, autype)

    def get_kl_data(self):            # 生成器, 逐根 yield CKLine_Unit（返回列表也行, 性能差些）
        ...
        yield CKLine_Unit({
            DATA_FIELD.FIELD_TIME:   CTime(y, m, d, h, mi),   # 必须是 CTime
            DATA_FIELD.FIELD_OPEN:   float(o),                # 以下四项必填
            DATA_FIELD.FIELD_CLOSE:  float(c),
            DATA_FIELD.FIELD_HIGH:   float(h),
            DATA_FIELD.FIELD_LOW:    float(l),
            DATA_FIELD.FIELD_VOLUME: float(v),                # 以下三项可选
            DATA_FIELD.FIELD_TURNOVER:  float(amount),
            DATA_FIELD.FIELD_TURNRATE:  float(turn),
        })
```

- **构造参数**：`code / k_type(KL_TYPE) / begin_date / end_date`（能否为 None、格式自定，由 `CChan` 初始化参数透传）；
- **需要登录/退出的源**（如 baostock 的 login、futu 的 ctx）：额外实现 `@classmethod do_init()` / `do_close()`；
- **注册使用**：把文件放进 `DataAPI/`，`CChan(data_src="custom:文件名.类名", ...)` 即可。美/港/A 不用自建，`--data-src yfinance`（默认）直接可用。

---

## 6. 调试与自检

| 工具 | 命令 | 用途 |
|------|------|------|
| 离线冒烟 | `python Script/SmokeOffline.py` | 合成数据跑通"数据源→缠论→十层纪律→回测→画图"全链路 + 确定性断言，**改完代码先跑它**（不联网） |
| 十层消融 | `python Script/AblationStudy.py --symbols AAPL,MSFT --start 2022-01-01 --end 2024-06-30` | 每标的跑"基线+关某层"11 次回测，量化每层贡献；`--mode only` 测独立贡献；`--energy-veto-only` 测⑩变体；`--offline` 合成数据验证脚本本身 |
| 逐笔归因 | `python Script/DumpTrades.py --symbol 1810.HK --energy veto` | 导出两个配置的逐笔成交，定位差异来自哪一笔（配合 `--layers X --mode off` 的对照结论） |
| ⑩模式决策 | `python Script/EnergyModeAdvisor.py --symbol 代码 --autype qfq` | 新票按波动形态推荐 关/仅否决（RESEARCH 第十六节，11 标的标定） |
| 买入持有基准 | `python Script/BuyAndHold.py` | 算同期买入持有涨幅，检验策略是否跑输裸持有 |

定位"某笔交易为什么发生/被挡"的惯用顺序：

1. 看回测报告逐笔 `reason` 字段——每笔都带触发原因（买卖点类型、是否分型确认、级别归属、小转大/中枢震荡/反弹计划）；
2. 对照 `--plot` 的结构图与成交标记；
3. 用 `--no-xxx` 关掉可疑层重跑，看这笔是否消失；
4. 还解释不了→在 `ChanStrategy` 对应钩子里打断点（`analyze` 模式会打印每层判定值）。
