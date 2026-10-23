# BuySellPoint —— 三类买卖点计算（BSPoint）

## 一、模块定位

`BuySellPoint` 实现缠论操作体系的核心输出——**第一、二、三类买卖点**（买点/卖点共用一套逻辑，靠方向翻转）。它消费 `ZS` 产出的中枢序列与 `Seg` 产出的线段序列，在“中枢 + 背驰 + 突破回抽”三要素之上定位可操作的转折点：

- **第一类买卖点（T1）**：趋势背驰点（>=2 同向中枢，进/出中枢笔力度衰减）。
- **盘整背驰一类（T1P）**：单中枢的盘整背驰点（比较末两同向笔力度）。
- **第二类买卖点（T2）/ 类二（T2S）**：一类出现后次级别回抽/反弹不创新极值的点。
- **第三类买卖点（T3A / T3B）**：中枢突破后次级别回抽不回到中枢（趋势确认）；按中枢在一类的前后分成 3a/3b。

文件：`BSPoint.py`（单个买卖点对象）、`BSPointConfig.py`（买/卖、笔/段四套配置 + `CPointConfig`）、`BSPointList.py`（三类买卖点计算流水线）、`__init__.py`（空）。

## 二、对应缠论课程

| 课号 | 标题 | 本模块对应的实现点 |
| --- | --- | --- |
| 17 | 走势终完美 | 一、二类买卖点的逻辑起源（第一类=下跌转化关节点，第二类=第一次次级别回调低点） |
| 20 | 走势中枢级别扩张及第三类买卖点 | 第三类买卖点判据（回抽不跌破 ZG / 不升破 ZD） |
| 21 | 缠中说禅买卖点分析的完备性 | 三类买卖点与中枢的对应关系、完备性定理 |
| 53 | 三类买卖点的再分辨 | 一类=背驰点、二类定义（不创新高/盘整背驰）、背驰 vs 盘整背驰 |
| 101 | 答疑1（第二类买卖点与走势必完美） | 第二类买点的三种情形、第二/三类合一、走势必完美（唯一分解） |

## 三、书中关键原文

> “一旦能把握下跌走势转化的关节点买入，就在市场中占据了一个最有利的位置，而这个买点，就是前面反复强调的“第一类买点”；……所以在第一类买点出现后第一次次级别回调制造的低点，是市场中第二有利的位置……这，就是在前面反复强调的第二类买点。”

——《教你炒股票17：走势终完美》

> “因此，只有在下跌确立后的中枢下方才可能出现买点。这就是第一类买点。”

> “而中枢扩张或新生，在中枢之上都会存在买点，这类买点，就是第三类买点。也就是说，第三类买点是中枢扩张或新生产生的。中枢扩张导致一个更大级别的中枢，而中枢新生，就形成一个上涨的趋势，这就是第三类买点后必然出现的两种情况。”

> “第二类买点是和第一类买点紧密相连的，因为出现第一类买点后，必然只会出现盘整与上涨的走势类型，而第一买点出现后的第二段次级别走势低点就构成第二类买点，根据走势必完美的原则，其后必然有第三段向上的次级别走势出现，因此该买点也是绝对安全的。”

> “缠中说禅买卖点的完备性定理：市场必然产生赢利的买卖点，只有第一、二、三类。”

——《教你炒股票21：缠中说禅买卖点分析的完备性》

> “一个次级别走势类型向上离开缠中说禅走势中枢，然后以一个次级别走势类型回试，其低点不跌破ZG，则构成第三类买点；一个次级别走势类型向下离开缠中说禅走势中枢，然后以一个次级别走势类型回抽，其高点不升破ZD，则构成第三类卖点。”

——《教你炒股票20：缠中说禅走势中枢级别扩张及第三类买卖点》

> “第一类买卖点，就是该级别的背驰点……一般说，高点一次级别向下后一次级别向上，如果不创新高或盘整背驰，都构成第二类卖点，而买点的情况反过来就是了。”

> “其次，对于背驰与盘整背驰，前者是有着最基础意义的，而后者，只是利用前者相应的力度分析方法进行的一个推广用法，主要用在与中枢震荡相关的力度比较中。”

——《教你炒股票53：三类买卖点的再分辨》

> “第一类买卖点就是背驰点，第三类买卖点就是中枢破坏点，这都是很清楚的。”

> “其实，所谓第二类买点，就是第一类买点的次级别回抽结束后再次探底或回试的那个次级别走势的结束点。”

> “一、最强的情况　第二类买点刚好构成原来下跌的最后一个中枢开始的震荡走势的第三类买点，也就是第二、三类买点合一了，这是最强的走势……二、最弱的情况　第二类买点跌破第一类买点，也就是第二类买点比第一类买点低，这是完全可以的，这里一般都构成盘整背驰”

> “所谓走势必完美，就是本ID所给出的分型、笔、线段、不同级别走势类型所对应的递归函数，能将行情的任何走势唯一地分解。”

——《教你炒股票101：答疑1》

## 四、实现思路

### 4.1 买卖点类型枚举与对象（BSPoint.py）

`Common.CEnum.BSP_TYPE`（字符串值）：

| 枚举 | value | 含义 |
| --- | --- | --- |
| `T1` | `'1'` | 趋势背驰第一类买卖点 |
| `T1P` | `'1p'` | 盘整背驰第一类（单中枢） |
| `T2` | `'2'` | 第二类买卖点 |
| `T2S` | `'2s'` | 类第二类（2 之后的同向续集） |
| `T3A` | `'3a'` | 第三类，中枢在一类**后面** |
| `T3B` | `'3b'` | 第三类，中枢在一类**前面** |

`CBS_Point[LINE_TYPE]`（`LINE_TYPE = CBi | CSeg`）记录：
- `bi`：触发笔/段；构造时即 `self.bi.bsp = self`（反向把自己挂回笔，便于从笔查买卖点）。
- `klu = bi.get_end_klu()`：定位点。
- `is_buy`：买/卖（`is_buy = bi.is_down()`，向下笔末端为买点）。
- `type: List[BSP_TYPE]`：**一个点可同时具备多类型**（原文第101课“第二、三类合一”），故用列表。
- `relate_bsp1`：该 2/3 类所依赖的一类买卖点（回指）。
- `is_segbsp`：是否段级买卖点标记（默认 False）。

`add_type()` / `add_another_bsp_prop()`：在同一 KLU 上追加类型并合并 `relate_bsp1`（若已有则 assert 两者 klu.idx 相同）。`type2str()` 输出如 `"2,3a"`。

### 4.2 配置体系（BSPointConfig.py）

`CBSPointConfig` 内部持有 **`b_conf`（买）与 `s_conf`（卖）两套 `CPointConfig`**；`GetBSConfig(is_buy)` 返回对应套。`ChanConfig` 还会派生 `bs_point_conf`（笔级买卖点）与 `seg_bs_point_conf`（段级买卖点），共四套配置。段级默认覆写：`macd_algo="slope"`（段用价格斜率而非 MACD 面积）、`bsp1_only_multibi_zs=False`。

`CPointConfig` 关键参数（默认值取自 `ChanConfig.set_bsp_config` 的 `para_dict`）：

| 参数 | 默认 | 语义 |
| --- | --- | --- |
| `divergence_rate` | `inf`（`DEFAULT_ALGO_CONFIG` 常另设 0.9） | 背驰阈值，`out <= rate*in` 即背驰；`>100` 保送（调试强判背驰） |
| `min_zs_cnt` | `1` | 趋势一类所需最少中枢数（`<=0` 关闭门控） |
| `bsp1_only_multibi_zs` | `True` | 一类只数“多笔中枢”（`get_multi_bi_zs_cnt`）还是全部中枢 |
| `max_bs2_rate` | `0.9999` | 二类回抽幅度上限，`assert <= 1` |
| `macd_algo` | `"composite_full"` | 背驰口径（见 `Math`），映射到 `MACD_ALGO` |
| `bs1_peak` | `True` | 一类要求出笔是中枢内最极端（`out_bi_is_peak`） |
| `bs_type` | `"1,1p,2,2s,3a,3b"` | 目标输出类型白名单，`parse_target_type()` 解析为 `target_types` |
| `bsp2_follow_1` | `True` | 二类必须紧跟一类（`bsp1_bi_idx in bsp1_bi_idx_dict`） |
| `bsp3_follow_1` | `True` | 三类必须有一类在前 |
| `bsp3_peak` | `False` | 三类突破需是中枢最极端突破 |
| `bsp2s_follow_2` | `False` | 类二必须在合法二类之后 |
| `max_bsp2s_lv` | `None` | 类二最多延伸层数 |
| `strict_bsp3` | `False` | 严格三类：中枢必须直接接在一类之后 |

配置注入通过 `set(k,v)`（`exec` 动态赋值 + `_parse_inf` 处理无穷值）；`ChanConfig` 支持 `-buy/-sell/-seg/-segbuy/-segsell` 后缀对四套分别覆写，未知键抛 `CChanException(PARA_ERROR)`。

### 4.3 计算流水线 `CBSPointList.cal()`（BSPointList.py）

`CBSPointList[LINE_TYPE, LINE_LIST_TYPE]`（`LINE_LIST_TYPE = CBiList | CSegListComm`）泛型，笔级与段级复用同一套代码。成员：`lst`（输出买卖点）、`bsp1_lst`（所有一类池，供 2/3 类回指）、`last_sure_pos`（增量锚点）。

`cal(bi_list, seg_list)` 分步：
1. **增量清理**：`lst`/`bsp1_lst` 只保留 `klu.idx <= last_sure_pos` 的旧点（已坐实部分不重算）。
2. 依次 `cal_seg_bs1point → cal_seg_bs2point → cal_seg_bs3point`（**必须 T1 先行**，因为 T2/T3 依赖 `bsp1_bi_idx_dict`）。
3. `update_last_pos(seg_list)`：把 `last_sure_pos` 刷新为最后一个已坐实段的**起始** KLU idx（用起始是因为本次计算最后一个段可能刚生成，需重算）。

`seg_need_cal(seg)`：段末 klu.idx > last_sure_pos 才需要计算（增量效率核心）。

`add_bs(bs_type, bi, relate_bsp1, is_target_bsp=True)`：
- 先按 klu 去重——若同点已存在，则 `add_another_bsp_prop`（合并类型，实现“一点多类型”）。
- 若 `bs_type` 不在目标白名单 → `is_target_bsp=False`。
- 仅当 `is_target_bsp` 或属于 T1/T1P 时才真正建对象；**非目标类型只有 T1/T1P 会被保留**（因为它们是 2/3 类回指的锚），其余直接丢弃。
- T1/T1P 额外 append 进 `bsp1_lst`。

### 4.4 第一类买卖点（趋势 T1 与盘整 T1P）

`cal_single_bs1point(seg, bi_list)`：
- 计算 `zs_cnt = get_multi_bi_zs_cnt() if bsp1_only_multibi_zs else len(zs_lst)`；`is_target_bsp = (min_zs_cnt<=0 or zs_cnt >= min_zs_cnt)`——**这是原文“趋势须 >=2 中枢”的门控实现**。
- 分支：末中枢存在、非一笔中枢、且末中枢的 `bi_out.idx == seg.end_bi.idx` → 走 `treat_bsp1`（趋势一类）；否则走 `treat_pz_bsp1`（盘整一类）。

`treat_bsp1`：
- `break_peak, _ = last_zs.out_bi_is_peak()`（注释指出 False 仅在线段第一笔直接拉得很低时出现）；
- `if bs1_peak and not break_peak: is_target_bsp = False`；
- `is_diver, _ = last_zs.is_divergence(BSP_CONF)`（进/出中枢笔 MACD 力度比较）；不背驰 → 非目标；
- `add_bs(T1, bi=last_zs.bi_out, ...)`。对应“第一类=背驰点/下跌转化关节点”。

`treat_pz_bsp1`（盘整背驰 → T1P，单中枢情形）：
- 取 `last_bi = seg.end_bi`、`pre_bi = bi_list[last_bi.idx-2]`（同向的前一笔）；
- 校验同段、同向（尾虚段方向可能不同则 return）；
- **创新极值门控**：向下笔若 `last_bi._low() > pre_bi._low()`（未创新低）return；向上笔若 `_high() < pre_bi._high()`（未创新高）return——即盘整一类必须比参照笔更极端；
- `is_macd_divergence(pre_bi, last_bi, macd_algo, divergence_rate)` 判背驰，不背驰则非目标；
- `add_bs(T1P, bi=last_bi, ...)`。对应第53课“盘整背驰”（背驰力度法的推广）。

### 4.5 第二类买卖点（T2 与类二 T2S）

`treat_bsp2(seg, ...)`：以一类所在段为基准：
- 多段情形：`bsp1_bi = seg.end_bi`（一类笔），`real_bsp1 = bsp1_bi_idx_dict.get(bsp1_bi.idx)`（回指的一类对象），`break_bi = bi_list[bsp1_bi.idx+1]`（突破笔），`bsp2_bi = bi_list[bsp1_bi.idx+2]`（回抽笔，即二类笔）。
- 单段情形：`bsp2_bi = bi_list[1]`、`break_bi = bi_list[0]`，无一类。
- `bsp2_follow_1` 门控：若开启且一类不在字典中，则 T2/T2S 都不算。
- **回抽幅度判据**：`retrace_rate = bsp2_bi.amp() / break_bi.amp()`，`bsp2_flag = retrace_rate <= max_bs2_rate`。由于 `max_bs2_rate<=1`（默认 0.9999），回抽幅度不超过突破幅度即“不创新极值” → `add_bs(T2, bsp2_bi, real_bsp1)`；否则若 `bsp2s_follow_2` 则不继续找类二。
- 之后进入 `treat_bsp2s`。

`treat_bsp2s(...)`：从 `bias=2` 起循环找“类二”（二类之后的同向续集）：
- `bsp2s_bi = bi_list[bsp2_bi.idx+bias]`；`max_bsp2s_lv` 限制 `bias/2` 层数；
- 跨段约束：`bsp2s_bi.seg_idx != bsp2_bi.seg_idx` 且（非最后两段 或 二类段已坐实）则 break；
- `bias==2` 时要求二类与首个类二**区间重叠**，并取交集 `[_low,_high]`；后续要求继续与交集重叠；
- `bsp2s_break_bsp1(bsp2s_bi, break_bi)`（类二突破二类突破笔极值）→ break；
- `retrace_rate = abs(bsp2s_bi.get_end_val()-break_bi.get_end_val())/break_bi.amp() > max_bs2_rate` → break；
- 否则 `add_bs(T2S, bsp2s_bi, real_bsp1)` 并 `bias += 2`。

对应第101课：二类是“一类次级别回抽结束后再次探底的结束点”，且“二类可能跌破一类（最弱，构成盘整背驰）”由 `max_bs2_rate<1` 与类二重叠逻辑共同刻画。

### 4.6 第三类买卖点（T3A 与 T3B）

核心判据（`bsp3_back2zs`）：`bsp3_bi` 回抽是否“回到中枢”——向下笔 `_low() < zs.high` 或向上笔 `_high() > zs.low` 即视为回到中枢（不成立三类）。等价于原文“低点不跌破 ZG / 高点不升破 ZD”（注意 `zs.high=ZG`、`zs.low=ZD`）。

`cal_seg_bs3point(seg_list, bi_list)`：同样以“一类所在段”为基准，取 `next_seg`（`seg.next`，可能 None）；`bsp3_follow_1` 门控；有 `next_seg` 则 `treat_bsp3_after`，随后再 `treat_bsp3_before`。

`treat_bsp3_after`（**T3A**，中枢在一类之后）：
- `first_zs = next_seg.get_first_multi_bi_zs()`，无则 return；
- `strict_bsp3` 要求 `first_zs.get_bi_in().idx == bsp1_bi_idx+1`（中枢必须直接接一类）；
- `bsp3_bi = bi_list[first_zs.bi_out.idx+1]`（突破中枢后的次级别回抽笔）；跨段且非末段则 return；
- `if bsp3_back2zs(bsp3_bi, first_zs): return`（回抽回到中枢 → 不是三类）；
- `bsp3_peak` 要求 `bsp3_break_zspeak(bsp3_bi, zs)`（突破笔须超越中枢极值 `peak_high/peak_low`）；
- `add_bs(T3A, bsp3_bi, real_bsp1)`。

`treat_bsp3_before`（**T3B**，中枢在一类之前）：
- `cmp_zs = seg.get_final_multi_bi_zs()`，无则 return；必须存在 `bsp1_bi`；
- `strict_bsp3` 要求 `cmp_zs.bi_out.idx == bsp1_bi.idx`；
- 遍历 `bi_list[bsp1_bi.idx+2 :: 2]` 至 `cal_bsp3_bi_end_idx(next_seg)`（一类后第一个中枢的 bi_out 位置），逐笔判 `bsp3_back2zs`，第一个不回到中枢者记 `add_bs(T3B, ...)` 后 break。

`cal_bsp3_bi_end_idx` 处理尾虚段只有一笔、或 next 段多笔中枢尚未形成等边界（返回 `inf` 表示不提前截断）。

### 4.7 边界与坑

- **T2/T3 依赖 T1**：`bsp1_lst` 必须先于 2/3 类构建，流水线顺序不可乱。
- **一点多类型**：同 KLU 会被 `add_bs` 合并到同一 `CBS_Point.type`（实现第101课“第二、三类合一”）。
- **非目标类型仍保留 T1/T1P**：即使 `bs_type` 白名单里没有 1/1p，一类点仍进 `lst`+`bsp1_lst`，以充当回指锚点。
- **增量重算锚点用段“起始” idx**：因本次计算末段可能刚生成，若用末段结束 idx 会漏算，故 `update_last_pos` 特意取 `seg.end_bi.get_begin_klu().idx`。
- **笔级 vs 段级**：段级把 `macd_algo` 改为 `slope`、`bsp1_only_multibi_zs` 关闭，反映“段用价格斜率/振幅而非笔内 MACD 面积”的口径差异。

## 五、文件清单

| 文件 | 内容 |
| --- | --- |
| `BSPoint.py` | `CBS_Point[LINE_TYPE]`：单买卖点对象（type 列表、relate_bsp1、回挂 bi.bsp） |
| `BSPointConfig.py` | `CBSPointConfig`（买/卖双配置）、`CPointConfig`（全部背驰/二类/三类开关）、macd_algo 映射 |
| `BSPointList.py` | `CBSPointList`：`cal()` 流水线，T1/T1P、T2/T2S、T3A/T3B 的完整计算与辅助函数 |
| `__init__.py` | 空 |

## 六、与其他模块的协作

- **驱动方 `KLine/KLineList.py`**：`bs_point_lst = CBSPointList[CBi,CBiList](conf.bs_point_conf)`、`seg_bs_point_lst = CBSPointList[CSeg,CSegListComm](conf.seg_bs_point_conf)`，在段/中枢算完后调 `.cal(bi_list, seg_list)`。
- **依赖 `ZS`**：通过 `seg.zs_lst`、`CZS.bi_out/is_divergence/out_bi_is_peak/low/high/peak_*` 定位中枢与背驰。
- **依赖 `Seg`**：`seg.get_multi_bi_zs_cnt()/get_first_multi_bi_zs()/get_final_multi_bi_zs()/end_bi/is_sure/next` 等。
- **依赖 `Bi`**：笔的 `amp()/_low()/_high()/get_end_val()/dir/seg_idx/bsp`。
- **依赖 `Common.FuncUtil.is_macd_divergence` / `has_overlap`**：一类背驰与类二重叠判定统一走指标层。
- **下游 `Strategy`/`Trade`/`Plot`**：`getLastestBspList()`、`type2str()`、`is_buy` 供选股/回测/绘图消费。
