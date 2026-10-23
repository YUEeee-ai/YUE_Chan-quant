# Combiner —— K线包含合并与顶底分型识别

## 一、模块定位

`Combiner` 是整个缠论计算框架的**最底层形态学引擎**。它做两件事：

1. **K线包含关系处理（合并）**：把原始行情中高低点互相"包含"的相邻 K 线，按上升/下降方向压缩成一根"合并 K 线"（代码里叫 `CKLine` / `CKLine_Combiner`），使得最终得到的 K 线序列不再有包含关系。
2. **顶分型 / 底分型识别**：在合并后的序列上，比较相邻三根 K 线的高低点，标出中间那根是"顶分型"还是"底分型"。

分型是"笔"的端点，笔是"线段"的端点，线段是"中枢"的构件。因此本模块是笔、线段、中枢、买卖点一切上层结构的**地基**。

值得注意的是，本模块被刻意设计成一个**泛型基类 `CKLine_Combiner[T]`**：`T` 既可以是原始 K 线单元（`CKLine_Unit`），也可以是"笔"（`CBi`）。这样同一套"包含合并 + 分型"算法，在形态学层用于合并 K 线、在走势层用于合并"特征序列元素"（线段划分，见 `Seg/Eigen.py`）。**一份算法，两级复用**，这是本框架最重要的架构决策之一。

- 关键类：`CKLine_Combiner`（泛型合并器）、`CCombine_Item`（元素适配器）。
- 关键枚举（`Common/CEnum.py`）：`KLINE_DIR{UP,DOWN,COMBINE,INCLUDED}`、`FX_TYPE{TOP,BOTTOM,UNKNOWN}`。

## 二、对应缠论课程

本模块严格实现缠师对 **K 线包含处理** 与 **顶底分型** 的原始定义，重点对应：

- **第 62 课《分型、笔与线段》**：顶分型/底分型定义、包含关系的合并方向、上升/下降一笔的基本形态。
- **第 65 课《再说说分型、笔、线段》**：包含关系的记号化表述、结合律与顺序原则、向上/向下的几何定义。
- （相关）**第 77 课《一些概念的再分辨》**：分型标记与"相邻分型必须满足结合律"的补充说明，为笔/线段共用。

## 三、书中关键原文

> 像图1这种，第二K线高点是相邻三K线高点中最高的，而低点也是相邻三K线低点中最高的，本ID给一个定义叫顶分型；图2这种叫底分型，第二K线低点是相邻三K线低点中最低的，而高点也是相邻三K线高点中最低的。
>
> ——《教你炒股票62：分型、笔与线段》

> 顶分型的最高点叫该分型的顶，底分型的最低点叫该分型的底，由于顶分型的底和底分型的顶是没有意义的，所以顶分型的顶和底分型的底就可以简称为顶和低。
>
> ——《教你炒股票62：分型、笔与线段》

> 实际图形里，有些复杂的关系会出现，就是相邻两K线可以出现如图6这种包含关系，也就是一K线的高低点全在另一K线的范围里，这种情况下，可以这样处理，在向上时，把两K线的最高点当高点，而两K线低点中的较高者当成低点，这样就把两K线合并成一新的K线；反之，当向下时，把两K线的最低点当低点，而两K线高点中的较低者当成高点，这样就把两K线合并成一新的K线。经过这样的处理，所有K线图都可以处理成没有包含关系的图形。
>
> ——《教你炒股票62：分型、笔与线段》

> 而图7，就给出了经过以上处理，没有包含关系的图形中，三相邻K线之间可能组合的一个完全分类，其中的二、四，就是分别是顶分型和底分型，一可以叫上升K线，三可以叫下降K线。所以，上升的一笔，由结合律，就一定是底分型+上升K线+顶分型；下降的一笔，就是顶分型+下降K线+底分型。
>
> ——《教你炒股票62：分型、笔与线段》

> 用[di，gi]记号第i根K线的最低和最高构成的区间，当向上时，顺次n个包含关系的K线组，等价于[maxdi，maxgi]的区间对应的K线，也就是说，这n个K线，和最低最高的区间为[maxdi，maxgi]的K线是一回事情；向下时，顺次n个包含关系的K线组，等价于[mindi，mingi]的区间对应的K线。
>
> ——《教你炒股票65：再说说分型、笔、线段》

> 结合律是有关本ID这理论中最基础的，在K线的包含关系中，当然也需要遵守，而包含关系，不符合传递律……因此在K线包含关系的分析中，还要遵守顺序原则，就是先用第1、2根K线的包含关系确认新的K线，然后用新的K线去和第三根比，如果有包含关系，继续用包含关系的法则结合成新的K线，如果没有，就按正常K线去处理。
>
> ——《教你炒股票65：再说说分型、笔、线段》

> 假设，第n根K线满足第n根与第n+1根的包含关系，而第n根与第n-1根不是包含关系，那么如果gn>=gn-1，那么称第n-1、n、n+1根K线是向上的；如果dn<=dn-1，那么称第n-1、n、n+1根K线是向下的。
>
> ——《教你炒股票65：再说说分型、笔、线段》

> 如果没有包含关系，3个K线就可以决定一个分型，但注意，任何相邻的分型之间必须满足结合律，也就是，不能有些K线分属不同的分型，这样是不允许的。
>
> ——《教你炒股票77：一些概念的再分辨》

## 四、实现思路

### 4.1 `CCombine_Item`（CombineItem.py）—— 统一元素视图的适配器

合并算法只关心四个量：`time_begin / time_end / high / low`。但"可被合并的元素"在本框架里有三种：原始 K 线 `CKLine_Unit`、笔 `CBi`、线段 `CSeg`。`CCombine_Item.__init__(item)` 用 `type(item) ==` 做**运行时分派**，把三者统一映射成一个只含高低点的中间对象：

- `CBi`：`time_begin = begin_klc.idx`，`time_end = end_klc.idx`，`high = item._high()`，`low = item._low()`（时间维用的是**合并 K 线索引 `idx`**，而非日历时间，便于在特征序列里比较先后）。
- `CKLine_Unit`：起止时间都是该 K 线自身 `time`，高低点取原始 `high/low`。
- `CSeg`：起止取首笔/末笔的 `begin_klc.idx / end_klc.idx`，极值取 `_high()/_low()`。
- 其它类型抛 `CChanException(..., ErrCode.COMMON_ERROR)`。

**坑与要点**：这里用了函数内 `from ... import` 做**惰性导入**（`CBi / CKLine_Unit / CSeg`），是为了打断 `Combiner ↔ KLine ↔ Bi ↔ Seg` 之间的循环依赖。`CBi`/`CSeg` 调用的是私有 `_high()/_low()`（带缓存的几何极值），而非公开的 `high/low` 属性——`CBi` 的高低点取决于笔的方向（上升笔高点在 `end_klc`，下降笔高点在 `begin_klc`），必须用 `_high()/_low()` 才能拿到正确极值。

### 4.2 `CKLine_Combiner[T]` 的核心数据结构（KLineCombiner.py）

泛型基类，每个实例代表**一根"正在生长的"合并元素**。私有字段：

- `__time_begin / __time_end`：合并跨度（起始终止）。
- `__high / __low`：当前合并后的极值包络，随合并动态收缩。
- `__lst: List[T]`：本合并元素内部聚合的所有原始子元素（K 线或笔）。这就是"顺次 n 个包含关系的 K 线组等价于一个区间"（第 65 课）的落地。
- `__dir`：当前合并方向（`UP`/`DOWN`），**决定后续遇到包含时取 max 还是 min**。它由上一根非包含 K 线相对本 K 线的位置推断并传入。
- `__fx`：分型类型，初值 `UNKNOWN`。
- `__pre / __next`：链表指针，指向相邻合并元素。
- `make_cache` 装饰器（`Common/Cache.py`）：给 `get_high_peak_klu / get_low_peak_klu` 做结果缓存；每当 `high/low/next/pre` 变化时调用 `clean_cache()` 失效缓存。

### 4.3 `test_combine()` —— 判定两元素的关系（算法第一步）

输入"当前合并元素 self"与"新元素 item"的高低点，返回四种关系之一：

| 条件 | 返回值 | 含义 |
|------|--------|------|
| `self.high >= item.high and self.low <= item.low` | `COMBINE` | self 完全包含 item，需合并 |
| `self.high <= item.high and self.low >= item.low` | `INCLUDED`/`COMBINE` | item 完全包含 self；默认 `COMBINE`，`exclude_included=True` 时返回 `INCLUDED` |
| `self.high > item.high and self.low > item.low` | `DOWN` | 两高点两低点都更低——下降关系 |
| `self.high < item.high and self.low < item.low` | `UP` | 都更高——上升关系 |

其余情形（高低交错、既非包含也无明确方向）理论上不可能出现，出现即抛 `ErrCode.COMBINER_ERR`。

**`allow_top_equal`（等高点特判）**：这是放宽变体，服务线段特征序列。
- `== 1`：当 `self.high == item.high and self.low > item.low`（顶部相等、被包含）时，判为 `DOWN` 而**不合并**；
- `== -1`：当 `self.low == item.low and self.high < item.high`（底部相等）时判为 `UP` 而不合并。
默认 `None` 走标准分支，会合并。K 线合并路径不会传这个参数，只有线段特征序列（`EigenFX`）会用到。

### 4.4 `try_add()` —— 执行合并（算法第二步）

拿到 `test_combine` 的结果 `_dir`；若为 `COMBINE`，则：
1. 把 `unit_kl` 追加进 `__lst`；若是 `CKLine_Unit`，调用 `unit_kl.set_klc(self)` 反向登记归属。
2. **严格按方向收缩包络**（第 62 课核心）：
   - `dir == UP`：`high = max(high, item.high)`，`low = max(low, item.low)`（高高、低高）；
   - `dir == DOWN`：`high = min(high, item.high)`，`low = min(low, item.low)`（低低、高低）。
3. **一字 K 线特判**：`if combine_item.high != combine_item.low or combine_item.high != self.high`——当新元素是 `high==low` 的一字线（涨跌停、集合竞价）时，避免它把包络错误地拉到 max/min；只有当它不是"与当前高点相同的一字线"时才收缩。DOWN 分支同理用 `low != self.low` 判断。
4. 更新 `__time_end = combine_item.time_end`，并 `clean_cache()`。

无论是否合并，`try_add` 都会把 `_dir`（`UP`/`DOWN`/`COMBINE`）返回给调用方 `CKLine_List`，调用方用它设置"下一根新建 K 线的方向"。`dir` 既非 `UP` 也非 `DOWN` 时抛 `COMBINER_ERR`。

### 4.5 `update_fx()` —— 顶/底分型判定（对应第 62 课定义）

三根合并元素 `_pre / self / _next` 就位后调用：
1. 先把三者的 `pre/next` 链表关系连好。
2. **标准分支**（`exclude_included=False`）：
   - 顶分型：`_pre.high < self.high and _next.high < self.high and _pre.low < self.low and _next.low < self.low` —— 即"中间那根高点最高、低点也最高"，与第 62 课吻合 → `FX_TYPE.TOP`；
   - 底分型：四路 `>` 全部反向 → `FX_TYPE.BOTTOM`。
3. **`exclude_included=True` 分支**（线段特征序列专用放宽变体）：允许"相等"的边缘情形判为分型（例如 `_next.high <= self.high`），并配合 `allow_top_equal` 精确控制顶相等/底相等时的取舍。默认走标准分支。

### 4.6 `get_high_peak_klu / get_low_peak_klu` —— 极值回溯定位

合并元素内部高低点可能不落在首尾子元素上。这两个方法**从 `__lst` 末尾反向遍历**，返回 `high`（或 `low`）等于包络值的那个原始子元素，供笔定位真实极值 K 线（`CBi.get_begin_klu/get_end_klu`）。带 `@make_cache` 缓存，找不到则抛 `COMBINER_ERR`。反向遍历是为了在多个相同极值时取**时间上最靠近端点**的那根，符合"当下性"。

### 4.7 与配置开关的关系

- 本模块自身**不直接读取 `CChanConfig`**，是纯粹的几何算法；但 `exclude_included` / `allow_top_equal` 由上层线段算法（`Seg`）按 `seg_algo` 传入，影响特征序列是否做包含合并。
- `KLINE_DIR`、`FX_TYPE` 枚举定义在 `Common/CEnum.py`。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `CombineItem.py` | `CCombine_Item`：把 `CKLine_Unit / CBi / CSeg` 统一适配成 `(time_begin, time_end, high, low)` 视图 |
| `KLineCombiner.py` | `CKLine_Combiner[T]`：包含合并（`test_combine`/`try_add`）、分型识别（`update_fx`）、极值定位、链表指针与缓存 |
| `__init__.py` | 空文件（包标记） |

## 六、与其他模块的协作

- **`KLine`**：`CKLine(CKLine_Combiner[CKLine_Unit])` 继承本模块，加上 `idx`、`kl_type` 与分型有效性校验（`check_fx_valid`）。`CKLine_List.add_single_klu` 每喂入一根原始 K 线就调用 `try_add`，非合并时新建 `CKLine` 并对倒数第二根调 `update_fx`。
- **`Bi`**：笔的端点就是本模块识别出的 `FX_TYPE.TOP/BOTTOM` 合并 K 线。
- **`Seg`**：`Eigen.CEigen(CKLine_Combiner[CBi])` **直接复用本模块的 `try_add`**，把"笔"当 K 线做包含合并，构建线段的特征序列；`update_fx` 覆写后额外标记缺口 `gap`。这是本模块泛型化设计的价值所在。
- 输出结果贯穿全框架：分型 → 笔 → 线段 → 中枢 → 买卖点，源头都在 `Combiner`。
