# DataAPI —— 数据源适配层

## 一、模块定位

`DataAPI` 是**行情数据的统一接入层**。各数据源（yfinance、baostock、ccxt……）的原始接口、
字段名、时间格式、复权方式差异极大，本层把它们**归一到同一个基类 `CCommonStockApi`**，
对外只暴露一个契约：给定 `code / k_type / begin_date / end_date / autype`，
`get_kl_data()` 逐根 `yield` 出标准化的 `CKLine_Unit`（内部 K 线单元）。

这样上游 `Chan.CChan` 完全不关心数据来自哪个市场/哪个厂商，只需按 `DATA_SRC` 枚举取对应实现类。

本层为**纯工程基础设施，无直接对应缠论课**——它服务于缠论计算链条的最前端"喂 K 线"，
其正确性（尤其是复权一致性）直接决定笔/线段/中枢能否被稳定地算出来。

## 二、对应缠论课程

**无直接原典对应，服务于"原始 K 线 → CKLine_Unit"的数据接入层。**
缠论的一切结构（笔、线段、中枢）都建立在经过包含关系处理后的 K 线上，而 K 线来自本层；
因此本层最关键的"复权"处理虽非缠论概念，却是保证"走势必完美"分析可复现的前提。

## 三、书中关键原文

**本层无直接原典对应。** 其服务的概念是缠论分析的最基本输入——原始（未合并）K 线序列：
所有笔、线段、中枢、买卖点都由 `CChan` 在本层交付的 `CKLine_Unit` 流上递归构建。

## 四、实现思路

### 4.1 统一接口：CCommonStockApi（CommonStockAPI.py）

基类 `CCommonStockApi` 定义了所有数据源必须遵守的契约：

- 构造：`__init__(code, k_type, begin_date, end_date, autype)`，并调用 `SetBasciInfo()`
  填充 `self.name`（标的名）与 `self.is_stock`（是否个股，指数/基金为 False）。
- 抽象方法：`get_kl_data() -> Iterable[CKLine_Unit]`（核心，逐根产出）、
  `SetBasciInfo()`、`do_init()` / `do_close()`（`@classmethod`，负责登录/释放全局连接）。

**共用工具**（避免各源重复实现）：

- `_FIELD_DICT`：外部列名 → 内部 `DATA_FIELD` 枚举的映射表
  （`time/date→FIELD_TIME`、`open/high/low/close`、`volume→FIELD_VOLUME`、
  `amount→FIELD_TURNOVER`（成交额）、`turn→FIELD_TURNRATE`（换手率））。
  注意 `date` 与 `time` 都映射到 `FIELD_TIME`，让不同源用不同列名也能落到同一内部字段。
- `GetColumnNameFromFieldList(fields)`：把 `"date,open,..."` 字符串转成 `DATA_FIELD` 列表。
- `parse_time_column(inp)`：兼容**三种时间串格式**——10 位日线 `2021-09-13`、
  17 位数字时间戳 `20210902113000000`、19 位分钟线 `2021-09-13 11:30:00`，返回 `CTime`；
  其它长度直接抛异常（不猜）。
- `create_item_dict(data, column_name, auto=True)`：`data[0]` 当时间串解析，其余 `str2float`，
  与列名 zip 成行字典。

### 4.2 工厂路由：Chan.GetStockAPI(src)

`CChan` 不直接 import 各源，而由 `Chan.GetStockAPI` 按 `DATA_SRC` 枚举路由：
`BAO_STOCK→CBaoStock`、`CCXT→CCXT`、`US_STOCK→CUSStockApi`；此外支持
`"custom:文件名.类名"` 形式**动态加载自定义数据源**（放于 `DataAPI/` 下，`exec+eval` 返回类）。
未匹配抛 `CChanException(SRC_DATA_TYPE_ERR)`。调用方（`Rotation.fetch_closes`、`CChan`）统一走
`api_cls.do_init() → 实例化 → get_kl_data() → api_cls.do_close()`。

### 4.3 CUSStockApi（USStockAPI.py，yfinance：美/港/A 统一取数）

- **代码约定（yfinance 后缀风格）**：美股 `AAPL`、港股 `0700.HK`、A 股 `600519.SS / 000001.SZ`；
  市场归属由 `Common.MarketCapability.detect_market` 按后缀路由（与交易/回测层共享同一识别逻辑）。
- `INTERVAL_MAP`：`KL_TYPE → yfinance interval`（`1m/5m/15m/30m/60m/1d/1wk/1mo`）；
  `PERIOD_MAP`：未给 `begin_date` 时的回溯期（分钟线 7–730 天、日周月 `max`）。
- 下载用 `yf.Ticker(code).history(**kwargs)`，**`auto_adjust=False`（手动复权）**。
- **复权处理（关键坑，注释详尽）**：
  - `AUTYPE.QFQ` 前复权：用 `ratio = Adj Close / Close` 同比例缩放 O/H/L/C，并 `.round(3)`。
    原因：yfinance 服务端 `Adj Close` 存在约 `1e-6` 级抖动（同标的不同请求返回略有差异），
    噪声注入复权价后会在 K 线合并的等值比较上**翻转笔/中枢结构**，导致同命令多次运行结果不同
    （000001.SZ 实测 7 次 7 个结果）；舍入到 0.001（远低于任何市场最小报价单位）消除抖动、保证可复现。
  - 若列里没有 `Adj Close`（新版 yfinance 字段变化）**直接报错**，拒绝"看似复权实则未复权"。
  - `AUTYPE.NONE`：用原始价，不处理；`AUTYPE.HFQ` 后复权：**明确 raise**（history 不直接提供），
    引导用户改前复权/不复权或换 BaoStock——避免静默返回错误价格。
- `_parse_row`：兼容 `pd.Timestamp/datetime`，大小写列名兜底（`Open/open`），
  `open_p==0 and close_p==0` 跳过无效行，异常返回 `None`（不中断整条流）。产出
  `CKLine_Unit(data_dict, autofix=True)`（`autofix` 让 K 线单元自动修正高低包含等）。

### 4.4 CBaoStock（BaoStockAPI.py，baostock：A 股/指数）

- 复用基类的 `create_item_dict / GetColumnNameFromFieldList`（字段映射、时间解析都走通用路径）。
- **字段随级别切换**：`kltype_lt_day(k_type)`（分钟级以下）时只取 `time,open,high,low,close`
  （指数无分钟数据时 `is_stock` 校验并抛"指数没有分钟级数据"）；天级以上取完整
  `date,open,high,low,close,volume,amount,turn`。
- **复权交给服务端**：`autype_dict={QFQ:"2", HFQ:"1", NONE:"3"}` 作为 `adjustflag` 传给
  `bs.query_history_k_data_plus`（BaoStock 自身支持三种复权，无需本地缩放）。
- `__convert_type`：`KL_TYPE → baostock frequency`（`d/w/m/5/15/30/60`）。
- 全局连接：`do_init` 里 `bs.login()`（用类属性 `is_connect` 去重），`do_close` 里 `bs.logout()`。
- `SetBasciInfo`：`bs.query_stock_basic` 取 `code_name` 与 `stock_type`（`'1'` 为个股）。
- 每行 `rs.next()` 拉取、`error_code!='0'` 立即抛异常。

### 4.5 CCXT（CCXT.py，加密货币现货）

- 可选依赖 `ccxt`：导入失败置 `_CCXT_AVAILABLE=False`，运行期取数时才
  `raise CChanException("ccxt 未安装...", SRC_DATA_TYPE_ERR)`（友好报错，不在 import 期崩）。
- 固定 `ccxt.binance()`；`__convert_type`：`KL_TYPE → timeframe`
  （`1d/1w/1M/5m/15m/30m/1h`），不支持的级别抛异常。
- **时间处理**：`since` 用 `parse8601(begin_date T00:00:00)`，缺省从交易所最早数据开始；
  `until` 用 `end_date T23:59:59`（毫秒）。用 **UTC**（`fromtimestamp(..., tz=utc)`）避免本地时区
  偏移导致时间戳错位。
- **分页拉取**：`fetch_ohlcv(limit=1000)` 循环，`since = 最后一根 +1` 续页；`ts>until` 提前 return，
  批次不足 `limit` 或 `since>until` 时结束——保证只取到回测右端。
- 只产出 OHLC（无成交额/换手），`auto=not kltype_lt_day(...)` 控制时间是否为分钟级。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `__init__.py` | 空（包声明） |
| `CommonStockAPI.py` | 基类 `CCommonStockApi` + 共用工具（`_FIELD_DICT/GetColumnNameFromFieldList/parse_time_column/create_item_dict`） |
| `USStockAPI.py` | `CUSStockApi`（yfinance，美/港/A；手动前复权 + 舍入防抖动） |
| `BaoStockAPI.py` | `CBaoStock`（baostock，A 股/指数；服务端复权 + 登录态管理） |
| `CCXT.py` | `CCXT`（ccxt/binance，加密货币；UTC + 分页） |

## 六、与其他模块的协作

- **下游被调**：`Chan.GetStockAPI` 工厂 → `CChan` 加载各级别 K 线；`Strategy.Rotation.fetch_closes`
  也直接用它取收盘价序列做轮动打分。
- **依赖 Common**：`CEnum`（`DATA_SRC/KL_TYPE/AUTYPE/DATA_FIELD`）、`CTime`、
  `ChanException`、`FuncUtil`（`str2float/kltype_lt_day`）。
- **产出交给 KLine**：每行标准化为 `KLine.KLineUnit.CKLine_Unit`，后续包含关系合并、笔、线段、
  中枢、买卖点全部在其上构建。
- **与 Trade/Strategy 的一致性**：`USStockApi` 的市场后缀识别与 `Common.MarketCapability.detect_market`
  一致，保证"数据源识别的市场"与"回测/实盘施加的交易规则市场"是同一个。
