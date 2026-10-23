# Common —— 通用工具 / 基础层

## 一、模块定位

`Common` 是全仓库的**地基**：被几乎所有其他包 import，提供枚举常量、时间对象、异常体系、
方法级缓存、通用数学/工具函数、背驰判定核心，以及跨市场交易能力描述与路由。它本身不做缠论
结构计算，但**决定了"用什么口径判背驰"和"哪个市场有哪些交易限制"这两件全局事实**。

文件一览：`CEnum.py`（枚举）、`CTime.py`（时间）、`ChanException.py`（异常/错误码）、
`Cache.py`（缓存装饰器）、`FuncUtil.py`（工具函数 + 背驰判定）、`MarketCapability.py`（市场能力路由）。

## 二、对应缠论课程

- **第 24 课《MACD 对背驰的辅助判断》**：`FuncUtil.is_macd_divergence` 是**背驰判据的核心实现**
  （红绿柱面积、柱高、黄白线回抽零轴的综合），有明确原典对应。
- 其余（`CEnum`/`CTime`/`ChanException`/`Cache`/`MarketCapability`）为**工程基础设施**，
  **无直接原典对应**，服务于全链路的类型安全、时间对齐、错误处理、性能与多市场规则统一。

## 三、书中关键原文

### 背驰的 MACD 辅助判断（第 24 课）

> "用MACD判断背驰，首先要有两段同向的趋势。同向趋势之间一定有一个盘整或反向趋势连接，把这三段分别称为A、B、C段。"
>
> "用MACD判断背驰的前提是，A、B、C段在一个大的趋势里，其中A之前已经有一个中枢，而B是这个大趋势的另一个中枢，这个中枢一般会把MACD的黄白线（也就是DIFF和DEA）回拉到0轴附近。而C段的走势类型完成时对应的MACD柱子面积（向上的看红柱子，向下看绿柱子）比A段对应的面积要小，这时候就构成标准的背弛。"
>
> "缠中说禅背驰-买卖点定理：任一背驰都必然制造某级别的买卖点，任一级别的买卖点都必然源自某级别走势的背驰。"
>
> "光用MACD辅助判断，即使你对中枢不大清楚，只要能分清楚A、B、C三段，其准确率也应该在90%以上。而配合上中枢，那是100%绝对的。"

——《教你炒股票24：MACD对背弛的辅助判断》

（实现说明：第 24 课原文强调的是"**C 段柱面积 < A 段柱面积** + **B 段中枢把黄白线回拉到 0 轴附近**"。
`FuncUtil` 在此之上补充了"柱高/峰值 `PEAK`""DIF 峰值 `DIF_PEAK`"等口径作为力度度量的工程扩展，
组合成 `COMPOSITE/COMPOSITE_AND/COMPOSITE_FULL`；这些扩展是**实现层的选择**，不应说成缠师原话，
但其形态前提（黄白线回抽零轴）与面积比较确为 24 课本意。）

## 四、实现思路

### 4.1 CEnum.py —— 全局枚举字典

集中定义所有类型安全枚举，避免魔法字符串散落各处：

- `DATA_SRC`：`BAO_STOCK / CCXT / US_STOCK`（数据源工厂键，见 `Chan.GetStockAPI`）。
- `KL_TYPE`：`K_1M/K_3M/K_5M/K_15M/K_30M/K_60M/K_DAY/K_WEEK/K_MON/K_QUARTER/K_YEAR`（级别，
  与 `FuncUtil.check_kltype_order` 的排序表配套）。
- `KLINE_DIR`（`UP/DOWN/COMBINE/INCLUDED`）、`FX_TYPE`（`TOP/BOTTOM/UNKNOWN` 分型）、
  `BI_DIR`（`UP/DOWN`）、`BI_TYPE`（严格/次高低点成笔等多种笔口径）。
- `BSP_TYPE`：买卖点类型 `'1'/'1p'/'2'/'2s'/'3a'/'3b'`，`main_type()` 取首字符归为 `'1'/'2'/'3'`；
  `T3A` = 中枢在 1 类后、`T3B` = 中枢在 1 类前。`Strategy._process_bsp` 就是按这些枚举分派。
- `AUTYPE`：`QFQ/HFQ/NONE` 复权类型（供 DataAPI）。
- `MACD_ALGO`：背驰力度口径全集——`AREA/PEAK/FULL_AREA/DIFF/SLOPE/AMP/VOLUMN/AMOUNT/…`，
  以及**复合口径** `COMPOSITE`（面积 OR 峰值）、`COMPOSITE_AND`（面积 AND 峰值）、`DIF_PEAK`（黄白线极值）、
  `COMPOSITE_FULL`（24 课三要素）——直接对应 4.5 的 `is_macd_divergence`。
- `DATA_FIELD`：行情字段内部键名（`FIELD_TIME/OPEN/…/VOLUME/TURNOVER/TURNRATE`），
  `TRADE_INFO_LST` 列出成交三件套。供 DataAPI 字段映射。

### 4.2 CTime.py —— 时间对象

`CTime(year, month, day, hour, minute, second=0, auto=True)`：

- `auto` 是"对天的自适应理解"：日线等无时分（`hour==0 and minute==0`）时，`set_timestamp`
  把时间戳记到**当天 23:59**，使"日 K 线"的 `ts` 落在该日末尾，保证与分钟级比较时日线不被误判为
  早于同日分钟线（区间套/多级别对齐都靠 `ts` 比较）。
- `to_str()/__str__`：无时分输出 `YYYY/MM/DD`，有则 `YYYY/MM/DD HH:MM`；`toDateStr/toDate` 供日期转换。
- 实现 `__gt__/__ge__` 基于 `ts` 比较。注意只实现了大于类比较，排序处多用显式 `.ts`。

### 4.3 ChanException.py —— 统一异常与错误码

`ErrCode(IntEnum)` 按号段分区：chan 错误 `0~99`（含 `SRC_DATA_TYPE_ERR/PLOT_ERR/CONFIG_ERROR/SEG_*` 等）、
Trade 错误 `100~199`（下单/记录/额度等）、KL 数据错误 `200~299`（`PRICE_BELOW_ZERO/KL_DATA_NOT_ALIGN/
SUSPENSION/NO_DATA` 等）。`CChanException(message, code)` 携带 `errcode/msg`，并提供
`is_kldata_err()/is_chan_err()` 按号段判定归类，便于上层（如 `MainChan`/脚本）区分"数据问题 vs 逻辑问题"。
文件末尾 `__main__` 演示不同 Python 版本下 `str(errcode)` 表现差异（3.8 枚举名 / 3.11 数字）。

### 4.4 Cache.py —— 方法级 memoize

`make_cache` 是**描述符式**缓存装饰器（`@make_cache`），约束严格：只能装饰**仅一个 `self` 参数**的方法
（`inspect.getfullargspec` 校验，否则抛异常）。`__get__` 返回绑定的 `MethodType`，首次调用把结果写进
实例上的 `_memoize_cache`（以 `str(func)` 为 key），之后直接命中缓存。用于把"无参纯计算"（如某对象的
派生量）在生命周期内只算一次。坑：缓存挂在实例上，实例被复用即复用缓存；无失效 API。

### 4.5 FuncUtil.py —— 工具函数与背驰核心

**通用工具**：
- `kltype_lt_day / kltype_lte_day`：级别是否小于/不大于日线（决定有无分钟数据、时间戳是否 `auto`）。
- `check_kltype_order(type_list)`：断言 `lv_list` 从大到小（`cur_lv < last_lv`）。
- `revert_bi_dir`：翻转笔方向；`has_overlap(l1,h1,l2,h2,equal)`：区间是否重叠（中枢重叠判定基础，
  `equal` 控制边界相等是否算重叠）。`str2float`：解析失败返回 `0.0`（数据源容错）。
- `cal_macd_slope / cal_macd_amp`：笔/线段的价格斜率（按持续 K 线数归一）与振幅，**Bi 与 Seg 共用同一口径**，
  作为 `SLOPE/AMP` 类背驰力度的度量。

**`_dif_pullback_zero(zs, bi_in, bi_out, rel_thred=0.3)` —— 黄白线回抽零轴检测（24 课形态前提）**：
遍历中枢 `zs.bi_lst` 内所有 KLU 的 `macd.DIF` 取 `|DIF|` 最小值，若 `min_abs_dif <= rel_thred × max(进/出波 DIF 峰值)`
即认为"黄白线回抽到了 0 轴附近"。无 `zs`、无数据或异常一律返回 `True`（不额外约束，兼容盘整背驰）。
这正是 24 课"中枢一般会把黄白线回拉到 0 轴附近"的实现。

**`is_macd_divergence(bi_in, bi_out, macd_algo, divergence_rate, zs=None)` —— 背驰统一入口**：
返回 `(是否背驰, out/in 比值)`。`divergence_rate>100` 为**保送**（强制背驰，仅供调试）。按口径分支：

- **单一口径**（`AREA/PEAK/DIF_PEAK/SLOPE/AMP/…`）：`out_metric <= divergence_rate * in_metric` 即背驰
  （进中枢用 `is_reverse=False`、出中枢 `is_reverse=True` 取对应侧的 MACD 度量）。
- **`COMPOSITE`（OR）**：`面积衰竭 or 峰值衰竭`——激进、抓底多。
- **`COMPOSITE_AND`**：`面积衰竭 and 峰值衰竭`——严格、过滤假背驰。
- **`COMPOSITE_FULL`（24 课完整三要素）**：
  `zero_ok（黄白线回抽零轴，形态前提）` **且** `dif_div（DIF 峰值衰减）` **且**
  `（area_div 面积萎缩 or peak_div 柱高衰减）`（力度确认）。最贴合原著"综合判断"，也是当前
  回测/实验默认口径（`macd_algo="composite_full"`，`divergence_rate=0.9`）。

参数默认：`divergence_rate=0.9`（Strategy/回测沿用），`zs` 仅 `COMPOSITE_FULL` 用（None 则跳过形态门槛）。

### 4.6 MarketCapability.py —— 跨市场能力与路由

`MARKET` 枚举 `CN/HK/US/CRYPTO`。`MarketCapability` dataclass 描述某市场全部交易规则：
`support_short / t_plus_0 / stamp_tax / commission_rate / transfer_fee / lot_size / allow_fractional /
price_limit_rate / currency`，并含 `market` 枚举字段（费率分支据此判定，**不依赖中文 name**）。

`DEFAULT_CAPABILITIES`（2024 规则，需随规更新）：
- **A 股**：`support_short=False`（融券需专门账户，默认关）、`t_plus_0=False`（T+1）、
  印花税 `0.0005`（2023.08 从 0.1% 减半单边）、佣金 `0.00025`、过户费 `0.00001`、`lot_size=100`、
  不允许碎股、涨跌停 `±10%`。
- **港股**：可做空、T+0、印花税 `0.001` 双边、佣金 `0.0003`、交收费 `0.00002`、`lot_size=100`（实际视个股）、
  无涨跌停。
- **美股**：可做空、T+0、无印花税、佣金 `0.0005`（含 SEC/FINRA）、`lot_size=1`、**允许碎股**。
- **加密货币**：可做空、T+0、佣金 `0.001`、`lot_size=1`、允许碎股、无涨跌停。

`DATA_SRC_TO_MARKET` 给数据源到市场的静态映射（`BAO_STOCK→CN`、`CCXT→CRYPTO`、`US_STOCK→US`），
但 **yfinance 一家可取美/港/A**，故 `detect_market(data_src, code)` 以**代码后缀/前缀**动态路由：

1. `data_src==CCXT` 或 code 含 `/`（`BTC/USDT`）→ `CRYPTO`；
2. `BAO_STOCK` → `CN`；
3. 后缀 `.HK` → `HK`；`.SS/.SZ/.SH` → `CN`；
4. Futu 前缀 `HK./US./SZ./SH.` → 对应市场；
5. 纯 6 位数字（无点）→ `CN`；纯字母 ticker → `US`；默认 `US`。

`get_market_capability(market)` 返回能力表。该模块被 `Strategy.Backtester`、`Strategy.ChanStrategy`
（注入 `market_cap` 决定能否做空）、`Trade.ChanTradeExecutor` 共享，是"**回测能跑的规则 = 实盘同样拦得住**"的
单一事实来源；`Script.SmokeOffline.test_market_routing` 专门冒烟 `detect_market` 正确性。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `__init__.py` | 空（包声明） |
| `CEnum.py` | 全局枚举：`DATA_SRC/KL_TYPE/KLINE_DIR/FX_TYPE/BI_DIR/BI_TYPE/BSP_TYPE/AUTYPE/MACD_ALGO/DATA_FIELD` 等 |
| `CTime.py` | `CTime` 时间对象（`auto` 日线时间戳自适应） |
| `ChanException.py` | `ErrCode`（三段号段）+ `CChanException` |
| `Cache.py` | `make_cache` 方法级 memoize 描述符 |
| `FuncUtil.py` | 工具函数 + `_dif_pullback_zero` + **`is_macd_divergence`（背驰核心）** |
| `MarketCapability.py` | `MARKET/MarketCapability/DEFAULT_CAPABILITIES/detect_market/get_market_capability` |

## 六、与其他模块的协作

- **被全仓库 import**：`CEnum` 的类型被 `KLine/Bi/Seg/ZS/BuySellPoint/Trend/Strategy/Plot` 广泛使用；
  `CTime` 是 K 线时间与区间套窗口比较的基础；`ChanException` 是统一抛错通道；`Cache` 优化派生量。
- **喂给 BuySellPoint/Trend**：`is_macd_divergence`（配合 `MACD_ALGO`）是笔/线段/中枢"力度衰竭"的判据入口，
  直接影响一类买卖点（趋势/盘整背驰）的成立与否。
- **喂给 Strategy/Trade**：`MarketCapability` 是回测成本、做空门控、T+1/lot 取整、实盘执行器风控的共同依据。
- **与 DataAPI 呼应**：`DATA_FIELD` 供字段映射，`kltype_lt_day` 供分钟级判断，`str2float` 供数值容错。
