# Seg —— 线段划分（特征序列、两种情况与缺口处理）

## 一、模块定位

`Seg` 实现缠论中最难的形态学环节：**把笔（`CBi`）序列划分成线段（`CSeg`）**。线段是构成中枢与走势类型的最小标准部件，其划分质量直接决定上层所有结构。核心思想是缠师提出的**特征序列**：把与线段方向相反的笔当作"K 线"，对它做包含合并、识别分型，用分型是否成立以及**特征序列缺口**是否被封闭来判断线段是否被破坏。

本文件夹按职责分四层：

- **元素层**：`Eigen.py`（`CEigen`：特征序列元素，继承 `Combiner` 泛型合并器，把笔当 K 线）。
- **判据层**：`EigenFX.py`（`CEigenFX`：三元素滑动状态机，实现线段破坏的**第一种 / 第二种情况**与缺口递归）。
- **对象层**：`Seg.py`（`CSeg[LINE_TYPE]`：线段对象，泛型支持"线段的线段"级别递归）、`SegConfig.py`（`CSegConfig`：算法与剩余段处理开关）。
- **调度层**：`SegListComm.py`（`CSegListComm`：抽象基类 + 剩余笔/首段收尾逻辑）、`SegListChan.py`（`CSegListChan`：缠师原文严格特征序列算法）。

- 关键枚举：`SEG_TYPE{BI,SEG}`、`BI_DIR`、`FX_TYPE`、`KLINE_DIR`、`LEFT_SEG_METHOD{ALL,PEAK}`。

## 二、对应缠论课程

- **第 67 课《线段的划分标准》**：特征序列与标准特征序列的定义、缺口定义、线段破坏的**第一种 / 第二种情况**的原始精确表述（本层算法的源头）。
- **第 65 课《再说说分型、笔、线段》**：线段至少三笔、前三笔必须重叠、线段被笔破坏的记号定义、缠中说禅线段分解定理。
- **第 69 课《月线分段与上海大走势分析、预判》**：特征序列底/顶分型的取舍、第二种情况需第二特征序列有三元素。
- **第 71 课《线段划分标准的再分辨》**：特征序列元素方向与段相反、缺口封闭、第一/第二元素的界定、两种情况判定的标准。
- **第 77 课《一些概念的再分辨》**：线段笔数为单数、前三笔重合、线段必须被线段破坏、第二种情况的第二特征序列不再分两种情况（简化）。
- **第 78 课《继续说线段的划分》**：线段方向、古怪线段的成因、第二种情况里第二特征序列必须按包含关系处理、线段标准化（端点即最高/最低）。

> 第 67 课《线段的划分标准》（2007-08-01）是线段划分"两种情况"最早的精确出处；第 71 课开头缠师自述"虽然67课已经给出了线段划分的标准，但由于那里用的是比较抽象的类数学语言……逐一进行再分辨"。因此 67 与 71/77/78 是同一套判据的"原始表述 + 再分辨"关系，代码 `EigenFX.py` 即据此实现。

## 三、书中关键原文

> 有了笔，那么线段就很简单了，线段至少有三笔，线段无非有两种，从向上一笔开始的，和从向下一笔开始的。
>
> ——《教你炒股票65：再说说分型、笔、线段》

> 对于从向上一笔开始的，其中的分型构成这样的序列：d1g1d2g2d3g3…dngn（其中di代表第i个底，gi代表第i个顶）。如果找到i和j，j>=i+2，使得dj<=gi，那么称向上线段被笔破坏。
>
> ——《教你炒股票65：再说说分型、笔、线段》

> 缠中说禅线段分解定理：线段被破坏，当且仅当至少被有重叠部分的连续三笔的其中一笔破坏。而只要构成有重叠部分的前三笔，那么必然会形成一线段，换言之，线段破坏的充要条件，就是被另一个线段破坏。
>
> ——《教你炒股票65：再说说分型、笔、线段》

> 以向上笔开始的线段，可以用笔的序列表示：S1X1S2X2S3X3…SnXn。容易证明，任何Si与Si+1之间，一定有重合区间。而考察序列X1X2…Xn，该序列中，Xi与Xi+1之间并不一定有重合区间，因此，这序列更能代表线段的性质。
>
> ——《教你炒股票67：线段的划分标准》

> 定义：序列X1X2…Xn成为以向上笔开始线段的特征序列；序列S1S2…Sn成为以向下笔开始线段的特征序列。特征序列两相邻元素间没有重合区间，称为该序列的一个缺口。
>
> ——《教你炒股票67：线段的划分标准》

> 关于特征序列，把每一元素看成是一K线，那么，如同一般K线图中找分型的方法，也存在所谓的包含关系，也可以对此进行非包含处理。经过非包含处理的特征序列，成为标准特征序列。以后没有特别说明，特征序列都是指标准特征序列。
>
> ——《教你炒股票67：线段的划分标准》

> 参照一般K线图关于顶分型与底分型的定义，可以确定特征序列的顶和底。注意，以向上笔开始的线段的特征序列，只考察顶分型；以向下笔开始的线段，只考察底分型。
>
> ——《教你炒股票67：线段的划分标准》

> 第一种情况：特征序列的顶分型中，第一和第二元素间不存在特征序列的缺口，那么该线段在该顶分型的高点处结束，该高点是该线段的终点；特征序列的底分型中，第一和第二元素间不存在特征序列的缺口，那么该线段在该底分型的低点处结束，该低点是该线段的终点；
>
> ——《教你炒股票67：线段的划分标准》

> 第二种情况：特征序列的顶分型中，第一和第二元素间存在特征序列的缺口，如果从该分型最高点开始的向下一笔开始的序列的特征序列出现底分型，那么该线段在该顶分型的高点处结束，该高点是该线段的终点；特征序列的底分型中，第一和第二元素间存在特征序列的缺口，如果从该分型最低点开始的向上一笔开始的序列的特征序列出现顶分型，那么该线段在该底分型的低点处结束，该低点是该线段的终点；
>
> ——《教你炒股票67：线段的划分标准》

> 强调，在第二种情况下，后一特征序列不一定封闭前一特征序列相应的缺口，而且，第二个序列中的分型，不分第一二种情况，只要有分型就可以。
>
> ——《教你炒股票67：线段的划分标准》

> 上面两种情况，就给出所有线段划分的标准。显然，出现特征序列的分型，是线段结束的前提条件。本课，就是把前面"线段破坏的充要条件就是被另一个线段破坏"精确化了。因此，以后关于线段的划分，都以此精确的定义为基础。
>
> ——《教你炒股票67：线段的划分标准》

> 显然，特征序列的元素的方向，和其对应的段的方向是刚好相反的，例如，一个向上段后接着一个向下段，前者的特征序列元素是向下的，后者是向上的，因此，根本也不可能存在包含的可能。
>
> ——《教你炒股票71：线段划分标准的再分辨》

> 这里的逻辑关系很明确的，线段要被笔破坏，那么必须其最后一个特征序列的缺口被封闭，否则就不存在被笔破坏的情况。
>
> ——《教你炒股票71：线段划分标准的再分辨》

> 在67课里，把线段的划分分为两种情况，显然，分清楚是哪种情况，对划分线段十分关键。……判断的标准只有一个，就是特征序列的分型中，第一和第二元素间不存在特征序列的缺口。
>
> ——《教你炒股票71：线段划分标准的再分辨》

> 特征序列的分型中，第一元素就是以该假设转折点前线段的最后一个特征元素，第二个元素，就是从这转折点开始的第一笔，显然，这两者之间是同方向的，因此，如果这两者之间有缺口，那么就是第二种情况，否则就是第一种，然后根据定义来考察就可以。
>
> ——《教你炒股票71：线段划分标准的再分辨》

> 线段划分的最基本原则，就是线段必须至少有三笔……由此可见，线段中包含笔的数目，都是单数的。
>
> ——《教你炒股票77：一些概念的再分辨》

> 而且，线段开始的那三笔，必须有重合，开始三笔没有重合的，是构不成线段的。
>
> ——《教你炒股票77：一些概念的再分辨》

> 各位肯定注意，在第二种情况下特别强调，第二特征序列，其实就是对应着线段C对线段B的破坏，不再分第一、二种情况了。这，其实是一个简化的方法。
>
> ——《教你炒股票77：一些概念的再分辨》

> 线段和笔，都是有方向的，从顶开始的笔一定结束在底，同样，以向上笔开始的线段一定结束于向上笔……一个线段，不可能是从底到底或从顶到顶，这是一个最基本的概念。
>
> ——《教你炒股票78：继续说线段的划分》

> 一定要注意，对于第二种情况的第二特征序列的分型判断，必须严格按照包含关系的处理来，这里不存在第一种情况中的假设分界点两边不能进行包含关系处理的要求。
>
> ——《教你炒股票78：继续说线段的划分》

> 经过标准化处理后，所有向上线段都是以最低点开始最高点结束，向下线段都是以最高点开始最低点结束，这样，所以线段的连接，就形成一条延续不断、首尾相连的折线……
>
> ——《教你炒股票78：继续说线段的划分》

> 其实，如果第二特征序列没有三个元素，就根本不存在出现分段中第二种情况的可能
>
> ——《教你炒股票69：月线分段与上海大走势分析、预判》（缠姐回复）

## 四、实现思路

### 4.1 `CEigen`（Eigen.py）—— 特征序列元素

`CEigen(CKLine_Combiner[CBi])` 是**把笔当 K 线的合并元素**：直接复用 `Combiner` 的 `try_add` 做包含合并。构造时额外初始化 `self.gap = False`。

- **覆写 `update_fx`**：先调父类算出标准顶/底分型，再补一条缺口标记——
  ```
  (fx==TOP and _pre.high < self.low) or (fx==BOTTOM and _pre.low > self.high) → gap=True
  ```
  即"分型第一元素的极值与第二元素之间存在跳空"。这正是第 71 课"第一和第二元素间存在特征序列缺口"→ 第二种情况的关键判据。
- `GetPeakBiIdx()`：把分型峰值所在的原始 K 线（实为笔）映射回笔索引。注意 `idx-1`：上升笔序列对应下降线段，取低点笔再退一格作为线段端点笔。
- 只被 `CEigenFX` 使用。

### 4.2 `CEigenFX`（EigenFX.py）—— 三元素滑动状态机（最难部分）

这是缠师原文"线段破坏两种情况"的严格实现。状态：`ele[0..2]` 三个 `CEigen`、`lst`（已喂入的笔）、`last_evidence_bi`（第二种情况递归时的取证笔）。

**`add(bi)`**：入口，先 `assert bi.dir != self.dir`——特征序列由**与线段方向相反**的笔构成（第 71 课对应）。按 `ele[0]/[1]/[2]` 是否为空分派到 `treat_first/second/third_ele`；三元素都还在却又来新笔抛 `SEG_EIGEN_ERR`。

**`treat_second_ele`**：把 `bi` 试加到 `ele[0]`，能合并就合并；不能则建 `ele[1]`。若"前两元素不可能成为分型"（上升段中 `ele[1].high < ele[0].high` 等反向关系）→ `reset()` 滑动窗口。

**`treat_third_ele`**：`allow_top_equal`（下降段给 1、上升段给 -1，仅在 `exclude_included` 时启用，见第 78 课"第二种情况的第二特征序列必须按包含关系处理"）。把 `bi` 试加 `ele[1]`：
- 先过 `actual_break()`（第三元素必须**实际突破**第二元素极值，否则 `reset`）；
- 建 `ele[2]` 后调 `ele[1].update_fx(ele[0], ele[2], ...)` 判定分型；
- `is_up` 段要出现 TOP、`is_down` 段要出现 BOTTOM 才算成，否则 `reset`。

**`actual_break()`**：`exclude_included=False`（普通规则）恒真；否则要求 `ele[2]` 的低（高）实际跌破 `ele[1]` 最后一笔的高（低）。若没有，退而看 `ele[2][0].next.next` 是否突破，作为 `last_evidence_bi` 取证。防止第二元素因合并抬高/压低门槛后误判"突破"。

**`can_be_end(bi_lst)` —— 第一种 vs 第二种情况的分岔**（核心）：
- `ele[1].gap == False` → **第一种情况**：直接 `return True`（分型成立即线段破坏）；
- `ele[1].gap == True` → **第二种情况**：`find_revert_fx(...)` 递归寻找反向特征序列分型。取 `end_bi_idx=GetPeakBiIdx()`，`thred_value`（需突破的阈值 = 该端笔端点值）、`break_thred`（第一元素极值）。

**`find_revert_fx(bi_list, begin_idx, thred_value, break_thred)`**：从 `end_bi_idx+2` 起，用方向相反的 `CEigenFX` 每隔一笔（`[begin_idx::2]`）喂入找反向分型；
- `COMMON_COMBINE=True` 时找到分型即 `return True`；
- 每步先检查价格是否已突破 `thred_value`（若先破阈值 → `return False`，判未破坏）；
- 检查 `ele[1]` 是否越过 `break_thred`（越过 → `return True`）；
- 遍历到列表尾仍未找到 → `return None`（调用方视同"正常结束"处理）。
这对应第 77 课"第二种情况的第二特征序列不再分第一、二种情况"的简化。

**`reset()`**：滑动窗口前移一格。`exclude_included=True` 时清空重建（重走普通合并），`False` 时把 `ele[1]/[2]` 前移、保留从第二元素起的笔。

**`all_bi_is_sure()`**：只要 `lst` 中有任一笔非确定、或取证笔非确定，就返回 `False`——用于门控线段是否可标 `is_sure`。

### 4.3 `CSeg`（Seg.py）—— 线段对象

**泛型 `CSeg[LINE_TYPE]`**：`LINE_TYPE=CBi` 是普通线段，`LINE_TYPE=CSeg` 即"线段的线段"（父级别，服务级别递归），靠 `seg_idx/parent_seg` 表达层次。

- 构造断言：非首段时 `start_bi.dir == end_bi.dir`（第 78 课"线段不可能从底到底/从顶到顶"）。`end_bi.idx - start_bi.idx < 2`（不足三笔）→ 自动置 `is_sure=False`。
- `check()`：确定线段须满足"下降段起点高于终点、上升段起点低于终点"（`SEG_END_VALUE_ERR`，第 78 课"顶肯定高于底"）与长度 `>=2`（`SEG_LEN_ERR`）。
- `_high/_low/get_begin_val/get_end_val/get_begin_klu/get_end_klu/amp/cal_bi_cnt/get_klu_cnt`：几何度量；`cal_klu_slope/cal_amp/cal_macd_metric`（仅 `SLOPE/AMP`）供线段级背驰。
- `zs_lst`（线段内中枢）+ `add_zs/clear_zs_lst`；`get_first_multi_bi_zs/get_final_multi_bi_zs/get_multi_bi_zs_cnt` 取"多笔中枢"数——走势类型（趋势需 ≥2 中枢）判定基础。
- `update_bi_list(bi_lst, idx1, idx2)`：回填段内每笔的 `parent_seg`，≥3 笔时构建 `CTrendLine`（趋势线）。

### 4.4 `CSegConfig`（SegConfig.py）—— 两个开关

| 参数 | 默认 | 作用 |
|------|------|------|
| `seg_algo` | `"chan"` | 目前仅 `chan`=`CSegListChan`（原文特征序列算法）。由 `KLine.KLineList.get_seglist_instance` 路由 |
| `left_method` | `"peak"` | `peak`=`LEFT_SEG_METHOD.PEAK`（剩余笔找极值分段）；`all`=`ALL`（尾部一笔到底，注释警告"容易找不到二类买卖点"）。在 `SegListComm.collect_first_seg/collect_segs` 使用 |

> **两个不同的"缺口"**：`gap_as_kl` 不是 `Seg` 的配置项，它定义在 `Bi.BiConfig`，作用是把笔跨度里的价格缺口当作一根额外 K 线来算 `get_klc_span`（详见 `Bi/README.md`）。`Seg` 层处理的是特征序列缺口（`CEigen.gap` + `EigenFX.can_be_end/find_revert_fx` 的第一/第二种情况），源自第 71/77/78 课，与 `gap_as_kl` 属于不同层次的"缺口"概念。`Seg` 自身的开关只有上表两项。

### 4.5 `CSegListComm`（SegListComm.py）—— 抽象基类与收尾逻辑

持有 `lst: List[CSeg]`，`lv` 区分 BI/SEG 级。`update()` 为抽象方法。核心是**处理"剩余未成段"的尾部笔**：

- `do_init()`：基类清空 `lst`（`Chan` 版覆写为"回滚末尾未确定线段"，见下）。
- `try_add_new_seg / add_new_seg`：追加线段并连 `pre/next`、`update_bi_list`；首段有 `split_first_seg` 逻辑（在极值处把过头的第一段拆成两段）；`add_new_seg` 捕获首段 `SEG_END_VALUE_ERR` 返回 `False`（防止首段方向与端点值矛盾）。
- `collect_left_seg` → 无段时 `collect_first_seg`、有段时 `collect_segs`：
  - `collect_first_seg`：`peak` 法比较首笔到全局最高/最低的偏离，选极值笔处切第一段（`reason=0seg_find_high/low`）；`all` 法按首尾值定方向一笔到底。
  - `collect_segs`：末确定段之后若尾部笔"突破"末笔极值，`FindPeakBi` 找极值补切虚段（`collectleft_find_high_force` 等）；否则按 `left_method` 收尾。
- `left_bi_break`：判断最后确定线段之后的笔是否突破其末笔（`DYH/Def` 用）。
- `FindPeakBi(bi_lst, is_high)`：模块级函数，扫描方向一致、且不被"隔一笔的同向笔"支配的极值笔（`bi.pre.pre` 比较用于跳过假极值）。

### 4.6 `CSegListChan`（SegListChan.py）—— 默认严格算法

`CSegListComm` 子类，缠师原文实现：

- `do_init()`：`while` 删除末尾所有 `is_sure=False` 的线段；若最后确定段的分型第三元素内含未确定笔，也要删（否则高低点会错）——这是逐根回放能收敛正确结果的关键回滚。
- `update(bi_lst)`：`do_init` 回滚 → `cal_seg_sure`（从 `self[-1].end_bi.idx+1` 续算）→ `collect_left_seg` 收尾。
- `cal_seg_sure(bi_lst, begin_idx)`：**两个并行状态机** `up_eigen`（吃下降笔判上升线段终结）与 `down_eigen`（吃上升笔），逐笔 `add`，一旦某方出现分型（`fx_eigen`）就 `treat_fx_eigen` 并 `break`。
  - **首段方向特殊判定**（`len(self)==0`）：不以"谁先成分型"定方向（注释举反例 `US.EVRG`），而是看 `up_eigen.ele[1]`/`down_eigen.ele[1]` 是否成形，配合回退 `last_seg_dir`。
- `treat_fx_eigen`：`can_be_end()` 返回 `True/None` → 在 `GetPeakBiIdx()` 处 `add_new_seg`（`is_sure` 由是否 `None` 结束 + `all_bi_is_sure` 共同决定），成功后继续从 `end_bi_idx+1` 递归 `cal_seg_sure`；返回 `False`（未破坏）则从 `fx_eigen.lst[1].idx` 重试。线段把 `eigen_fx` 存起来供 `do_init` 回滚校验。

### 4.7 级别递归的接线

`CKLine_List` 同时持有 `seg_list`（`lv=SEG_TYPE.BI`，输入是笔）与 `segseg_list`（`lv=SEG_TYPE.SEG`，输入是线段）。`KLineList.cal_seg_and_zs` 先 `cal_seg(bi_list, seg_list)`，再 `cal_seg(seg_list, segseg_list)`——同一套 `CSegListChan` 泛型复用，实现第 65/18 课"把线段当笔再算一段"的递归。`CSeg` 的 `_high/_low` 会被 `CCombine_Item` 读取以参与上一层合并。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `Eigen.py` | `CEigen`：特征序列元素，继承 `CKLine_Combiner[CBi]`，补 `gap` 标记与 `GetPeakBiIdx` |
| `EigenFX.py` | `CEigenFX`：三元素状态机——第一/第二种情况、`actual_break`、`find_revert_fx` 缺口递归 |
| `Seg.py` | `CSeg[LINE_TYPE]`：线段对象（方向/校验/度量/中枢挂载/趋势线），泛型支持级别递归 |
| `SegConfig.py` | `CSegConfig`：`seg_algo`、`left_method` 开关 |
| `SegListComm.py` | `CSegListComm`：抽象基类 + 首段/剩余段收尾 + `FindPeakBi` |
| `SegListChan.py` | `CSegListChan`：**默认**，缠师原文特征序列算法（双状态机 + 回滚） |

## 六、与其他模块的协作

- **上游 `Bi`**：`bi_list` 是线段算法输入；`CEigen` 把笔当 K 线合并，`CCombine_Item` 读 `CBi._high/_low/idx`。
- **上游 `Combiner`**：`CEigen` 直接继承 `CKLine_Combiner`，复用 `try_add/update_fx`。
- **下游 `ZS`**：`CKLine_List.cal_seg` 后把线段归属回填给每笔（`set_seg_idx`）；`update_zs_in_seg` 给线段挂 `zs_lst`、给中枢设 `bi_in/bi_out`。走势类型（`Seg.get_multi_bi_zs_cnt`）依赖线段内中枢。
- **下游 `BuySellPoint`**：段级买卖点 `seg_bs_point_lst` 先算、笔级后算；`CSeg` 的力度度量（`cal_macd_metric`/`cal_amp`）用于段级背驰比较。
- 配置总闸在 `ChanConfig.py`（`seg_algo`、`left_seg_method`），逐根回放的驱动在 `KLine.KLineList.add_single_klu / cal_seg_and_zs`。
