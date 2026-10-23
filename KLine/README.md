# KLine —— K线对象、合并K线与单级别计算流水线

## 一、模块定位

`KLine` 是**形态学的存储与索引层**，把最原始的一根根行情数据封装成对象、组织成链表/列表，并挂载各类技术指标。它是 `Combiner`（合并算法）的**宿主**，也是笔、线段、中枢、买卖点所在计算流水线的**总入口**。三个核心对象层层递进：

- `CKLine_Unit`（K 线单元）：一根**原始** K 线。持有 `time/open/high/low/close`、成交信息 `CTradeInfo`、以及挂载在其上的指标对象（`macd`/`boll`/`trend`/`demark`）。它还持有跨级别关系（`sub_kl_list` 次级别子 K 线、`sup_kl` 父级别 K 线）与指向所属合并 K 线的 `__klc`。
- `CKLine`（合并 K 线）：**继承** `Combiner.CKLine_Combiner[CKLine_Unit]`，在合并包络之上加了序号 `idx`、级别 `kl_type`，并实现了分型有效性校验 `check_fx_valid`。一根 `CKLine` 内部聚合 1~N 根 `CKLine_Unit`（`self.lst`）。
- `CKLine_List`（K 线列表）：**单个级别的中枢调度器**。持有并串联该级别的全部计算结果——合并 K 线列表、笔、线段、线段之线段、笔中枢、段中枢、买卖点。`Chan.py` 对每个级别建一个 `CKLine_List`。

- 辅助：`CTradeInfo` 把成交量/成交额/换手率封装进 K 线单元。
- 关键枚举：`KL_TYPE`（周期）、`FX_TYPE`、`FX_CHECK_METHOD{STRICT,LOSS,HALF}`、`DATA_FIELD`、`TREND_TYPE`。

## 二、对应缠论课程

- **第 62 课《分型、笔与线段》**：K 线是"只看高低点、不分阴阳"的几何对象，是分型/笔的数据载体。
- **第 65 课《再说说分型、笔、线段》**：分型/笔/线段答案的"唯一性、当下性"——只有"K 线已经走出来"才能确定结构，这正是 `CKLine_List` 增量喂入流水线的理论依据。
- **第 24 课《MACD对背弛的辅助判断》**：MACD 红绿柱面积、黄白线（DIF/DEA）与 0 轴回拉——本模块把 `CMACD`/`BollModel` 等指标挂到每根 K 线单元上，为上层背驰力度度量供数。

## 三、书中关键原文

> 下面的定义与图，都适合任何周期的K线图。先看图中的第1、2，图中的小线段代表的是K线，这里不分阳线阴线，只看K线高低点。
>
> ——《教你炒股票62：分型、笔与线段》

> 上面包含关系的定义已经十分清楚，就是一些最精确的几何定义，只要按照定义来，没有任何图是不可以精确无误地、按统一的标准去找出所有的分型来。注意，这种定义是唯一的，有统一答案的……这答案与时间无关，与人无关，是客观的，不可更改的，唯一的要求就是被分析的K线已经走出来。
>
> ——《教你炒股票65：再说说分型、笔、线段》

> C段的走势类型完成时对应的MACD柱子面积（向上的看红柱子，向下看绿柱子）比A段对应的面积要小，这时候就构成标准的背弛。
>
> ——《教你炒股票24：MACD对背弛的辅助判断》

> MACD上有黄白线，也有红绿柱子，红绿柱子交界的那条直线就是0轴。
>
> ——《教你炒股票24：MACD对背弛的辅助判断》

> 这个中枢一般会把MACD的黄白线（也就是DIFF和DEA）回拉到0轴附近。
>
> ——《教你炒股票24：MACD对背弛的辅助判断》

## 四、实现思路

### 4.1 `CKLine_Unit`（KLineUnit.py）—— 单根原始 K 线

**构造与合法性校验**：`__init__(kl_dict, autofix=False)` 从字典按 `DATA_FIELD.*` 取出 `time/close/open/high/low`，随后调用 `check(autofix)`：
- 若 `low` 不是 `{low, open, high, close}` 的最小值：`autofix=True` 时把它修正成最小值，否则抛 `ErrCode.KL_DATA_INVALID`；`high` 同理取最大值方向校验。
- 默认 `kl_data_check`（`ChanConfig`）为 `True`，即脏数据直接报错而非静默修正。
- 末尾 `set_idx(-1)`：索引在入列时由 `CKLine_List` 回填。

**关系指针**（支撑多级别递归）：
- `sub_kl_list`（次级别 K 线列表）+ `add_children/get_children`；
- `sup_kl`（指向父级别 K 线）+ `set_parent/get_parent_klc`；
- `__klc`（指向所属合并 K 线）+ `set_klc/klc`（读取时 `assert` 非空）。
这三者让"1 分钟 K 线 ↔ 5 分钟 K 线"能相互回溯，`CKLine.GetSubKLC()` 就靠它取子级别合并 K 线。

**指标挂载容器** `set_metric(metric_model_lst)`：对每个指标模型 `isinstance` 分派：
- `CMACD` → `self.macd = metric_model.add(self.close)`（返回 `CMACD_item`，含 `macd` 柱值与 `DIF`）；
- `CTrendModel` → 写入 `self.trend[type][T]`（均线/区间极值，按类型与周期分桶）；
- `BollModel` → `self.boll = ...`；
- `CDemarkEngine` → `self.demark = metric_model.update(...)`。
指标模型列表由 `CChanConfig.GetMetricModel()` 生成（默认含 MACD(12,26,9) 与 BOLL(20)，Demark 需 `cal_demark=True` 才挂）。

`_low()/_high()` 是供 `CCombine_Item` 读取的统一接口名（与 `CBi/CSeg` 同名，便于泛型合并）。`limit_flag`（-1 跌停 / 1 涨停）用于后续涨跌停一字线处理。

### 4.2 `CTradeInfo`（TradeInfo.py）—— 成交信息容器

遍历 `TRADE_INFO_LST = [volume, turnover, turnover_rate]`，用 `info.get(name)` 存入 `self.metric` 字典（缺失为 `None`）。`CBi.Cal_MACD_trade_metric` 会读取 `klu.trade_info.metric[metric]` 累加成交量/额，若遇 `None` 直接返回 0.0（即缺数据不报错、退化为无量度）。

### 4.3 `CKLine`（KLine.py）—— 合并 K 线

继承 `CKLine_Combiner[CKLine_Unit]`，新增：
- `idx`：合并 K 线在列表中的序号，`time_begin/time_end` 在笔/线段的特征序列里就是靠这个 `idx` 排先后。
- `__str__`：`3th^:...` 形式，`^` 顶分型、`_` 底分型、无符号普通。
- `GetSubKLC()`：遍历内部每根子 K 线的次级别 K 线，用 `last_klc` 去重（相邻两个 `CKLine` 的子 K 线**可能重叠**，因为子 K 线合并时可能跨过父 K 线的结束边界——代码注释明确记录了这一坑）。
- `get_klu_max_high()/get_klu_min_low()`：取本合并 K 线内部**原始**高低点的极值（注意：与包络 `high/low` 可能不同，因为合并可能收缩过）。
- `has_gap_with_next()`：用 `Common.FuncUtil.has_overlap` 判断本 K 线与下一根是否价格重叠；返回 `True` 表示**存在缺口**（相等也算重叠=无缺口）。服务于笔跨度 `gap_as_kl` 与线段缺口判定。

**`check_fx_valid(item2, method, for_virtual)` —— 分型/笔端点有效性核心**：
判断"我"（顶或底分型 K 线）与对面 `item2` 是否构成一笔两端所需的极值关系。三种口径（`FX_CHECK_METHOD`）：
- `LOSS`：只比较顶/底分型那根 K 线自身（最宽松）；
- `HALF`：比较分型及其前一根（`item2.pre`）与"我"及其后一根（`self.next`）的极值（中等）；
- `STRICT`：比较分型三根 K 线（`pre/self/next`）的极值（最严格，默认口径）。
顶分型成立条件：`self.high > item2_high and item2.low < self_low`（顶要高于对面的高点、对面底要低于本底的低点）；底分型反向。`for_virtual=True`（虚笔）时不要求 `item2.next` 存在，只用 `item2.pre` 与 `item2`，避免尾部未走完时越界。方法参数非法时抛 `ErrCode.CONFIG_ERROR`。该 `method` 来自 `bi_fx_check` 配置。

### 4.4 `CKLine_List`（KLineList.py）—— 单级别计算总调度器

**持有结构**（一个级别的全部产物）：`lst`（合并 K 线）、`bi_list`（`CBiList`）、`seg_list`（笔线段）与 `segseg_list`（线段之线段，级别递归）、`zs_list`（笔中枢）与 `segzs_list`（段中枢）、`bs_point_lst` 与 `seg_bs_point_lst`（笔级/段级买卖点）、`metric_model_lst`（指标模型）。`seg_list/segseg_list` 通过 `get_seglist_instance` 构造线段算法实例（目前仅 `chan` 特征序列算法；`seg_algo` 合法性在 `CSegConfig` 校验）。

**增量流水线 `add_single_klu(klu)`**（对应第 65 课"当下性"，逐根喂入）：
1. `klu.set_metric(...)` 挂指标；
2. 首根 → 建 `CKLine(idx=0)`；
3. 否则 `self.lst[-1].try_add(klu)`：
   - 返回非 `COMBINE`（不合并）→ 用 `_dir` 新建 `CKLine`；凑够 ≥3 根时对**倒数第二根** `lst[-2].update_fx(lst[-3], lst[-1])` 定分型；再调 `bi_list.update_bi(...)` 增量更新笔（`step_calculation` 模式下若笔有变动触发 `cal_seg_and_zs`）；
   - 返回 `COMBINE`（合并了）→ `step_calculation` 模式下尝试 `try_add_virtual_bi`（注释指向 issue#175：合并末根也要重估虚笔）。

**全量重算 `cal_seg_and_zs()`**（非逐根模式收尾时调用）：
`bi_list.try_add_virtual_bi`（补尾部虚笔）→ `cal_seg`（笔→线段）→ `zs_list.cal_bi_zs`（笔中枢）→ `update_zs_in_seg`（线段内挂中枢、回填 `bi_in/bi_out`）→ **再上一层** `cal_seg(seg_list, segseg_list)` + `segzs_list.cal_bi_zs`（线段之线段 + 段中枢，即级别递归）→ `update_klc_in_bi`（回填每笔的 `klc_lst`）→ 最后先算**段级**买卖点、再算**笔级**买卖点。顺序上"先高一级别后低一级别"。

**辅助函数**：
- `cal_seg`：`seg_list.update(bi_list)` 后，把每笔的 `seg_idx` 用字典映射回填（找不到的归最后一个线段，通常是尾部虚线段）。
- `update_zs_in_seg`：给每线段挂其内部中枢 `add_zs`；对每个中枢 `set_bi_in`（前一笔）、`set_bi_out`（后一笔，越界则不设）、`set_bi_lst`。含断言 `zs.begin_bi.idx > 0`。
- `update_klc_in_bi`：`bi.set_klc_lst(self[begin_klc.idx : end_klc.idx+1])`，供 MACD 面积/极值在笔内遍历。

### 4.5 关键参数与默认值（来自 `ChanConfig.py`）

- `kl_data_check=True`：原始数据合法性校验；`autofix` 决定是否静默修正。
- `macd={fast:12, slow:26, signal:9}`、`boll_n=20`：指标参数，经 `GetMetricModel()` 生成挂到每根 K 线单元。
- `triger_step=False`：为 `True` 时走 `step_calculation` 逐 K 线回放（`add_single_klu` 内部即时重算），为 `False` 时批量喂完后统一 `cal_seg_and_zs`。
- `seg_algo="chan"`、`bi_fx_check="strict"`（默认，KLine 层的 `check_fx_valid` 口径）。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `KLineUnit.py` | `CKLine_Unit`：单根原始 K 线，数据/关系/指标挂载容器 |
| `KLine.py` | `CKLine`：合并 K 线（继承 `CKLine_Combiner`）+ 分型有效性校验 `check_fx_valid` + 缺口 `has_gap_with_next` + 子级别 K 线 `GetSubKLC` |
| `KLineList.py` | `CKLine_List`：单级别计算总调度器（增量 `add_single_klu` / 全量 `cal_seg_and_zs`）+ `get_seglist_instance` 工厂 |
| `TradeInfo.py` | `CTradeInfo`：成交量/额/换手率容器 |
| `__init__.py` | 空文件（包标记） |

## 六、与其他模块的协作

- **被 `Chan.py` 调用**：`CChan` 为每个级别实例化一个 `CKLine_List`，`load/load_iterator/step_load` 逐根把数据源 K 线转成 `CKLine_Unit` 喂入。
- **依赖 `Combiner`**：`CKLine` 直接继承 `CKLine_Combiner` 完成合并与分型。
- **产出供给上层**：`add_single_klu`/`cal_seg_and_zs` 生成 `bi_list`（`Bi`）、`seg_list/segseg_list`（`Seg`）、`zs_list/segzs_list`（`ZS`）、`bs_point_lst`（`BuySellPoint`）。
- **依赖 `Math`**：MACD/BOLL/TrendModel/Demark 指标模型经 `set_metric` 挂到 `CKLine_Unit`，其数值被 `CBi/CSeg` 的背驰度量读取。
- 本模块是"数据 → 形态 → 走势"的转换枢纽：上承原始行情，下启笔线段中枢买卖点。
