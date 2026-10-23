# ZS —— 走势中枢（生成、合并、级别扩张/延伸/新生）

## 一、模块定位

`ZS` 文件夹实现缠论体系里最核心的几何对象——**缠中说禅走势中枢（CZS）**，以及把笔/线段序列增量式地聚合成中枢序列的算法（`CZSList`）。中枢是缠论给“盘整 / 趋势 / 级别 / 买卖点”下精确定义的基石：

- 盘整 = 只含 **一个** 中枢；趋势 = 至少含 **两个依次同向** 的中枢。
- 中枢的三种演化：**延伸**（围绕同一区间震荡）、**扩展/扩张**（与前一中枢波动区间重叠 → 形成更大级别中枢）、**新生**（产生不重叠的同级别中枢 → 构成趋势）。
- 中枢区间 `[ZD, ZG]` 直接决定第三类买卖点的判据（回抽是否“回到中枢”）。

本模块还承载背驰（力度衰减）判定的落点 `CZS.is_divergence()`：比较“进中枢笔 `bi_in`”与“出中枢笔 `bi_out`”的 MACD 力度，为第一类买卖点提供依据（详见 `BuySellPoint`）。

文件：`ZS.py`（单个中枢对象 + 背驰判定）、`ZSConfig.py`（中枢合并开关）、`ZSList.py`（由笔/段列表构建中枢序列）。`__init__.py` 为空。

## 二、对应缠论课程

| 课号 | 标题 | 本模块对应的实现点 |
| --- | --- | --- |
| 17 | 走势终完美 | 中枢定义（至少三个连续次级别走势重叠）、盘整/趋势定义 |
| 18 | 不被面首的雏男是不完美的 | 中枢区间公式 `(max(低点), min(高点))`、走势类型延伸、中枢定理三（破坏） |
| 20 | 缠中说禅走势中枢级别扩张及第三类买卖点 | `[ZD,ZG]`、延伸/扩张/新生、级别延续定理、第三类买卖点判据 |
| 63 | 替各位理理基本概念 | 中枢递归存在性、“不同级别显微镜”比喻 |

## 三、书中关键原文

> “为了深入研究这复杂问题，必须先引入缠中说禅走势中枢的概念：某级别走势类型中，被至少三个连续次级别走势类型所重叠的部分，称为缠中说禅走势中枢。”

> “缠中说禅盘整：在任何级别的任何走势中，某完成的走势类型只包含一个缠中说禅走势中枢，就称为该级别的缠中说禅盘整。缠中说禅趋势：在任何级别的任何走势中，某完成的走势类型至少包含两个以上依次同向的缠中说禅走势中枢，就称为该级别的缠中说禅趋势。该方向向上就称为上涨，向下就称为下跌。”

——《教你炒股票17：走势终完美》

> “缠中说禅走势中枢：某级别走势类型中，被至少三个连续次级别走势类型所重叠的部分。具体的计算以前三个连续次级别的重叠为准，严格的公式可以这样表示：次级别的连续三个走势类型A、B、C，分别的高、低点是a1\a2，b1\b2，c1\c2。则，中枢的区间就是（max（a2，b2，c2），min（a1，b1，c1））”

> “这里最大的也是唯一的难点在于“走势类型的延伸”。……对于趋势来说，其“延伸”就在于同级别的同向“缠中说禅走势中枢”不断产生；而对于盘整来说，其“延伸”就在于不能产生新的“缠中说禅走势中枢”。……因此“走势类型延伸”是否结束的判断关键就在于是否产生新的“缠中说禅走势中枢”。”

> “某级别“缠中说禅走势中枢”的破坏，当且仅当一个次级别走势离开该“缠中说禅走势中枢”后，其后的次级别回抽走势不重新回到该“缠中说禅走势中枢”内。”

——《教你炒股票18：不被面首的雏男是不完美的。》

> “缠中说禅走势中枢由前三个连续次级别走势类型的重叠部分确定，其后的走势有两种情况：一、该走势中枢的延伸。二、产生新的同级别走势中枢。而在趋势里，同级别的前后缠中说禅走势中枢是不能有任何重叠的……如果三个连续次级别走势类型的重叠区间虽然不和前面的走势中枢有任何重叠，但围绕该中枢产生的波动触及前面走势中枢延续时的某个瞬间波动区间，这时候，就不能认为该走势类型是趋势，而只是产生一个更大级别的缠中说禅走势中枢。”

> “缠中说禅走势级别延续定理二：更大级别缠中说禅走势中枢产生，当且仅当围绕连续两个同级别缠中说禅走势中枢产生的波动区间产生重叠。”

> “特别地，再定义ZG= min(g1、g2)，ZD=max(d1、d2)，显然，[ZD，ZG]就是缠中说禅走势中枢的区间……缠中说禅走势中枢中心定理一：走势中枢的延伸等价于任意区间[dn，gn]与[ZD，ZG]有重叠。换言之，若有Zn，使得dn>ZG或gn<ZD，则必然产生高级别的走势中枢或趋势及延续。”

> “一个次级别走势类型向上离开缠中说禅走势中枢，然后以一个次级别走势类型回试，其低点不跌破ZG，则构成第三类买点；一个次级别走势类型向下离开缠中说禅走势中枢，然后以一个次级别走势类型回抽，其高点不升破ZD，则构成第三类卖点。”

——《教你炒股票20：缠中说禅走势中枢级别扩张及第三类买卖点》

> “一个对象的确立，特别是一个数学和几何对象的确立，首先要证明其存在性……例如中枢或走势类型这对象，如果不能证明其一定存在，而且是按级别存在的，那谈论就没意义了。所以，前面关于中枢的递归定义，就是解决这个问题的，是解决存在性问题。”

> “进而，就有了不同级别显微镜的比喻。……再次强调，什么级别的图和什么级别的中枢没有任何必然关系，走势类型以及中枢就如同显微镜下的观察物，是客观存在的，其存在性由上面所说最原始的递归定义保证，而级别的图，就如同显微镜，不同倍数的看这客观的图就看到不同的精细程度，如此而已。”

——《教你炒股票63：替各位理理基本概念》

## 四、实现思路

### 4.1 `CZS` 泛型中枢对象（ZS.py）

`LINE_TYPE = TypeVar('LINE_TYPE', CBi, "CSeg")`，`class CZS(Generic[LINE_TYPE])`。同一个类既能表示**笔中枢**（`LINE_TYPE=CBi`，由笔构成）也能表示**段中枢**（`LINE_TYPE=CSeg`，由线段构成，即级别递归的上一层）。这是缠论“显微镜倍数”思想（第63课）的代码落地：笔序列聚合出笔中枢，线段序列聚合出段中枢，逻辑完全复用 `CZSList`。

核心成员（`__init__` 传入构成中枢的 `lst: List[LINE_TYPE]`，`lst is None` 时用于 `make_copy` 复制路径，只建空壳由 `init_from_zs` 回填）：

- `__begin` / `__end`：中枢首尾 **KLU（`CKLine_Unit`）** 指针，永远指向具体 K 线单元，用于跨模块按 klu.idx 做增量对齐。
- `__low` / `__high`：中枢区间 `[low, high]`，**对应原文 `[ZD, ZG]`**：
  - `__low = max(bi._low() for bi in lst)` = ZD = `max(d1, d2)`（各段低点的最大值）；
  - `__high = min(bi._high() for bi in lst)` = ZG = `min(g1, g2)`（各段高点的最小值）；
  - `__mid = (low + high) / 2` 中枢中点（仅供绘图/参考）。
  计算封装在 `update_zs_range()`。注意 `low` 与 `high` 是“重叠出来的区间”，因此必然 `low <= high`（构造前提见 4.3）。
- `__peak_low`（初值 `+inf`）/ `__peak_high`（初值 `-inf`）：中枢所涉笔的**最宽极值**，对应原文里的 `DD=min(dn)`、`GG=max(gn)`。在 `update_zs_end()` 遍历每个元素时用 `item._low()/item._high()` 逐步刷新。`peak_low/peak_high` 服务于第三类买卖点“突破是否最极端”的校验（`bs3_break_zspeak`）与一类买卖点 `bs1_peak`。
- `__begin_bi` / `__end_bi`：中枢内部的首笔、末笔（`LINE_TYPE`）。
- `__bi_in` / `__bi_out`：**进入中枢的那一笔 / 离开中枢的那一笔**，由外部 `update_zs_in_seg`（KLineList.py）回填，不在构造时设置。`is_divergence` 背驰判定就是比较 `bi_in` 与 `bi_out`。
- `__bi_lst`：`begin_bi ~ end_bi` 之间的所有笔，同样由 `update_zs_in_seg` 通过 `set_bi_lst()` 回填，供 `out_bi_is_peak()` 与 `COMPOSITE_FULL` 的黄白线回抽零轴检测遍历内部 KLU。
- `__sub_zs_lst`：合并/扩张后被子中枢列表（见 4.4）。
- `__is_sure`：中枢是否“已坐实”，随段/笔的确定性传递。

缓存：`end_bi_break`、`out_bi_is_peak` 用 `@make_cache` 装饰，任何修改区间/端点的操作（`update_zs_range`、`update_zs_end`、`do_combine`、`set_bi_in/out/lst`、`init_from_zs`）都会调 `clean_cache()` 清缓存，这是关键的一致性约定，忘记清除会读到旧的突破判定结果。

### 4.2 中枢的“延伸”（try_add_to_end / in_range）

对应第20课**中心定理一**“走势中枢的延伸等价于任意区间[dn，gn]与[ZD，ZG]有重叠”：

- `in_range(item)` → `has_overlap(self.low, self.high, item._low(), item._high())`，判新笔是否与中枢区间 `[ZD,ZG]` 有重叠。
- `try_add_to_end(item)`：若 `in_range` 为真，则更新区间端点（`update_zs_end`），并在仍是一笔中枢时重算区间（`update_zs_range([begin_bi, item])`）返回 True；否则返回 False（说明该笔已离开中枢，触发 4.5 的破坏判定或新一段累积）。

`has_overlap(l1,h1,l2,h2,equal=False)`（`Common/FuncUtil.py`）默认严格不等号 `h2>l1 and h1>l2`，`equal=True` 时含边界 `h2>=l1 and h1>=l2`。

### 4.3 `CZSList` 的构建流程（ZSList.py）

`CZSList` 从笔（或段）列表**增量**构建 `zs_lst: List[CZS]`。关键参数与成员：

- `self.config`：`CZSConfig`（见 4.6）。
- `self.free_item_lst`：尚未凑成中枢的候选笔缓冲区。
- `self.FORCE_CAL_ALL`（默认 `False`）：debug 用；置 True 时 `update_last_pos` 直接把 `last_sure_pos=-1`，即每次全量重算。理论上开不开结果一致，但效率差很多。
- `self.last_sure_pos`：上次计算里“最后一个 **已坐实** 段的起始 KLU idx”，用它做增量：只对 `seg_need_cal(seg)`（段末 klu.idx > last_sure_pos）之后的段重算，之前的旧中枢保留。

构建中枢的判据在 `try_construct_zs(lst, is_sure)`：
- 若未开 `one_bi_zs`：`len==1` 直接返回 None；否则取最后两个 `lst[-2:]`，判 `min_high > max_low`（即存在 `[ZD,ZG]` 重叠）才 `CZS(lst)`。
- 若开了 `one_bi_zs`：允许单笔中枢（`min_high`/`max_low` 由单笔自身高低构成，恒成立）。

`add_to_free_lst(item, is_sure)`：先做去重（`item.idx == free_item_lst[-1].idx` 时弹出末尾，防止笔因新高/新低更新带来的重复 bug），追加后调 `try_construct_zs`。若成功且 `res.begin_bi.idx > 0`（**禁止第一笔就是中枢起点**）才 append 进 `zs_lst`、清空缓冲并 `try_combine()`。

`update(bi, is_sure)`：优先尝试把笔并入当前末中枢（`try_add_to_end`）→ 延伸成功则再 `try_combine()`（`zs_combine_mode=peak` 时延伸可能触发合并）；否则走 `add_to_free_lst` 累积。

`add_zs_from_bi_range(seg_bi_lst, seg_dir, seg_is_sure)`：按线段喂笔。规则：
- 与段方向**同向**的笔跳过（`bi.dir == seg_dir` continue）——中枢由“与中枢形成方向一致的次级别走势（Z 走势段）”重叠确定（第20课原文：回升形成的中枢由向上的次级别区间重叠确定）。
- 段内**第一笔**（`deal_bi_cnt < 1`）只进缓冲（`add_to_free_lst`），避免 `try_add_to_end` 把首笔误并入上一段的末中枢；之后才走 `update`。

主入口 `cal_bi_zs(bi_lst, seg_lst)`：
1. 先裁掉 `zs_lst` 里 `end.idx > last_sure_pos` 的旧中枢（保留已坐实部分）；
2. 逐段（`seg_need_cal` 为真）取 `bi_lst[seg.start_bi.idx : seg.end_bi.idx+1]` 喂 `add_zs_from_bi_range`；
3. 处理**尚未成段的尾部笔**：`add_zs_from_bi_range(bi_lst[seg_lst[-1].end_bi.idx+1 :], revert_bi_dir(seg_lst[-1].dir), False)`——尾部虚段方向取反、`is_sure=False`。

`try_combine()`：见 4.4，受 `need_combine` 控制。

### 4.4 中枢的“扩张/合并”（combine / do_combine）

对应第20课“更大级别中枢产生 ⇔ 围绕连续两个同级别中枢的波动区间产生重叠”。`combine(zs2, combine_mode)`：

- 前置拒绝：`zs2.is_one_bi_zs()` 返回 False；两中枢首笔不同段（`begin_bi.seg_idx != zs2.begin_bi.seg_idx`）返回 False（跨段不合并）。
- `combine_mode == 'zs'`：仅当两中枢**区间 `[ZD,ZG]` 重叠**（`has_overlap(low,high, zs2.low,zs2.high, equal=True)`，含边界）才 `do_combine`。
- `combine_mode == 'peak'`：当两中枢**最宽极值 `[peak_low,peak_high]` 重叠**即合并（更激进，容易形成更大级别中枢）。
- 其他值抛 `CChanException(PARA_ERROR)`。

`do_combine(zs2)`：
- 首次合并时把自身副本 `make_copy()` 放进 `sub_zs_lst`，再 append `zs2`——从而 `sub_zs_lst` 记录“由哪些子中枢构成这个更大级别中枢”，`__str__` 输出形如 `begin->end(sub1,sub2)`。
- 扩张区间：`low=min`、`high=max`、`peak_low=min`、`peak_high=max`；并把末尾/出笔/末笔更新为 `zs2` 的对应值（合并后右端延伸到 zs2）。

`try_combine()` 用 while 循环持续把倒数第二个与最后一个合并，合并成功后删除最后一个，直到不再重叠。

### 4.5 中枢的“破坏/新生”与背驰判定

- `end_bi_break()`（`@make_cache`）：判 `bi_out` 是否真正突破中枢——向下笔且 `_low() < low`，或向上笔且 `_high() > high`。这是第18课“中枢破坏/离开”与第三类买卖点“离开中枢”的判据基础。
- `is_divergence(config: CPointConfig)`：先要求 `end_bi_break()`（不突破不谈背驰），再把比较委托给 `Common/FuncUtil.is_macd_divergence(bi_in, bi_out, macd_algo, divergence_rate, zs=self)`，返回 `(是否背驰, 比值)`。传 `zs=self` 是为了 `COMPOSITE_FULL` 口径能取中枢内部 KLU 做“黄白线回抽零轴”的形态门槛（对应第24/25课）。背驰的算法细节属于 `Math`/`BuySellPoint` 范畴，本模块只是发起比较的载体。
- `out_bi_is_peak()`（`@make_cache`）：返回 `(是否极端笔, 与中枢内最接近它的差距比例)`——遍历 `bi_lst`，若存在比 `bi_out` 更极端的笔则 False，否则 True 并算出最小差距率，供一类买卖点 `bs1_peak` 校验。
- `is_inside(seg)`：`seg.start_bi.idx <= begin_bi.idx <= seg.end_bi.idx`，用于把中枢归属到线段。

### 4.6 配置开关（ZSConfig.py + ChanConfig.py）

`CZSConfig(need_combine=True, zs_combine_mode="zs", one_bi_zs=False)`：

| 参数 | 默认值（ChanConfig） | 作用 |
| --- | --- | --- |
| `zs_combine` → `need_combine` | `True` | 是否执行相邻中枢扩张合并 |
| `zs_combine_mode` | `"zs"` | 合并判据口径：`"zs"`（区间[ZD,ZG]重叠，保守）/`"peak"`（极值重叠，激进） |
| `one_bi_zs` | `False` | 是否允许单笔即构成中枢 |

中枢回填（`bi_in/bi_out/bi_lst`）不发生在 ZS 内部，而是 `KLine/KLineList.py::update_zs_in_seg()`：`bi_in = bi_list[begin_bi.idx-1]`、`bi_out = bi_list[end_bi.idx+1]`（越界则不设）、`bi_lst = bi_list[begin_bi.idx : end_bi.idx+1]`。因此中枢对象一旦离群（首笔 idx=0）会 assert 失败，这也是“禁止第一笔成中枢起点”的另一重保障。

## 五、文件清单

| 文件 | 内容 |
| --- | --- |
| `ZS.py` | `CZS[LINE_TYPE]` 中枢对象：区间 `[ZD,ZG]`、极值 `[DD,GG]`、延伸、扩张合并、破坏判定、背驰入口 |
| `ZSConfig.py` | `CZSConfig`：`need_combine / zs_combine_mode / one_bi_zs` |
| `ZSList.py` | `CZSList`：由笔/段列表增量聚合中枢序列（`cal_bi_zs` 主入口、延伸、合并） |
| `__init__.py` | 空 |

## 六、与其他模块的协作

- **上游 `Bi`/`Seg`**：`CZS` 泛型消费 `CBi` 或 `CSeg`（`_low()/_high()/dir/idx/seg_idx/get_begin_klu()/get_end_klu()`）。
- **驱动方 `KLine/KLineList.py`**：`zs_list = CZSList(conf.zs_conf)`（笔中枢）、`segzs_list = CZSList(conf.zs_conf)`（段中枢）。`cal_seg_and_zs()` 依次调 `zs_list.cal_bi_zs(bi_list, seg_list)` → `update_zs_in_seg(...)`（回填 bi_in/bi_out/bi_lst 并把中枢归入段），再对段段做同样流程实现级别递归。
- **下游 `BuySellPoint`**：`CZS` 的 `low/high/peak_low/peak_high`、`bi_out`、`end_bi_break()`、`is_divergence()`、`out_bi_is_peak()`、`is_one_bi_zs()` 是三类买卖点（尤其第三类与背驰一类）的直接输入。
- **`Common.FuncUtil`**：`has_overlap`（延伸/合并判据）、`is_macd_divergence`（背驰）、`revert_bi_dir`（尾部虚段方向）。
- **`Math.MACD`**：背驰比较所需的每根 K 线 `macd`（`klu.macd`）由指标层逐 KLU 计算，ZS 只读取聚合。
