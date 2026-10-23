# Trend —— 走势分析与十层交易纪律

缠论原典只给出概念、定理与操作原理，没有可编程的阈值、加权系数或开关名。下文凡涉及阈值、比例、开关、降级策略，都是本框架把这些概念操作化后的工程实现，不等同于原文表述。

---

## 一、模块定位

`Trend` 是全仓最大、最核心的一层，负责把 `BuySellPoint` 产出的"结构买卖点"升维成"**级别 + 走势类型**"的操作语境。

- 上游（`Chan` / `KLine` / `Bi` / `Seg` / `ZhongShu` / `BuySellPoint`）解决"分型→笔→线段→中枢→买卖点"的**几何结构**；
- `Trend` 层解决"**这个买卖点属于哪一级别的哪一段走势类型？这段走势走完了没有（终完美）？该持有、该离场、该开仓、还是该观望？**"；
- 下游（`Strategy/ChanStrategy.py`）把这些判定接成**十层可独立开关的交易纪律门控**，直接决定 `allow_open / allow_short / allow_exit` 与仓位缩放。

`Trend/__init__.py` 自述本层是"缠论『级别/走势』的操作化"，共 11 个分析器（外加 1 个公共小工具 `TrendCommon`）。其中 `Strategy` 层把它们编织成"**十层**交易纪律"（`LevelLinkage` 与 `SameLevelDecompose`/`TrendAnalyzer` 等分工计入十层编号）。

核心缠论依据一句话：**"任何级别的任何走势类型终要完成"（走势终完美）** —— 操作只在走势类型完成（背驰/买卖点）的边界上进行，买点买、卖点卖，不测而测。

---

## 二、对应缠论课程（分析器 ↔ 课号对照表）

| # | 分析器（文件） | 主要缠论概念 | 对应课号 |
|---|----------------|--------------|----------|
| ① | `TrendAnalyzer.py` | 走势类型状态机（盘整/趋势）、走势终完美、中枢演化（延伸/扩展/新生） | **17、20**（辅：24/27 背驰=终完美） |
| ① | `LevelLinkage.py` | 多级别联立、级别与完全分类、跨级别背驰归属 | **17、102、44**（辅：16/21 区间套） |
| ② | `SameLevelDecompose.py` | 同级别分解 | **38**（辅：36 结合律、37 背驰再分辨） |
| ⑨ | `FugueDecompose.py` | 同级别分解的多重赋格（多声部对位） | **40**（辅：38 同级别分解） |
| ③ | `MiddleYin.py` | 中阴阶段（转折后模糊期） | **89、90** |
| ④ | `MATrend.py` | 均线、轮动与板块强弱 | **106** |
| ⑤ | `SmallTurnBig.py` | 小级别背驰引发大级别转折 | **44** |
| ⑥ | `ZSOscillation.py` | 中枢震荡的监视器 | **92** |
| ⑦ | `ReboundTrader.py` | 如何操作短线反弹 | **107** |
| ⑧ | `InsideOutside.py` | 走势结构的两重表里关系 | **91、93、99** |
| ⑩ | `EnergyDynamics.py` | 几何结构与能量动力结构（未竟篇） | **104**（辅：24 MACD 辅助背驰） |
| — | `TrendCommon.py` | 公共数据结构与前置检查（非概念层） | — |
| 力度 | 走势类型连接/力度贯穿 `TrendAnalyzer`、`LevelLinkage` | 转折的力度与级别、背驰的再分辨 | **29、37** |

> 说明：`EnergyDynamics`（第 104 课）在原典中**只立纲领、未给算法**——缠师只说"一切都是几何结构说了算，一切的能量动力形态，都变几何化"，但并未给出可编程的能量度量。本框架用 **MACD 红绿柱面积近似能量**，属工程化补全；MACD 辅助背驰本身有 24 课原文支持。

---

## 三、书中关键原文

### 第 17 课《走势终完美》—— 走势类型、盘整/趋势定义、中枢

> "任何级别的所有走势，都能分解成趋势与盘整两类，而趋势又分为上涨与下跌两类。"

> ""缠中说禅技术分析基本原理一"：任何级别的任何走势类型终要完成。后面一句用更简练的话，就是"走势终完美"。"

> ""走势终完美"这句话有两个不可分割的方面：任何走势，无论是趋势还是盘整，在图形上最终都要完成。另一方面，一旦某种类型的走势完成以后，就会转化为其他类型的走势……"

> "必须先引入缠中说禅走势中枢的概念：某级别走势类型中，被至少三个连续次级别走势类型所重叠的部分，称为缠中说禅走势中枢。"

> "缠中说禅盘整：在任何级别的任何走势中，某完成的走势类型只包含一个缠中说禅走势中枢，就称为该级别的缠中说禅盘整。"

> "缠中说禅趋势：在任何级别的任何走势中，某完成的走势类型至少包含两个以上依次同向的缠中说禅走势中枢，就称为该级别的缠中说禅趋势。该方向向上就称为上涨，向下就称为下跌。"

——《教你炒股票17：走势终完美》

### 第 20 课《缠中说禅走势中枢级别扩张及第三类买卖点》—— 中枢延伸/扩展/新生

> "缠中说禅走势中枢由前三个连续次级别走势类型的重叠部分确定，其后的走势有两种情况：一、该走势中枢的延伸。二、产生新的同级别走势中枢。而在趋势里，同级别的前后缠中说禅走势中枢是不能有任何重叠的……"

> "缠中说禅走势级别延续定理一：在更大级别缠中说禅走势中枢产生前，该级别走势类型将延续。也就是说，只能是只具有该级别缠中说禅走势中枢的盘整或趋势的延续。"

> "缠中说禅走势级别延续定理二：更大级别缠中说禅走势中枢产生，当且仅当围绕连续两个同级别缠中说禅走势中枢产生的波动区间产生重叠。"

> "一个次级别走势类型向上离开缠中说禅走势中枢，然后以一个次级别走势类型回试，其低点不跌破ZG，则构成第三类买点；一个次级别走势类型向下离开缠中说禅走势中枢，然后以一个次级别走势类型回抽，其高点不升破ZD，则构成第三类卖点。"

——《教你炒股票20：缠中说禅走势中枢级别扩张及第三类买卖点》

### 第 24 课《MACD 对背弛的辅助判断》—— 背驰-买卖点定理、MACD 辅助

> "缠中说禅背驰-买卖点定理：任一背驰都必然制造某级别的买卖点，任一级别的买卖点都必然源自某级别走势的背驰。"

> "而C段的走势类型完成时对应的MACD柱子面积（向上的看红柱子，向下看绿柱子）比A段对应的面积要小，这时候就构成标准的背弛。"

> "光用MACD辅助判断，即使你对中枢不大清楚，只要能分清楚A、B、C三段，其准确率也应该在90%以上。而配合上中枢，那是100%绝对的……"

——《教你炒股票24：MACD对背弛的辅助判断》

### 第 29 课《转折的力度与级别》—— 背驰-转折定理、小级别积累引大转折

> "缠中说禅背驰-转折定理：某级别趋势的背驰将导致该趋势最后一个中枢的级别扩展、该级别更大级别的盘整或该级别以上级别的反趋势。"

> "如果市场的转折与背驰都有这在级别上一一对应关系，那这市场也太没意思、太刻板了，而由于这种小级别背驰逐步积累后导致大级别转折的可能，才使得市场充满当下的生机。"

——《教你炒股票29：转折的力度与级别》

### 第 37 课《背驰的再分辨》—— 没有趋势没有背驰、c 必创新高/新低

> "没有趋势，没有背驰，不是任何a+A+b+B+c形式的都有背驰的。当说a+A+b+B+c中有背驰时，首先要a+A+b+B+c是一个趋势。而一个趋势，就意味着A、B是同级别的中枢……"

> "还有，如果a+A+b+B+c是上涨，c一定要创出新高；a+A+b+B+c是下跌，c一定要创出新低。"

——《教你炒股票37：背驰的再分辨》

### 第 38 课《走势类型连接的同级别分解》—— 同级别分解唯一性

> "所谓同级别分解，就是把所有走势按一固定级别的走势类型进行分解。根据"缠中说禅走势分解定理"，同级别分解具有唯一性，不存在任何含糊乱分解的可能。"

> "对于这种同级别分解视角下的操作，永远只针对一个正在完成着的同级别中枢，一旦该中枢完成，就继续关注下一个同级别中枢。"

——《教你炒股票38：走势类型连接的同级别分解》

### 第 40 课《同级别分解的多重赋格》—— 多声部对位、自动换档

> "……这个现象就保证了，在同级别分解下，一个小级别的操作是可以按一个自动模式换档成一个高级别的操作。"

> "市场的走势，其实就是这样的多重赋格，看似复杂，其实脉络清晰，可以有机地统一在多层次的同级别分解操作中。"

> "而每一层次的操作都是独立又在一个整体的操作中……"

——《教你炒股票40：同级别分解的多重赋格》

### 第 44 课《小级别背驰引发大级别转折》—— 小背驰-大转折定理（必要条件）

> "缠中说禅小背驰-大转折定理：小级别顶背驰引发大级别向下的必要条件是该级别走势的最后一个次级别中枢出现第三类卖点；小级别底背驰引发大级别向上的必要条件提是该级别走势的最后一个次级别中枢出现第三类买点。"

> "注意，关于这种情况，只有必要条件，而没有充分条件，也就是说不能有一个充分的判断使得一旦出现某种情况，就必然导致大级别的转折。"

> "如果这个向下走势并没有回到构成最后一个30分钟中枢的第三类买点那个5分钟向下走势类型的高点，那么这个向下走势就不必要理睬，因为走势在可接受的范围内。"

——《教你炒股票44：小级别背驰引发大级别转折》

### 第 89 课《中阴阶段的具体分析》—— 中阴的界定与 100% 依据

> "中阴阶段能否处理好，关系到操作节奏的连接问题。很多人的操作节奏特乱，就是因为不知道中阴阶段的问题。中阴阶段，虽然表现为中枢震荡，但并不是一般性的中枢震荡。"

> "这些可能，首先一个最基本的原则是，必须先出现一个5分钟中枢，因为无论后面是什么级别的走势，只要是超1分钟级别的，就一定先有一个5分钟中枢，这没有任何特例的可能。而这个100%成立的结论，就构成我们操作中最大也是100%准确的基本依据。"

> "而这5分钟中枢成立后，就必然100%面临一个破坏的问题，也就是一个延伸或着第三买卖点的问题……"

——《教你炒股票89：中阴阶段的具体分析》

### 第 90 课《中阴阶段结束时间的辅助判断》—— 布林收口预判中阴结束

> "一般来说，某一级别的布林通道收口，就意味着比这低级别的某个中阴过程要级别扩展或结束了，一般都对应着有相应的第三类买卖点。"

——《教你炒股票90：中阴阶段结束时间的辅助判断》

### 第 91 课《走势结构的两重表里关系 1》—— 笔定理与表里过滤

> "缠中说禅笔定理：任何的当下，在任何时间周期的K线图中，走势必然落在一确定的具有明确方向的笔当中（向上笔或向下笔），而在笔当中的位置，必然只有两种情况：一、在分型构造中。二、分型构造确认后延伸为笔的过程中。"

> "如果5分钟里是（1，1）或者（-1，1）的状态，那么1分钟里前面的任何波动，都没有太大的价值，因为无论这种波动如何大，都没到足以改变5分钟（1，1）或者（-1，1）状态的程度，这里就对1分钟的波动有了一个十分明确的过滤作用。"

——《教你炒股票91：走势结构的两重表里关系1》

### 第 99 课《走势结构的两重表里关系 3》—— 连接走势级别小于中枢、越界即危险

> "因为划分中的这种情况，我们就很明确地知道，走势的最大特点就是，连接中枢的走势级别一定小于中枢，换言之，一个走势级别完成后必然面临至少大一级别的中枢震荡。"

> "任何一个后续的更大级别中枢震荡，必然至少要落在前一走势类型的最后一个中枢范围里，这是一个必然结论……但，一旦其中枢震荡回到原走势类型的第二甚至更后中枢里，那么，对应的中阴状态就是不健康的，是危险的……"

——《教你炒股票99：走势结构的两重表里关系3》

> 注：第 93 课《走势结构的两重表里关系 2》正文多为解盘杂文，其"以分型/笔为表"的判据与第 91 课一致，故不单独引用。

### 第 102 课《再说走势必完美》—— 级别与完全分类、区间套

> "正因为本ID的理论揭示了看似毫无规律的市场走势有如此完美的整体规律，所以才有了其后一系列的操作可能。这才是走势必完美真正关键的地方。"

> "而级别的存在，一个必然的结论就是，任何高级别的改变都必须先从低级别开始。例如，绝对不可能出现5分钟从下跌转折为上涨，而1分钟还在下跌段中。"

> "注意，完全分类是级别性的，是有明确点位界限的。而不是粗糙的上下平的无聊概念。也就是说，本ID的理论完全是数量化的，因此而就是精确化的，里面不存在任何含糊的地方。"

——《教你炒股票102：再说走势必完美》

### 第 104 课《几何结构与能量动力结构 1》—— 纲领（未竟篇，未给算法）

> "而本ID的理论，本质上是站在这种现代物理的角度构建自己的能量动力学结构的。这里，一切都是几何结构说了算，一切的能量动力形态，都变几何化，必须有这种思维上的根本改变，才会有真正的理解。"

——《教你炒股票104：几何结构与能量动力结构1》

> 说明：104 课只立"能量动力=几何化"的**纲领**，明确说"具体怎么样，以后慢慢说来"，并未给出任何能量度量算法。本框架用 MACD 柱面积近似能量属工程化补全（MACD 辅助背驰见第 24 课原文，上文已引）。

### 第 106 课《均线、轮动与缠中说禅板块强弱指标》—— 均线系统与板块强弱

> "除了最简单的笔，任何走势都是大级别套小级别的，因此，单纯一条均线的意义不大，必须是均线系统。"

> "由此可见，走势级别与均线虽然没有必然的关系，但还是有一个大致的区间对应的。"

> "还有一种更重要的，就是根据板块来，要判别一板块的强弱很简单，就是把类别数平均一下，越大越强，而这个平均类别数，可以叫缠中说禅板块强弱指标。"

——《教你炒股票106：均线、轮动与缠中说禅板块强弱指标》

### 第 107 课《如何操作短线反弹》—— 反弹分段操作、不测反弹/反转

> "在这种分析下，具体的反弹操作一定是同次级别分解方式进行的，也就是说，30分钟级别的反弹，是按5分钟的节奏去处理的。"

> "最后，一定不要去预测什么反弹还是反转，这根本没意义。反弹越搞越大，最后就自然成了反转……你唯一需要知道的就是，只要在第一中枢后出现第三类买点并形成非背驰类向上，才可以流着口水地持股睡觉等其余中枢形成，否则，随时都有被反回来的风险。"

——《教你炒股票107：如何操作短线反弹》

### 第 92 课《中枢震荡的监视器》—— 高抛低吸与 Zn 监视

> "中枢震荡，最终一定以某级别的第三类买卖点结束。但问题是，如何预先给出有参考价值的提示，也就是如何去监控这震荡是在逐步走强，还是逐步走弱，这是一个有操作价值的问题。"

> "一个中枢确立后，中枢区间的一半位置，称为震荡中轴Z。而每一个次级震荡区间的一半位置，依次用Zn表示……"

> "这里，存在着一种必然的关系，就是最终，Zn肯定要超越A或B，为什么？如果不这样，就永远不会出现第三类买卖点了……"

——《教你炒股票92：中枢震荡的监视器》

---

## 四、实现思路

### 4.1 TrendAnalyzer（走势类型状态机 + 中枢演化）

文件：`TrendAnalyzer.py`。三个数据结构 + 一个静态方法集合 `CTrendAnalyzer`。

- `ZoushiType`（枚举）：`UP_TREND / DOWN_TREND / CONSOLIDATION / UNDEFINED`，对应 17 课"上涨趋势 / 下跌趋势 / 盘整 / 走势未完成"。
- `ZoushiStatus`（枚举）：`PERFECT / IMPERFECT`，对应"走势终完美 / 进行中"。
- `ZoushiState`（dataclass）：`zoushi_type, status, zs_count, direction, divergence_ratio`，并暴露 `is_perfect / is_trend` 属性。

核心方法：

1. **`classify(seg)`**（走势类型判定，粒度=单个线段内的笔中枢）：先 `_valid_zs_list` 过滤 `is_one_bi_zs()`（排除单笔中枢），按有效中枢个数分支：
   - `0` → `UNDEFINED`；`1` → `CONSOLIDATION`（盘整）；
   - `≥2`：逐对相邻中枢判断——`nxt.low > cur.high` 完全抬高记为上涨、`nxt.high < cur.low` 完全降低记为下跌；两者都不成立（有重叠）→ 视为中枢扩展、降级为 `CONSOLIDATION`。这正是 17 课"趋势=≥2 依次同向、20 课"趋势里前后中枢不能有任何重叠"的直接编码。
2. **`direction_of(seg)`**：`UP_TREND→"up"`、`DOWN_TREND→"down"`；盘整/未完成用 `seg.is_down()` 兜底。
3. **`is_perfect(seg, bsp_config)`**（走势终完美判定，24/27 课）：取最后一个多笔中枢，若有 `bi_out`（离开段）则调用中枢自带的 `last_zs.is_divergence(bsp_config)`，返回 True 即判定走势完成（离开段背驰）。异常安全地吞掉返回 False。
4. **`analyze(seg, bsp_config=None)`**：把上述合成为完整 `ZoushiState`，`bsp_config` 提供 `macd_algo / divergence_rate`（`is_divergence` 的判定入参来自上游 `BuySellPoint` 中枢对象，本层不重算背驰算法，只做结构级调用）。

**"级别放大"专用方法（正确粒度=中枢序列）**：

- **`classify_by_zs_list(zs_seq, min_trend_zs=2)`**：与 `classify` 区别在于看整个级别的中枢序列（`zs_list.zs_lst` 或放大级别的 `segzs_list`）。从最后一个中枢**往前数连续同向且不重叠**的中枢个数：`up_cnt`（后中枢低点>前中枢高点）或 `down_cnt`（后中枢高点<前中枢低点）达到 `min_trend_zs` 才判趋势。返回 `(ZoushiType, last_zs)`。
- **`is_zoushi_perfect(zs_seq, bsp_config)`**：末中枢离开段背驰 → 走势完成（序列版）。

**中枢演化（第 20 课 延伸/扩展/新生）**：

- **`zs_relation(prev_zs, next_zs)`**：用 `Common.FuncUtil.has_overlap(...)` 判区间是否重叠——重叠 → `'expansion'`（扩展，转更大级别盘整）；`next.low > prev.high` → `'newborn_up'`（新生向上，趋势延续）；`next.high < prev.low` → `'newborn_down'`。
- **`zs_evolution(zs_seq)`**：把相邻中枢关系串成序列。
- **`is_trend_continuing(zs_seq)`**：只要最新一段关系是 `'newborn_*'` 就说明趋势还在生长、顶底未真正完成 → 不应被小级别假卖点洗出。

`classify` 用严格"后中枢低点>前中枢高点"（完全分离）作为"不重叠"判据，是把 20 课"前后中枢不能有任何重叠"离散化的实现选择；`min_trend_zs` 默认 2 对应"至少两个中枢"，但它本身是本框架可调参数而非原典规定。

### 4.2 LevelLinkage（多级别联立 + 跨级别背驰归属）

文件：`LevelLinkage.py`。把 16/21/102/44 课的"级别"变成可执行的"**信号级别背书**"。

- `LevelState`（dataclass）：单级别快照——`lv, zoushi_type, is_perfect, zs_count, divergence_ratio, last_close, last_zs_low/high`，暴露 `is_up_trend / is_down_trend`。
- `ReversalAttribution`（dataclass）：一个操作级反转信号的跨级别归属结论——`is_buy, effective_lv, endorsed_by_higher, higher_active_trend, higher_perfect, allow_exit, allow_open, allow_short, reason, level_trace`。
- `MultiLevelContext`：入参 `lv_list`（从大到小）、`operating_lv`（信号产生级别）、`min_trend_zs`。
  - `_rank(lv)`：把 `KL_TYPE` 映射成整数序（`K_1M=1 … K_YEAR=11`）；`higher_levels()` 返回比操作级别大的级别列表。
  - **`update(chan, bsp_conf)`**：对每个级别调 `_analyze_level`：取 `kl.zs_list.zs_lst` → `classify_by_zs_list` 得走势类型；用 `_perfect_ratio`（末中枢 `bi_out` 是否背驰）得 `is_perfect`。缓存进 `self.states`。
  - **`attribute_reversal(is_buy)`**（核心·跨级别归属）：信号方向 `signal_dir`（买点=up / 卖点=down），阻挡趋势 `blocking`（买点遇 `DOWN_TREND` / 卖点遇 `UP_TREND`），背书趋势 `endorsing`（反之）。**自高向低**扫描更高级别：
    - 高级别处于**逆向趋势且未完美** → 该操作级信号降级为"次级别回调"：`allow_exit=False`（顺势仓不被洗出）、`allow_open=False`（不开逆势新仓）、`allow_short=is_buy`（卖点场景且高级别上涨未完 → 禁做空），立即返回，`reason` 写明"操作级别背驰归属为次级别回调，持有不逆势"；
    - 高级别逆向趋势**已完美** → `higher_perfect=True`；高级别**已转同向趋势** → `endorsed_by_higher=True`；
    - 高级别只是盘整/未完成 → 继续看更高级别，最后回落"操作级别自身是否完美"判定。

**为何需要**（呼应 102 课"任何高级别的改变都必须先从低级别开始"）：日线顶背驰若发生在周/月线上涨未完成阶段，它只是大级别上涨里的一段次级别回调，按日线卖点平多/做空就是被假卖点洗出、逆大势开空；只有高级别上涨本身也完美，日线卖点才是真反转。

`_rank` 的级别序数表、以及"逆向趋势未完美=阻挡、已完美/转同向=背书、方向不明=回落"这套三态决策树，是本框架把级别原理**规则化**的实现；原典只给出"背驰必须归属级别"的原理与"高级别改变先由低级别开始"的定理，未给这套布尔门控。单级别（`lv_list` 只有操作级别）时 `higher_levels()` 为空，归属逻辑自动退化为"只看操作级别自身完美与否"（兼容旧行为）。

### 4.3 SameLevelDecompose（同级别分解）

文件：`SameLevelDecompose.py`。落地 38 课"把所有走势按一固定级别的走势类型进行分解，具有唯一性"。

- `DecomposePiece`（dataclass）：一段走势类型——`idx, zoushi_type, direction, zs_list, is_perfect, divergence_ratio, begin_time, end_time`，暴露 `zs_count / is_up / is_down`。
- `SameLevelDecomposer.decompose(chan, lv, bsp_conf)`：以操作级别的**笔中枢序列**（去单笔中枢）为骨架，**自左向右贪心分段**：
  - 相邻中枢关系用 `TrendAnalyzer.zs_relation` 判定；
  - `'expansion'`（重叠）→ 并入当前段（盘整/中枢扩展延续）；
  - 与当前段方向**一致**的新生 → 并入（趋势延伸）；
  - 与当前段方向**相反**的新生 → 结束当前段、另起新段（方向翻转）；
  - `_finalize` 结算段类型：段内同向不重叠中枢数（`_count_same_dir`）`≥ min_trend_zs` → 趋势，否则盘整；末中枢 `bi_out` 背驰（`is_divergence`）→ `is_perfect=True`；记录时间窗与背驰比。
  - 列表最后一个 piece 通常是"进行中的当前段"。
- 便捷函数：**`current_piece(pieces)`** 取最后一段；**`holding_signal(pieces, is_long)`** —— 持多且当前段是上涨走势类型且未完美 → 返回 True（应持有）；已完美或方向相反 → False。

这提供了与"级别递归（区间套）"正交的另一条操作路径：注意力锁死在"操作级别这一段走势类型是否完成"，中途次级别回调/盘整都不构成离场理由——正是"不被假卖点洗出"的可执行判据。

"方向翻转即收束当前段、另起新段"的贪心切分规则、`min_trend_zs` 阈值、`_single_direction` 用 `bi_out` 方向给单中枢段定方向，均是把 38 课"固定级别分解"编程化的本框架选择。

### 4.4 FugueDecompose（多重赋格）

文件：`FugueDecompose.py`。落地 40 课"多重赋格 = 把同级别分解同时施加到多个级别，像赋格曲多声部对位"。

- `FugueVoice`：一个级别声部的当前段——`lv, direction, is_perfect, zs_count`。
- `FugueState`：`voices, consensus_dir（多数方向）, aligned（齐奏）, conflict（冲突）, reason`，暴露 `voice_count / direction_of(lv)`。
- `FugueDecomposer.decompose(chan, lv_list, bsp_conf)`：对 `lv_list` 中**每个级别独立运行 `SameLevelDecomposer`**，取各自当前段方向；`up_n/down_n` 统计——`consensus_dir` 取多数方向，`aligned = 只有单一方向（无冲突）`，`conflict = not aligned`。

**策略含义**：各级别当前段方向一致（对位齐奏）→ 趋势可靠、可加权持有/加仓；声部方向冲突（大小级别打架）→ 禁开逆势仓、减仓观望。

把"赋格/对位"量化成"多数方向共识 + 是否单一方向"、以及策略层的加权系数 `fugue_boost`（见 4.10 与第六节），是本框架的启发式实现；原典只描述"多层次同级别分解的独立又统一"。

### 4.5 MiddleYin（中阴阶段）

文件：`MiddleYin.py`。落地 89/90 课"转折后、新走势类型形成前的方向未定模糊期"。

- `MiddleYinState`：`in_middle_yin, boundary_time, bars_since, new_zs_count, has_t3, reason`。
- `MiddleYinDetector.detect(chan, lv, max_bars=None)`：
  1. 找最近一个**转折边界** = 最后一个 `BSP_TYPE.T1 / T1P`（趋势/盘整背驰一类买卖点）；无边界则直接返回（谈不上中阴）；
  2. 统计边界**之后**是否已出现确认结构：`has_t3`（边界后出现 `T3A/T3B` 第三类买卖点）、`new_zs_count`（begin 落在边界之后的新多笔中枢数）；
  3. `bars_since` = 当前合并 K 线索引 − 边界索引（近似经过的 K 线数）；
  4. `resolved = has_t3 or new_zs_count>0`；`timed_out = max_bars 且 bars_since>max_bars`；
     - `resolved or timed_out` → `in_middle_yin=False`（超时"视为已消化"）；否则 `in_middle_yin=True`，`reason="转折后尚无新中枢与第三类买卖点确认, 方向未定"`。

对应 89 课"转折后必然先出现一个更大级别中枢，处理中阴就是把这个中枢处理好、直到第三类买卖点结束震荡"，以及 90 课"中阴结束通常对应第三类买卖点出现"。

`max_bars` 的"中阴最长时限"（默认 30，见策略层）是原典没有的超时兜底——原典只说中阴会被新中枢/第三类买卖点结束，本框架额外给了一个"太久没确认就当已消化"的保险丝，属于工程化启发式。

### 4.6 MATrend（均线强弱）

文件：`MATrend.py`。落地 106 课"必须是均线系统、走势级别与均线有大致区间对应、板块强弱指标"。

- `MATrendState`：`close, ma_short/mid/long, bull_alignment, bear_alignment, ma_short_rising/falling, strength∈[-1,1], enough_data`，暴露 `is_neutral`。
- `MATrendEvaluator(short=5, mid=10, long=20)`：
  - `_closes` 取操作级别最近 `long+2` 根合并 K 线收盘价（每根用最后一个 klu 的 close）；数据不足 `< long` → 直接返回 neutral，`enough_data=False`，**不施加任何门控**；
  - 多头排列 `ma_short>ma_mid>ma_long 且 close>ma_short`；空头排列反之；
  - 斜率用短均线一阶差分（与前一根短均线比较）；
  - **`strength`**：`(close − ma_long)/ma_long` 归一后 *5.0 截断到 [-1,1]，多头排列 +0.05 / 空头 −0.05 加成。

**为何需要**（106 课 + 框架动机）：背驰是"反转"信号，对强单边趋势不友好——健康强势上涨里每次次级别回调都可能被判顶背驰而过早离场/逆势开空。均线给"走势强弱"打分，用于**逆势信号否决 + 顺势持有强化**的软门控。

三条均线的 5/10/20 参数、"多头/空头排列"的精确定义、`strength` 打分公式（*5.0、±0.05 加成）都是本框架自创的量化规则；106 课原文用的是斐波那契式均线系统（5/13/21/34/55/89/144/233）与"类别数平均"的板块强弱指标，本框架未照搬该均线族，而是简化为常规三均线，属工程化取舍。策略层里 `use_ma_filter / ma_veto_short_in_bull / ma_veto_long_in_bear` 才是真正的开关（见第六节）。

### 4.7 SmallTurnBig（小转大）

文件：`SmallTurnBig.py`。落地 44 课"小级别背驰引发大级别转折"，且明确它是 `LevelLinkage` 的**补集**。

- `SmallTurnBigState`：`is_buy, active, large_lv, sub_lv, zs_low/high, sub_divergence_count, broke_out, recovered, reason`。
- `SmallTurnBigDetector(min_sub_divergence=1)`：入口 `detect_buy`（大级别下跌被次级别底背驰逆转=向上小转大）/ `detect_sell`（向下，镜像），共用 `_detect(chan, large_lv, sub_lv, is_buy, bsp_conf)`。确认**三条件同时成立**才 `active=True`：
  1. **无大级别背驰**：大级别末中枢 `bi_out` 的 `is_divergence` 为 False（否则就是常规一类转折，不是小转大）；
  2. **有小级别背驰**：次级别在大级别末中枢形成以来出现过同向 `T1/T1P` 买卖点（`sub_divergence_count ≥ min_sub_divergence`），且最新一次小背驰之后价格**没有**再创大级别顺势新极值；
  3. **结构破坏确认**：大级别价格曾顺趋势方向冲出末中枢（`broke_out`：买入侧曾跌破 `last_zs.low`），且当前收盘已重新收回中枢（`recovered`）——"跌出去又收回来"=空头结构被破坏。

对应 44 课"小级别顶/底背驰引发大级别转折的**必要条件**是最后一个次级别中枢出现第三类卖/买点"——本框架用"大级别价格曾跌出中枢后又收回中枢"作为该必要条件的一种可计算近似（结构被破坏），并强调它只是必要条件、非充分条件（`min_sub_divergence` 只是防单次噪声）。

搜索窗口取"大级别末中枢 `begin.time` 起"、"未再创新极值"判据、`min_sub_divergence` 阈值，以及策略层的 `small_turn_big_scale` 缩仓（默认 0.3），均是本框架的量化实现；44 课本体的判据是"最后一个次级别中枢的第三类买卖点"，本框架用中枢区间破而复收来近似，属工程化。

### 4.8 ZSOscillation（中枢震荡监视器）

文件：`ZSOscillation.py`。落地 92 课"中枢震荡用高抛低吸对待、用监视器预判强弱、最终以某级别第三类买卖点结束"。

- `ZSOscillationState`：`active, zs_low/high/mid, touch_low/high, close, in_low_band, in_high_band, amplitude_pct, bars_in_zs, advice, reason`。
- `ZSOscillationMonitor(band=0.005, min_touch=1).detect(chan, lv)`：以操作级别**最后一个有效中枢** Z 为监视对象：
  1. 尚无第三类买卖点（`T3A/T3B` 且 `klu.idx > begin_idx`）确认离开——有则"中枢已被第三类买卖点破坏, 转趋势操作"，返回不激活；
  2. 最新收盘仍在 `[Z.low×(1−band), Z.high×(1+band)]` 缓冲带内——出带则"价格已离开中枢区间"；
  3. 触摸计数：中枢形成以来各笔触及下沿 `bi._low()<=lo` / 上沿 `bi._high()>=hi` 次数，两侧各 `< min_touch` → "震荡未成形"；
  4. 位置三等分：收盘在下 1/3 → `in_low_band`+advice"低吸区"；上 1/3 → `in_high_band`+"高抛区"；中间 → "观望"。

对应 92 课"下来了补点、上去了抛点"的高抛低吸，与"是否处于中枢震荡"决定策略要不要禁趋势追单、放行盘整背驰（T1P）低吸/高抛。

缓冲带 `band=0.5%`、`min_touch`、三等分区间划分，都是本框架把 92 课的"中轴 Z / Zn 监视"简化成可判定的区间带；原典的监视指标是 Zn（各次级震荡区间中点连线），本框架用"收盘在区间相对位置 + 两侧触摸计数"近似，属工程化。

### 4.9 ReboundTrader（短线反弹）

文件：`ReboundTrader.py`。落地 107 课"急跌后的抢反弹只能短线、仓位必须小、有明确目标位与止损位"。

- `ReboundPlan`：`setup, drop_pct, drop_bars, high_price, low_price, low_idx, target_price, stop_price, reason`。
- `ReboundPlanner(drop_window=20, drop_pct=12.0, target_ratio=0.618, stop_buffer=0.02).plan(chan, lv)`：
  1. **急跌判定**：最近 `drop_window` 根合并 K 线内，自窗口高点 `peak` 计算回落 `drop=(peak/cur_close−1)×100 ≥ drop_pct` → 进入 `setup`；且用"从最低点收复比例 >50%"关闭窗口（仍在超卖区才算）；
  2. **入场**：`setup` 有效期间出现 `T1/T1P` 买点即触发（实际触发在策略层买卖点回调里）；`entry_allowed(plan, bsp)` 要求买点 `klu.idx ≥ plan.low_idx`（最低点之后的点，才是"跌完之后"的反弹点）；
  3. **目标位**：上方最近一个有效中枢的下沿（压力）；若上方无中枢，取 `low + (peak−low)×target_ratio`（默认 0.618 回撤位）；
  4. **止损位**：急跌窗口最低价 ×(1−stop_buffer)。
- 输出计划由策略层 `_open_rebound_long` / `_manage_rebound_pos` 执行，到位/破位机械离场。

对应 107 课"反弹不是反转"——本模块把反弹仓与趋势仓完全隔离：只在急跌到位窗口放行轻仓做多，靠小仓位 + 目标/止损纪律控风险，**刻意绕过**趋势门控（因为抢反弹本身就是逆里级别大势的短线交易）。

`drop_pct=12%`、`drop_window=20`、`target_ratio=0.618`（黄金回撤）、`stop_buffer=2%`、"收复过半跌幅即关窗"、"目标位取上方中枢下沿"等，全部是本框架自创的量化规则；107 课原文只给"反弹应按次级别分解分段操作、不预测反弹还是反转、仓位要小、到位就走"的原理，未给任何百分比阈值。

### 4.10 InsideOutside（两重表里关系）

文件：`InsideOutside.py`。落地 91/93/99 课"里级别走势 × 表级别结构的立体配合"。

- `InsideOutsideState`：`inside_lv（表/小）, outside_lv（里/大）, outside_type, outside_perfect, inside_dir, inside_perfect, relation, allow_exit_long/short, allow_open_long/short, reason`。`relation ∈ resonance / pullback / reversal_confirm / undefined`。
- `InsideOutsideAnalyzer(min_trend_zs=2).analyze(chan, inside_lv, outside_lv, bsp_conf)`：
  - **里**（复用 `TrendAnalyzer.classify_by_zs_list` + `is_zoushi_perfect` 判里级别走势类型与是否终完美）；
  - **表**（复用 `SameLevelDecomposer` 取表级别当前段方向与是否完美）；
  - **关系判定（以持多视角，下跌完全镜像）**：
    - `relation='pullback'`（表阴里阳）：里上涨未完美 + 表当前段为回调/下跌 → 表级别卖点是**中继** → `allow_exit_long=False, allow_open_short=False`（持有不卖、不开逆势空）；
    - `relation='resonance'`（表里同阳）：里上涨未完美 + 表同向上涨 → `allow_exit_long=False`（共振强化持有）；
    - `relation='reversal_confirm'`：里级别不阻挡（已完美/盘整/未完成）+ 表级别背驰 → 允许按表级别转折离场/反手；
    - `undefined`：结构不足，不施加意见。

它作为**独立于"级别归属"的另一条持有/离场判据**：`LevelLinkage` 看"信号属于哪个级别"，`InsideOutside` 看"两级结构当下如何配合"。

对应 91 课"表级别（次级别笔/分型）的波动没到足以改变里级别状态的程度就是过滤/中继"，99 课"连接中枢的走势级别一定小于中枢""中枢震荡回到原走势更后中枢=不健康/危险"。

`relation` 三分类及其直接映射到 4 个 `allow_*` 布尔开关的决策表，是本框架把表里关系**规则化**的实现；91 课原典用 (±1, 0/1) 状态数组描述当下四种笔状态及其转移，本框架未实现该状态机，而是用"里走势类型+是否完美 × 表当前段方向+是否完美"的组合近似，属工程化。

### 4.11 EnergyDynamics（能量动力结构）

文件：`EnergyDynamics.py`。落地 104 课"能量动力=几何化"的**纲领**，并用 24 课 MACD 辅助背驰把它做成可算的能量度量。

- `EnergyState`：`last_ratio（末中枢出/入能量比）, energy_in/out, divergence_energy, divergence_down（True=下跌侧/False=上涨侧）, trend_energy_seq, reason`。
- `EnergyEvaluator(decay_threshold=0.8).evaluate(chan, lv)`：
  - `_bi_energy(bi)`：一笔能量 = 笔内全部 K 线 `Σ|macd 柱|`；MACD 缺失时退化 `Σ|收盘变动|`（再退化用笔首尾位移）——**这是本框架用 MACD 近似能量的核心，属工程化补全**；
  - 对最近至多 5 个中枢算 `bi_out/bi_in` 能量比 → `trend_energy_seq`、`last_ratio`；
  - **能量背驰 `divergence_energy`**：离开段把价格推过进入段极值（`bi_out` 创出顺势新极值：下跌侧 `bi_out._low() < bi_in._low()` / 上涨侧反之），**但能量比 < decay_threshold（默认 0.8，即能量衰减超 20%）** → 价格与能量背离。

**策略语义（许可性而非阻挡性）**：能量背驰允许顺势仓在几何卖点被门控挡住时**提前离场**（能量先于结构衰竭），并**否决**在能量背驰方向的追势开仓；它从不阻挡"持有"逻辑。且因独立回测贡献为负，**默认关闭**（`use_energy=False`）。

104 课原典**只立纲领、明确"以后慢慢说来"、未给任何算法**。本节整套 MACD 能量近似（`Σ|macd|`、0.8 阈值、能量比序列）都是本框架的工程化实现；其中"用 MACD 柱面积比较进出段力度判背驰"有 24 课原文支持（"C 段对应的 MACD 柱子面积比 A 段小就构成标准背弛"），但"能量先于几何衰竭 → 许可性提前离场"是本框架的自创交易假设。

### 4.12 TrendCommon（公共数据结构）

文件：`TrendCommon.py`。非概念层，是各分析器入口共用的**前置检查小工具**，供新增分析器直接复用：

- `fetch_kl(chan, lv, state, missing_reason="级别数据缺失")`：取某级别 KLine，级别缺失时写 `state.reason` 并返回 None；
- `valid_zs_list(kl)`：过滤掉 `is_one_bi_zs()` 后的有效中枢序列；
- `require_valid_zs(kl, state, empty_reason="无有效中枢")`：有效中枢为空时写 reason 并返回 None。

`ZSOscillation / ReboundTrader / InsideOutside / EnergyDynamics` 的入口都用它统一"取级别 KLine → 过滤单笔中枢 → 空结果写 reason"的样板，避免各分析器重复。

> 注：`TrendAnalyzer / SameLevelDecompose / LevelLinkage` 等**未**使用 `TrendCommon`，而是各自内联 `[z for z in ... if not z.is_one_bi_zs()]` 过滤；本框架的收敛主要在新增的 4 个分析器里。

---

## 五、文件清单

| 文件 | 行数级别 | 角色 | 对应课 |
|------|----------|------|--------|
| `__init__.py` | 包入口 | 统一导出 11 个分析器与其状态类，附中文说明 | — |
| `TrendCommon.py` | ~30 | 公共前置检查（取级别/过滤单笔中枢/空结果写 reason） | — |
| `TrendAnalyzer.py` | ~280 | 走势类型状态机 + 中枢演化（延伸/扩展/新生） | 17、20（辅 24/27） |
| `LevelLinkage.py` | ~240 | 多级别联立 + 跨级别背驰归属 | 17、102、44（辅 16/21） |
| `SameLevelDecompose.py` | ~190 | 同级别分解（贪心分段 + 持有判据） | 38（辅 36/37） |
| `FugueDecompose.py` | ~108 | 多重赋格（多级别同步分解 + 声部对位） | 40 |
| `MiddleYin.py` | ~107 | 中阴阶段识别（边界后确认结构判定） | 89、90 |
| `MATrend.py` | ~118 | 均线强弱（多头/空头排列 + 打分） | 106 |
| `SmallTurnBig.py` | ~175 | 小转大（三条件确认早期反转） | 44 |
| `ZSOscillation.py` | ~140 | 中枢震荡监视器（区间带 + 触摸 + 位置分区） | 92 |
| `ReboundTrader.py` | ~148 | 短线反弹计划（急跌窗口 + 目标/止损） | 107 |
| `InsideOutside.py` | ~138 | 两重表里关系（里走势 × 表段配合） | 91、93、99 |
| `EnergyDynamics.py` | ~130 | 能量动力（MACD 近似能量 + 能量背驰，默认关闭） | 104（辅 24） |

---

## 六、与其他模块的协作（十层如何接线与开关默认值）

`Trend` 各分析器本身**不做交易决策**，只产出结构化状态；真正的接线在 `Strategy/ChanStrategy.py`（`StrategyConfig` + `ChanStrategy`），CLI 开关默认值在 `MainChan.py`（`_build_strategy_config`）。

### 6.1 刷新机制：每根 K 线更新十层上下文

`ChanStrategy._refresh_context(chan)` 在 `on_bar` 开头调用，按各自开关刷新：
`use_level_linkage`→`MultiLevelContext.update`；`use_same_level_decompose`→`decompose` 得 `self._pieces`；`use_middle_yin`→`MiddleYinDetector.detect(max_bars=middle_yin_max_bars)`；`use_ma_filter`→`MATrendEvaluator.evaluate`；以及新增六层 `use_small_turn_big`（需 `parent_lv` 与 `sub_lv`，`sub_lv = nested_lv[0]`）、`use_zs_oscillation`、`use_rebound`、`use_inside_outside`（需 `parent_lv`）、`use_fugue`（对整条 `lv_list`）、`use_energy`。父级别 = 比操作级别大一级的最近级别。

### 6.2 十层在开/平/持三处如何门控

- **做空门控 `_can_short`** 与 **做多门控 `_can_open_long`**（对称）：
  ① 级别联立 `attribute_reversal` → `allow_short/allow_open` 为 False 时本应否决，但 **⑤ 小转大确认**（`self._stb_*.active`）或 **⑥ 中枢震荡高抛/低吸区**（`in_high_band/in_low_band`）可放行，并按 `small_turn_big_scale`/`zs_osc_scale` 设 `self._open_scale` 缩仓；
  ④ 均线 `ma_veto_short_in_bull` 且多头排列 → 禁逆势做空（`ma_veto_long_in_bear` 默认关，保留抄背驰底）；
  ⑧ 表里关系 `not io.allow_open_short/long` → 否决；
  ⑨ 多重赋格声部齐奏反向（`consensus_dir=="up" and aligned` 对做空 / `"down"` 对做多）→ 否决；
  ⑩ 能量侧向背驰（`divergence_energy` 且方向匹配）→ 否决追势开仓。
- **离场 `_should_exit_long` / `_should_exit_short`（趋势持有）**：
  ⑩ 能量上涨侧背驰（且非 `energy_veto_only`）→ 许可性提前离场；否则 ① 级别归属 `not allow_exit` → 持有；② 同级别分解 `holding_signal(_pieces, is_long)` → 持有；⑧ 表里 `relation=='pullback'` → 持有、`=='reversal_confirm'` → 放行；⑨ 赋格齐奏同向 → 强化持有。全部不挡时 → 允许平。
- **仓位加权/降权**：`_open_long/_open_short` 里叠加 ③ `_scale_middle_yin`（中阴期 `middle_yin_scale` 降权）、门控放行缩放 `_open_scale`（⑤⑥）、⑨ `_fugue_boost_ratio`（齐奏同向 × `fugue_boost`）。
- **⑦ 短线反弹**独立通道：`_handle_bsp1` 里若 `use_rebound && _rebound_plan.setup && entry_allowed` 走 `_open_rebound_long`，绕过趋势门控，持仓由 `on_bar` 顶部 `_manage_rebound_pos` 按目标/止损机械离场。
- 区间套（`ChanNestedStrategy`，第 21 课）在开仓后用次级别背驰逐层夹逼精确定位入场价，与 `SmallTurnBig` 的 `sub_lv = nested_lv[0]` 共享次级别配置。

### 6.3 开关默认值（来自 `StrategyConfig` / `MainChan`）

| 层 | 开关 | 默认 | 关键子参数（默认） | CLI |
|----|------|------|--------------------|-----|
| ① 级别联立 | `use_level_linkage` | **True** | `lv_list` 空=仅操作级 | `--no-level-linkage` |
| ② 同级别分解 | `use_same_level_decompose` | **True** | `min_trend_zs=2` | `--no-decompose` |
| ③ 中阴阶段 | `use_middle_yin` | **True** | `middle_yin_scale=0.5`, `middle_yin_max_bars=30` | `--no-middle-yin` |
| ④ 均线强弱 | `use_ma_filter` | **True** | `ma=5/10/20`, `ma_veto_short_in_bull=True`, `ma_veto_long_in_bear=False` | `--no-ma` |
| ⑤ 小转大 | `use_small_turn_big` | **True** | `small_turn_big_scale=0.3` | `--no-small-turn-big` |
| ⑥ 中枢震荡 | `use_zs_oscillation` | **True** | `zs_osc_scale=0.3` | `--no-zs-oscillation` |
| ⑦ 短线反弹 | `use_rebound` | **True** | `rebound_scale=0.2`, `rebound_drop_pct=12.0`, `rebound_window=20` | `--no-rebound` |
| ⑧ 表里关系 | `use_inside_outside` | **True** | — | `--no-inside-outside` |
| ⑨ 多重赋格 | `use_fugue` | **True** | `fugue_boost=1.25` | `--no-fugue` |
| ⑩ 能量动力 | `use_energy` | **False**（默认关） | `energy_decay=0.8`, `energy_veto_only=False` | `--use-energy`（开启）、`--energy-veto-only` |

其它贯穿配置：`operating_lv=K_DAY`、`nested_lv=[K_30M]`、`position_l1/l2/l3 = 0.3/0.4/0.3`、`divergence_rate=0.9`、`hold_trend_until_perfect=True`、`flip_short/flip_long=False`（反手默认关，一律先回空仓）、`enable_short=True`（A 股等市场由 `MarketCapability.support_short` 强制关）。

### 6.4 单级别休眠提示

`MainChan._dormant_layer_warning`：当 `lv_list_full` 只有 1 个级别时，①级别联立 / ⑤小转大 / ⑧表里关系 / ⑨多重赋格 会**休眠**（无父/高级别可依），打印提示并建议用 `--lv week,day` 之类传多级别方可生效。`analyze` 模式（`run_analyze`）会依次打印十层各自的当前状态字符串，便于逐项对照实验。


