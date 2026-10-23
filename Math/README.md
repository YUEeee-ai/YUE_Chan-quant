# Math —— 技术指标（MACD / BOLL / Demark / 趋势线 / 趋势模型）

## 一、模块定位

`Math` 是指标计算层，逐 K 线（`CKLine_Unit`）增量维护各类技术度量对象，结果挂回 K 线单元供**背驰力度比较**与**绘图可视化**使用。本文件夹定位需分开看：

- **`MACD.py`** 是缠论原生相关模块——缠师用 MACD 的“红绿柱面积、柱子高度、黄白线回抽零轴”辅助判断背驰（第24/25课）。但要注意分工：`MACD.py` 只负责**计算指标序列**（每根 K 线的 DIF/DEA/柱值快照），真正的“进/出中枢力度比较（背驰判定）”逻辑在 `Common.FuncUtil.is_macd_divergence`、`Bi.cal_macd_metric`、`ZS.CZS.is_divergence` 里实现。
- **`BOLL.py`、`Demark.py`、`TrendLine.py`、`TrendModel.py`** 是**缠论原典之外的通用技术指标**（布林带、TD 序列、趋势回归线、滑窗趋势统计），缠论 108 课中**没有对应原文**。它们在本框架里作为**辅助判据 / 可视化用途**存在，不参与中枢、买卖点的核心推导。

文件：`MACD.py`、`BOLL.py`、`Demark.py`、`TrendLine.py`、`TrendModel.py`，`__init__.py` 为空。

## 二、对应缠论课程

| 课号 | 标题 | 对应实现 |
| --- | --- | --- |
| 24 | MACD对背弛的辅助判断 | MACD 序列计算 + 面积/柱高/黄白线回抽零轴三要素（口径在 FuncUtil 落地） |
| 25 | 吻，MACD、背弛、中枢 | MACD 参数 12/26/9、柱子高度=乖离、黄白线回拉 0 轴形态 |

> BOLL / Demark / TrendLine / TrendModel：**非缠论原生**，无对应课程，仅作通用指标与绘图辅助。

## 三、书中关键原文

> “用MACD判断背驰的前提是，A、B、C段在一个大的趋势里，其中A之前已经有一个中枢，而B是这个大趋势的另一个中枢，这个中枢一般会把MACD的黄白线（也就是DIFF和DEA）回拉到0轴附近。而C段的走势类型完成时对应的MACD柱子面积（向上的看红柱子，向下看绿柱子）比A段对应的面积要小，这时候就构成标准的背弛。”

> “注意，看MACD柱子的面积不需要全出来，一般柱子伸长的力度变慢时，把已经出现的面积乘2，就可以当成是该段的面积。”

> “这种盘整中的类似背驰方法的应用，称为盘整背弛判断。”

——《教你炒股票24：MACD对背弛的辅助判断》

> “MACD的灵敏度，和参数有关，一般都取用12、26、9为参数，这对付一般的走势就可以了……不难发现，MACD的柱子伸长，和乖离有关，大致就是走势和均线的偏离度。”

> “最后，开始继续突破第二个中枢，MACD的黄白线以及柱子都再次重复前面的过程，但这次，黄白线不能创新高，或者柱子的面积或者伸长的高度能不能突破新高，出现背驰，这就结束了这一个两个中枢的上涨过程。”

> “对于000572。现在看日线的MACD意义不大，该看的是30分钟以下级别的，因为背弛首先需要的是回拉0轴的黄白线”

——《教你炒股票25：吻，MACD、背弛、中枢》

## 四、实现思路

### 4.1 `MACD.py`（缠论原生辅助指标）

两个类：

- **`CMACD_item`**：单根 K 线的指标快照，字段 `fast_ema`、`slow_ema`、`DIF`、`DEA`，以及 `macd = 2 * (DIF - DEA)`。乘 2 是**国内软件约定**的红绿柱高度（对应原文“红绿柱子”）；`DIF/DEA` 即“黄白线”。
- **`CMACD`**：在线（增量）MACD 引擎。构造参数默认 `fastperiod=12, slowperiod=26, signalperiod=9`（对应第25课“12、26、9 为参数”）。

`add(value)` 算法：
- 首值播种：`fast_ema=slow_ema=value, DIF=0, DEA=0`（保证冷启动无前视）。
- 之后用**递推式 EMA**：`ema = (2*value + (p-1)*prev_ema) / (p+1)`，等价标准 `ema = value*k + prev*(1-k)`（`k=2/(p+1)`）。
- `DIF = fast_ema - slow_ema`；`DEA = (2*DIF + (signal-1)*prev_DEA)/(signal+1)`；柱值 `macd = 2*(DIF-DEA)`。
- 每次返回最新 `CMACD_item`，由 `KLineUnit.set_metric` 存进 `klu.macd`。

**背驰“力度比较”不在本文件**，而在 `Common.FuncUtil.is_macd_divergence(bi_in, bi_out, macd_algo, divergence_rate, zs=None)`，它把第24课三要素做成可切换口径（`MACD_ALGO`）：

| 口径 | 逻辑 | 对应原文 |
| --- | --- | --- |
| `AREA` / `FULL_AREA` | 红绿柱面积（单侧/双侧）比较 | “柱子面积……比A段小” |
| `PEAK` | 柱子峰值高度 | 第25课“柱子伸长=乖离” |
| `DIF_PEAK` | 黄白线（DIF）极值高度 | 第25课“黄白线创新高” |
| `COMPOSITE` | 面积**或**峰值任一衰竭即背驰（激进） | 第24课综合判断 |
| `COMPOSITE_AND` | 面积**且**峰值都衰竭（最严，过滤假背驰） | 同上 |
| `COMPOSITE_FULL` | 三要素：`_dif_pullback_zero` 黄白线回抽零轴（形态前提）**且** DIF 峰值衰减 **且**（面积萎缩或柱高衰减） | “背弛首先需要的是回拉0轴的黄白线” + 面积/柱高 |
| `SLOPE/AMP/AMOUNT/VOLUMN/...` | 段级/量能口径（段级买卖点默认用 `slope`） | — |

`_dif_pullback_zero(zs, bi_in, bi_out, rel_thred=0.3)` 取中枢内部所有 KLU 的 `|DIF|` 最小值，若 `<= 0.3 * max(进/出波 DIF 幅度)` 即认为“黄白线回抽到了零轴附近”；无 `zs` 或无数据返回 True（盘整背驰不施加该形态门槛）。`divergence_rate > 100` 时直接“保送”返回 True（调试用）。

### 4.2 `BOLL.py`（布林带，通用指标）

- **`BollModel(N=20)`**：滑窗均值/标准差模型，`assert N>1`。`add(value)` 追加并保留最近 `N` 个值，算 `ma = mean(arr)`、`theta = std(arr)`（总体标准差，除以 `len`），返回 `BOLL_Metric`。
- **`BOLL_Metric`**：`MID=ma`、`UP=ma+2*theta`、`DOWN=ma-2*theta`（经典 2σ 布林带）。
- `_truncate(x)`：把 0 替换成 `1e-7`，避免带宽为 0 时下游除零（用于 `theta` 与 `DOWN`）。
- 由 `ChanConfig` 的 `boll_n`（默认 20）实例化，结果挂 `klu.boll`。**用途：绘图/通道辅助，不参与中枢/买卖点核心逻辑。**

### 4.3 `Demark.py`（TD 序列，通用指标）

TD Setup/Countdown 的完整实现，`CDemarkEngine` 暴露可调常量（同时是类级默认）：

- 参数：`DEMARK_LEN=9`（Setup 目标计数）、`SETUP_BIAS=4`（与 4 根前 close 比较）、`COUNTDOWN_BIAS=2`（与 2 根前比较）、`MAX_COUNTDOWN=13`、`TIAOKONG_ST=True`（跳空首根是否跟前一根 close 比）、`SETUP_CMP2CLOSE` / `COUNTDOWN_CMP2CLOSE`（比较基准取 close 还是高/低）。
- `C_KL`：`(idx, close, high, low)`，`v(is_close, dir)` 按比较基准返回 close 或高/低点。
- **`CDemarkSetup`**：维护一段 Setup 序列的 `kl_list`；`update(kl)` 判“当前 close 与 SETUP_BIAS 根前的基准值”是否延续同向条件，满足则 `add_setup()`（idx++），否则 `setup_finished=True`；Setup 计满 9 后开启 `CDemarkCountdown`。`cal_TDST_peak()` 计算 TDST 峰值（含跳空时纳入 pre_kl.close）。
- **`CDemarkCountdown`**：`update(kl)` 与 COUNTDOWN_BIAS 根前比较递增计数，遇 TDST 反向突破或达 `MAX_COUNTDOWN` 则 `finish`。
- `CDemarkEngine.update(idx, close, high, low)`：追加 K 线，据当前 close 相对 `SETUP_BIAS` 根前的方向新建/终止 DOWN/UP 系列，`clean_series_from_setup_finish` 只保留最先完成 9 计数的系列，`clear` 清理无效系列，返回 `CDemarkIndex`。
- `CDemarkIndex`：`setup` / `countdown` 两类索引的容器（`get_setup()/get_countdown()`）。
- **默认关闭**：`cal_demark=False`，仅当配置显式开启才进 `GetMetricModel()`。**用途：反转计数辅助信号，缠论原典无对应。**

### 4.4 `TrendLine.py`（趋势线，通用/可视化）

- `Point(x,y)` + `cal_slope`，`Line(p, slope)` + `cal_dis`（点到直线垂直距离）。
- `CTrendLine(lst)`：`cal` 对 `lst[-1::-2]`（每隔一笔取枢轴点）从最右端点出发，`cal_tl` 贪心找“斜率最极端（UP 取最大、DOWN 取最小斜率）”的枢轴构造直线，逐步剔除已收敛点，取“到所有枢轴点距离和最小”的一条线作为趋势线。
- **用途：画上涨/下跌趋势线，纯可视化辅助，非缠论原生。**

### 4.5 `TrendModel.py`（滑窗趋势统计）

- `CTrendModel(trend_type: TREND_TYPE, T)`：滑动窗口长度 `T`，`add(value)` 保留最近 `T` 个值，按类型返回：`MEAN`（均值）、`MAX`（窗口最大）、`MIN`（窗口最小），未知类型抛 `CChanException(PARA_ERROR)`。
- 配置：`mean_metrics=[...]` 生成若干 `MEAN` 模型，`trend_metrics=[...]` 各生成 `MAX` 与 `MIN` 两个模型；结果存 `klu.trend[type][T]`。**用途：均线/包络类辅助，非缠论原生。**

### 4.6 指标装配与调用链

`ChanConfig.GetMetricModel()` 组装模型列表（顺序）：1 个 `CMACD`（`macd` 配置 `{"fast":12,"slow":26,"signal":9}`）→ `mean_metrics` 对应的 `CTrendModel(MEAN)` → `trend_metrics` 对应的 `CTrendModel(MAX/MIN)` → 1 个 `BollModel(boll_n)` → （`cal_demark` 为真时）`CDemarkEngine`。

`KLineList.metric_model_lst = conf.GetMetricModel()`；每收到一根 `CKLine_Unit`，`set_metric(metric_model_lst)` 按 `isinstance` 分派：MACD → `klu.macd`、CTrendModel → `klu.trend`、BollModel → `klu.boll`、CDemarkEngine → `klu.demark`。至此 `ZS.is_divergence` / `FuncUtil.is_macd_divergence` 才能在笔/段范围内聚合这些逐 KLU 的度量做背驰比较。

## 五、文件清单

| 文件 | 缠论原生 | 内容 |
| --- | --- | --- |
| `MACD.py` | 是（辅助，第24/25课） | `CMACD`/`CMACD_item`：在线增量 MACD，产出每 KLU 的 DIF/DEA/柱值 |
| `BOLL.py` | 否 | `BollModel`/`BOLL_Metric`：2σ 布林带 |
| `Demark.py` | 否 | `CDemarkEngine` 及 Setup/Countdown：TD 序列 |
| `TrendLine.py` | 否 | `CTrendLine`：枢轴点最小距离趋势线 |
| `TrendModel.py` | 否 | `CTrendModel`：滑窗 MEAN/MAX/MIN |
| `__init__.py` | — | 空 |

> 背驰力度比较的算法主体位于 `Common/FuncUtil.py`（`is_macd_divergence`、`_dif_pullback_zero`、`cal_macd_slope`、`cal_macd_amp`），本文件夹只提供逐 K 线的指标序列数据。

## 六、与其他模块的协作

- **`ChanConfig.py`**：`GetMetricModel()` 依据 `macd / mean_metrics / trend_metrics / boll_n / cal_demark / demark` 构建实例；`DEFAULT_ALGO_CONFIG` 把买卖点默认口径设为 `macd_algo="composite_full"`（第24课三要素）。
- **`KLine/KLineUnit.py`**：`set_metric` 把各指标结果挂到 `klu.macd / klu.boll / klu.trend / klu.demark`。
- **`Bi` / `Seg`**：`cal_macd_metric(MACD_ALGO, is_reverse)` 在笔/段区间上聚合 `klu.macd`（面积、峰值、DIF 峰值等），是背驰比较的最小计算单元。
- **`ZS.CZS.is_divergence` → `Common.FuncUtil.is_macd_divergence`**：读取 MACD 聚合值完成趋势/盘整背驰判定。
- **`Plot`**：`BOLL / TrendLine / Demark / TrendModel` 主要供绘图层做通道、趋势线、TD 标记等可视化辅助。
