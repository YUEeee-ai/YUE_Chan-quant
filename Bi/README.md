# Bi —— 笔的生成、严格笔与力度度量

## 一、模块定位

`Bi` 模块把 `Combiner` 识别出的**顶/底分型**串成**笔（`CBi`）**——缠论里最小的走势单元，也是线段划分的构件。它做三件事：

1. **成笔判定**：在分型序列上，按"顶底交替 + 跨度约束 + 极值约束"决定是否连成一笔。
2. **增量维护笔序列**：`CBiList` 以逐 K 线（step）模式动态增删笔，并管理尾部尚未确认的**虚笔**。
3. **笔的力度度量**：`CBi` 提供方向、振幅、跨度、以及 MACD 红绿柱面积/峰值等一系列"类背驰力度"指标，供上层线段与买卖点比较进出力度。

三个核心文件：`Bi.py`（笔对象 + 力度度量）、`BiConfig.py`（成笔口径开关）、`BiList.py`（笔序列的生成与维护）。

- 关键枚举：`BI_DIR{UP,DOWN}`、`FX_TYPE`、`FX_CHECK_METHOD`、`KLINE_DIR`、`MACD_ALGO`、`BI_TYPE`。

## 二、对应缠论课程

- **第 62 课《分型、笔与线段》**：笔的定义（相邻顶底之间）、一笔最基本图形（顶底之间还有一根 K 线）、老笔"顶底必须各有独立 K 线"的要求；读后感补充的**新笔定义**（放松跨度条件）。
- **第 65 课《再说说分型、笔、线段》**：先顶后底构成向下一笔、先底后顶构成向上一笔；图形可唯一分解为上下交替的笔；线段至少三笔。
- **第 77 课《一些概念的再分辨》**：笔划分唯一性的三步法，以及"同一笔中顶分型最高 K 线区间至少有一部分高于底分型最低 K 线区间"的约束（对应代码的 `end_is_peak` / `check_fx_valid`）。
- **第 24 课《MACD对背弛的辅助判断》**：用 MACD 红绿柱面积、黄白线比较两段力度——`CBi.cal_macd_metric` 的多种口径来源。

## 三、书中关键原文

> 两个相邻的顶和底之间构成一笔，所谓笔，就是顶和底之间的其他波动，都可以忽略不算，但注意，一定是相邻的顶和底，隔了几个就不是了。……而图5，是一笔的最基本的图形，顶和底之间还有一根K线。在实际分析中，都必须要求顶和底之间都至少有一K线当成一笔的最基本要求。
>
> ——《教你炒股票62：分型、笔与线段》

> 新笔定义：本ID想了想，计算了一下能量力度，觉得以后可以把笔的成立条件略微放松一下，就是一笔必须满足以下两个条件：1、顶分型与底分型经过包含处理后，不允许共用K线，也就是不能有一K线分别属于顶分型与底分型，这条件和原来是一样的，这一点绝对不能放松，因为这样，才能保证足够的能量力度；2、在满足1的前提下，顶分型中最高K线和底分型的最低K线之间（不包括这两K线），不考虑包含关系，至少有3根（包括3根）以上K线。
>
> ——《教你炒股票62：分型、笔与线段》（第62课读后感）

> 就可以严格地说，先顶后底，构成向下一笔；先底后顶，构成向上一笔。而所有的图形，都可以唯一地分解为上下交替的笔的连接。
>
> ——《教你炒股票65：再说说分型、笔、线段》

> 笔，必须是一顶一底，而且顶和底之间至少有一个K线不属于顶分型与底分型。当然，还有一个最显然的，就是在同一笔中，顶分型中最高那K线的区间至少要有一部分高于底分型中最低那K线的区间，如果这条都不满足，也就是顶都在低（底）的范围内或顶比底还低，这显然是不可接受的。
>
> ——《教你炒股票77：一些概念的再分辨》

> 一、确定所有符合标准的分型。二、如果前后两分型是同一性质的，对于顶，前面的低于后面的，只保留后面的，前面那个可以X掉；对于底，前面的高于后面的，只保留后面的，前面那个可以X掉。不满足上面情况的，例如相等的，都可以先保留。三、经过步骤二的处理后，余下的分型，如果相邻的是顶和底，那么这就可以划为一笔。
>
> ——《教你炒股票77：一些概念的再分辨》

> C段的走势类型完成时对应的MACD柱子面积（向上的看红柱子，向下看绿柱子）比A段对应的面积要小，这时候就构成标准的背弛。
>
> ——《教你炒股票24：MACD对背弛的辅助判断》

## 四、实现思路

### 4.1 `CBiConfig`（BiConfig.py）—— 成笔口径的四个开关

| 参数 | 默认 | 作用 |
|------|------|------|
| `bi_algo` | `"normal"` | `"fx"` 时 `can_make_bi` 恒真（只看分型交替，最宽松）；`normal` 走完整校验 |
| `is_strict` | `True` | **严格笔（老笔）开关**：`True` 要求分型跨度 `>=4`（两分型不共用 K 线，中间有独立合并 K 线）；`False` 走新笔（跨度 `>=3` 且原始 K 线数 `>=3`） |
| `bi_fx_check` | `"strict"`（顶层默认，`CBiConfig` 形参默认 `half`） | 映射为 `FX_CHECK_METHOD.{STRICT,LOSS,HALF}`，决定端点极值比较范围，交给 `CKLine.check_fx_valid` |
| `gap_as_kl` | `True` | 计算笔跨度时**把缺口当成一根额外 K 线** |
| `bi_end_is_peak` | `True` | 要求笔的两端是该段极值（`end_is_peak`） |

> 注意默认值漂移：`ChanConfig.py` 构造 `CBiConfig` 时显式传 `bi_fx_check="strict"`，覆盖 `CBiConfig` 形参默认 `half`；框架统一口径是**严格笔 + strict 分型校验**。

### 4.2 `CBi`（Bi.py）—— 笔对象

**方向由起点分型推断**：`set()` 中，起点 `begin_klc.fx==BOTTOM → BI_DIR.UP`，`==TOP → DOWN`，否则抛 `BI_ERR`。`check()` 再验证方向与端点值序一致（下降笔 `begin.high > end.low`，上升笔相反），不一致抛 `BI_ERR`。这直接落地第 65 课"先顶后底=向下一笔"。

**几何度量**（均 `@make_cache`）：
- `get_begin_val/get_end_val`：起/终的极值价（上升笔起点取 low、终点取 high）。
- `get_begin_klu/get_end_klu`：调用 `begin_klc/end_klc.get_peak_klu(...)` 定位真实极值所在的原始 K 线单元。
- `amp / _high / _low / _mid / get_klu_cnt / get_klc_cnt`：振幅、笔的高低、中位价、跨度（K 线单元数 / 合并 K 线数）。

**虚笔端点管理**（尾部未确认）：`update_virtual_end(new_klc)` 记住原 `sure_end` 后把终点临时延伸到新 K 线、置 `is_sure=False`；`restore_from_virtual_end` 回滚；`is_virtual_end()` 判断 `sure_end` 是否非空。这是"当下性"的实现——走势还在长，最后一笔随时可能改写。

**MACD 力度分派 `cal_macd_metric(macd_algo, is_reverse)`**（背驰比较的基础，口径对应第 24 课）：
- `AREA` → `Cal_MACD_half(is_reverse)`：从端点起**沿同向累加柱面积、遇反向柱即停**（`Cal_MACD_half_obverse` 从起点正向扫、`Cal_MACD_half_reverse` 从终点反向扫），最贴合"这一段趋势的力度"；
- `PEAK` → 笔内同向最大柱高；`FULL_AREA` → 全笔 `abs(macd)` 之和；`DIFF` → 柱极差；`SLOPE`/`AMP` → 借助 `Common.FuncUtil` 计算斜率/幅度；`DIF_PEAK` → 黄白线（DIF）在笔内极值（上升取 max、下降取 min，对应第 24 课"黄白线回拉 0 轴"）；`VOLUMN/AMOUNT/*_AVG` → 累加 `trade_info` 成交量/额，缺数据返回 0.0。不支持的 `macd_algo` 抛 `PARA_ERROR`。

### 4.3 `CBiList`（BiList.py）—— 笔序列的增量生成

**核心状态**：`bi_list`（笔表）、`last_end`（末笔尾部所在的 K 线）、`free_klc_lst`（第一笔画出前的缓存，仅为精度，不影响后续）。

**主流程 `update_bi(klc, last_klc, cal_virtual)`**：`klc` 是倒数第二根 K 线、`last_klc` 是最后一根。先 `update_bi_sure(klc)` 处理确定的分型，`cal_virtual=True` 时再 `try_add_virtual_bi(last_klc)` 补尾部虚笔。

**`update_bi_sure(klc)` 的分派逻辑**（对应第 77 课"同性质分型只留后者"的实时化版本）：
1. 先 `delete_virtual_bi()` 撤掉上一次的虚笔，记下撤前末 K 线索引 `_tmp_end`；
2. `klc.fx==UNKNOWN` → 无分型，仅返回"虚笔末点是否变了"；
3. 还没有任何笔 → `try_create_first_bi`；
4. `klc.fx == last_end.fx`（同性分型）→ `try_update_end`：**同向则延长/替换末笔端点**——上升笔遇更高顶、下降笔遇更低底才更新，这正是第 77 课"两同性分型保留更极端那个、X 掉另一个"的增量实现；
5. 反向分型 → `can_make_bi` 满足则 `add_new_bi` 新增一笔并返回 `True`；
6. 都不满足 → 返回 `_tmp_end` 是否变化（注释举例 `US.BELFA`：新增 K 线可能让原本的虚笔消失）。

**`can_make_bi(klc, last_end)` —— 成笔三条件**：
- `bi_algo=="fx"` 直接 `True`；
- 否则先要求 `last_end.check_fx_valid(klc, bi_fx_check)`（端点极值关系成立）且 `satisfy_bi_span`（跨度达标）；
- 若还开了 `bi_end_is_peak`，再要求 `end_is_peak(last_end, klc)`。

**`satisfy_bi_span` —— 老笔 vs 新笔的跨度**：
- `is_strict=True`：`get_klc_span >= 4`（严格笔/老笔：两分型之间至少一根独立合并 K 线）；
- `is_strict=False`（新笔）：`bi_span >= 3` **且** 两分型之间的原始 K 线单元总数 `uint_kl_cnt >= 3`——对应第 62 课新笔定义条件 2"……之间至少有 3 根以上 K 线"。

**`get_klc_span(klc, last_end)` —— 跨度与缺口**：基础跨度 = `klc.idx - last_end.idx`；`gap_as_kl=False` 直接返回；否则当跨度 `<4` 时逐根扫描，每发现一处 `has_gap_with_next()`（缺口）就把 `span += 1`——把缺口"当作一根 K 线"计入跨度（`span>=4` 时提前返回以加速）。

**`end_is_peak(last_end, cur_end)`**（模块级函数）：从 `last_end.next` 走到 `cur_end`，检查中间是否出现比 `cur_end` 更高（顶为底起点时）/更低（底为顶起点时）的 K 线；若有则端点不是极值，返回 `False`。落地第 77 课"顶必须真高、底必须真低"。

**虚笔维护 `try_add_virtual_bi(klc, need_del_end)`**：
- 若末笔方向上 `klc` 还在创新高/新低 → `update_virtual_end` 延长末笔；
- 否则从 `klc` 反向逐根找是否存在一个反向分型满足 `satisfy_bi_span` + `check_fx_valid(for_virtual=True)`，若有则新增一笔 `is_sure=False`（虚笔）。
`delete_virtual_bi`：末笔非确定时，若是虚端点则 `restore_from_virtual_end`，否则直接删除末笔。

`add_new_bi` 维护 `pre/next` 双向链表。

### 4.4 关键参数与默认值

框架统一口径（`ChanConfig.DEFAULT_ALGO_CONFIG`）：`bi_strict=True`（严格笔）、`bi_fx_check="strict"`、`gap_as_kl=True`、`bi_end_is_peak=True`。逐根回放时 `CKLine_List.add_single_klu` 会在 `triger_step=True` 下驱动 `update_bi`/`try_add_virtual_bi`。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `Bi.py` | `CBi`：笔对象——方向推断、几何度量、虚笔端点管理、`cal_macd_metric` 力度度量族 |
| `BiConfig.py` | `CBiConfig`：`bi_algo/is_strict/bi_fx_check/gap_as_kl/bi_end_is_peak` 成笔口径 |
| `BiList.py` | `CBiList`：笔序列增量生成（首笔、确定笔、跨度校验、端点极值、虚笔增删）+ 模块级 `end_is_peak` |

## 六、与其他模块的协作

- **上游依赖 `KLine` / `Combiner`**：笔的端点是带 `FX_TYPE` 的 `CKLine`；`check_fx_valid`、`has_gap_with_next`、`get_peak_klu` 都在 `KLine/Combiner` 里实现。`CKLine_List.add_single_klu` 每识别一个分型就调 `bi_list.update_bi`。
- **下游服务 `Seg`**：线段算法 `CEigen` 继承 `CKLine_Combiner[CBi]`，把笔当 K 线做包含合并（`CBi._high/_low` 被 `CCombine_Item` 读取）；`CBiList` 的 `bi_list` 是线段划分的输入。
- **下游服务 `ZS` / `BuySellPoint`**：中枢由笔重叠构造；`cal_macd_metric` 被进出中枢的两段笔调用做背驰比较。
- `CBi.parent_seg`、`set_seg_idx`、`bsp` 字段回指线段与买卖点，形成双向引用，便于绘图与查询。
