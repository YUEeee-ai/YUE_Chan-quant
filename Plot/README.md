# Plot —— 缠论结构绘图层

## 一、模块定位

`Plot` 是**可视化层**：把 `Chan.CChan` 计算出来的整套缠论结构（合并 K 线、笔、线段、线段中枢、
特征序列、中枢、三类买卖点、MACD/均线/BOLL/通道/Demark 等辅助指标，以及外部成交标记）
渲染成 matplotlib 图。设计上分成两半：

- `PlotMeta.py`：**数据抽取层**——把各类缠论对象转成纯坐标元数据（`*_meta` 小对象），
  绘图代码只跟 `*_meta` 打交道，不直接依赖算法对象，解耦且便于 x 范围裁剪。
- `PlotDriver.py`：**渲染层** `CPlotDriver`——按 `plot_config` 开关逐项 `draw_xxx`，管理 figure/
  子图布局、x/y 轴范围、多级别联排、MACD 副图。
- `AnimatePlotDriver.py`：`CAnimateDriver`——配合 `step_load` 做逐 K 线生长动画（Notebook 内）。

本层为**纯工程基础设施，无直接对应缠论课**——它只把已有结构"画出来"，不参与任何判定。
（笔/线段/中枢/买卖点这些概念的原典出处见各自算法包，如 `Bi/Seg/ZS/BuySellPoint`。）

## 二、对应缠论课程

**无直接原典对应，服务于"结构可视化"层。** 它呈现的对象（分型、笔、线段、中枢、三类买卖点）
在书中各有专课，但那些定义由对应的计算包实现；本层仅负责把它们映射到屏幕坐标，
不重复实现任何缠论判据。

## 三、书中关键原文

**本层无直接原典对应。** 本层是把 `CChan` 已算出的结构原样可视化，所有语义都来自上游算法包，
绘图本身不引入新的缠论概念，因此不引用原文。

## 四、实现思路

### 4.1 元数据抽取：CChanPlotMeta（PlotMeta.py）

`CChanPlotMeta(kl_list)` 接收单级别 `CKLine_List`，一次性把结构抽成坐标：

- `Cklc_meta`：合并 K 线（端点 idx、high/low、`type`——有分型用 `FX_TYPE`，否则用 `KLINE_DIR`，
  决定画框颜色）、`klu_list`。
- `CBi_meta`：笔 `begin_x/end_x`（原始 K 线 idx）、`begin_y/end_y`、`dir/type`、`is_sure`（未完成笔虚线）。
- `CSeg_meta`：线段端点（**若 `start_bi` 是线段则再下钻一层**，兼容线段线段的嵌套），方向、`is_sure`，
  并计算趋势线 `has_tl/tl_x0/tl_x1/...`（由 `seg.trend_line.line` 的斜率反解 x，`+1e-7` 防除零）。
- `CEigen_meta / CEigenFX_meta`：特征序列矩形的 x 跨度/高度；分型元数据强制 `assert len(ele)==3`。
- `CZS_meta`：中枢 `low/high/begin/end` 与宽高 `w/h`、`is_sure`、**递归 `sub_zs_lst`**、
  `is_onebi_zs`（一笔中枢，默认不画）。
- `CBS_Point_meta`：买卖点 `x=klu.idx`，`y` 买点在 `klu.low`、卖点在 `klu.high`；`desc()` 生成
  `b{type}/s{type}` 文本，线段级别加 `※` 前缀（`is_seg`）。
- `CChanPlotMeta` 汇总：`klc_list / bi_list / seg_list(+eigenfx_lst) / segseg_list / zs_lst /
  segzs_lst / bs_point_lst / seg_bsp_lst`，`datetick`（每根 K 线的日期串）、`klu_len`。
- 供裁剪范围的辅助：`sub_last_kseg_start_idx / sub_last_kbi_start_idx / sub_range_start_idx`——
  多级别联画时把高级别可见范围映射到次级别的起始 idx。

### 4.2 配置解析：plot_config 的三种写法

`parse_plot_config` 支持灵活输入并归一为 `{KL_TYPE: {plot_xxx: bool}}`：
- 单层 dict / 逗号分隔字符串 / 列表 → 对所有级别套同一份配置；
- key 为 `KL_TYPE` 的 dict → 每级别各自配置（要求覆盖 `lv_list` 全部级别）；
- `reformat_plot_config` 自动补 `plot_` 前缀（写 `bi` 等价 `plot_bi`）。
非法类型抛 `CChanException(PLOT_ERR)`。

### 4.3 figure 布局与坐标（PlotDriver 顶层函数）

- `create_figure`：按每个级别是否画 MACD 决定子图数（画 MACD=2 个子图，`macd_h` 高度比例默认 0.3），
  用 `gridspec_kw.height_ratios` 拼总高，返回 `axes_dict[KL_TYPE]=[主图轴, 可选MACD轴]`；
  单级别不画 MACD 时 `axes` 不是数组会触发 except 兜底包成 `[axes]`。
- `GetRealXrange`：x 范围四种互斥设置 `x_range / x_bi_cnt / x_seg_cnt / x_begin_date`
  （断言不能同时设），分别按 K 线根数 / 最近 N 笔 / 最近 N 段 / 起始日期反推 `x_range`。
- `set_x_tick`：按 `x_tick_num`（默认 10）稀疏化刻度并旋转 20°；`cal_y_range` 只统计落在当前 x 窗内的
  合并 K 线高低点（须先设 x_tick 再算 y）；`set_grid` 支持 `xy/x/y/None`。
- `GetPlotMeta`：对 `chan.lv_list` 每个级别造一个 `CChanPlotMeta`；`only_top_lv` 可只画最高级别。

### 4.4 CPlotDriver 主流程

`__init__(chan, plot_config, plot_para)`：解析配置 → 造 metas → 算 x_range → 建 figure →
逐级别取主/MACD 轴、设网格与标题 `code/级别`、算 x/y limit → `DrawElement` → 非最低级别时用
`sub_last_kseg/kbi/range_start_idx` 收紧下一级别 x 左界（多级别对齐）→ `set_ylim`。

`DrawElement` 就是一串 `if plot_config.get("plot_xxx"): self.draw_xxx(...)`，各 `draw_` 的样式参数
从 `plot_para[元素名]` 透传。另有 `save2img(path)` 与 `ShowDrawFuncHelper()`
（反射打印所有 `draw_` 函数默认值，用于写文档）。

### 4.5 各元素绘制要点（draw_*）

- `draw_klu`（K 线）：`plot_mode` 支持 `kl/close/open/high/low`；`rugd=True` 红涨绿跌（否则反色）；
  阳线空心矩形 + 上下影线分开画，阴线实心。范围外（`i+width<x_begin`）跳过。
- `draw_klc`（合并 K 线）：按 `FX_TYPE.TOP/BOTTOM` 红/蓝框、无分型绿色框；`plot_single_kl=False` 时
  跳过单根合并线。
- `draw_bi`（笔）：`plot_bi_element` 实线（`is_sure`）/虚线（未确认）；`show_num` 标笔序号、`disp_end`
  标端点价；多级别 `sub_lv_cnt` 用半透明 `fill_between` 高亮次级别区域。
- `draw_seg / draw_segseg`（线段 / 线段线段）：线宽分别默认 5 / 7，确认实线未确认虚线，
  `plot_trendline` 画趋势线。
- `draw_eigen`（特征序列）：顶红/底蓝半透明矩形，`only_peak` 只画中间第 2 元素。
- `draw_zs / draw_segzs`（中枢 / 线段中枢）：橙色 / 红色矩形框，虚线表未确认，递归画 `sub_zs_lst`；
  `draw_one_bi_zs=False` 默认过滤一笔中枢，`show_text` 标上下沿价格。
- `draw_macd`：取每根 `klu.macd` 的 `DIF/DEA/macd` 柱，橙 DIF、蓝 DEA、红柱、负柱改深绿
  （`assert macd_lst[0] is not None`——须开 `macd_metric`）。
- `draw_mean / draw_channel / draw_boll`：均线用 `hsv` colormap 分色 + 图例；通道取 `TREND_TYPE.MAX/MIN`
  的指定 `T`（未设则报错提示去 `CChanConfig.trend_metrics`）；BOLL 取 `klu.boll.MID/UP/DOWN`，
  未配置 `boll_n` 时 `AttributeError` 转成友好 `CChanException`，并扩展 y 范围。
- `bsp_common_draw / draw_bs_point / draw_seg_bs_point`：买卖点文字 + 箭头，买点在下方（`top` 对齐、
  箭头向上）、卖点在上方；线段买卖点字号/箭头更大；自动把 y_min/y_max 撑开避免箭头被裁。
  `plot_closeAction` 可画平仓动作箭头。
- `draw_marker`：**外部标记**（成交/veto），入参 `{日期:(文字, up/down[, 颜色])}`；用 `datetick_dict`
  把日期映射到 x，越界（`x<x_begin or x>x_end`）跳过防错；`up` 用 `high`、`down` 用 `low` 作基准点，
  箭头长度 = `arrow_l*y_range - 半个箭头`（防与 K 线重叠）。这是 `Strategy.Backtester` 叠加成交/否决标记的接口。
- `draw_demark`：TD 序列 setup/countdown 数字，`min_setup` 过滤、最后 countdown 加背景框，
  `draw_demark_begin_line` 画系列起点水平线（依赖 `Math.Demark.CDemarkEngine`）。

### 4.6 动画 CAnimateDriver（AnimatePlotDriver.py）

`for _ in chan.step_load()` 每根新 K 线重建一个 `CPlotDriver`，用
`IPython.display.clear_output(wait=True)+display(g.figure)` 在 Notebook 中刷新，实现"结构随行情生长"的动画。
依赖 IPython，仅用于交互研究，非出图主路径。

### 4.7 关于 CJK（中文）字体

本层 `PlotDriver` 自身**不做中文字体配置**（其标题/买卖点文字均为 ASCII，如 `b1/s2/1d` 等）。
真正需要中文的是**成交/veto 标记**（"买/空/平多/×满仓/×均线"等），字体设置放在
`Strategy.Backtester._setup_cjk_font`：在候选列表（Microsoft YaHei、SimHei、PingFang SC、
Noto Sans CJK SC 等）里选第一个系统可用字体，写入 `matplotlib.rcParams["font.sans-serif"]`
并设 `axes.unicode_minus=False`，找不到则返回 `None`（中文可能显示为方框）。本层只负责把
`draw_marker` 收到的中文字符串画出来，字体就绪由调用方保证。

## 五、文件清单

| 文件 | 内容 |
|------|------|
| `__init__.py` | 空（包声明） |
| `PlotMeta.py` | `CChanPlotMeta` 与各 `*_meta`（Cklc/CBi/CSeg/CEigen/CEigenFX/CZS/CBS_Point）坐标抽取 |
| `PlotDriver.py` | `CPlotDriver`（渲染器）+ `parse_plot_config/create_figure/set_x_tick/...` 顶层函数 + 全部 `draw_*` |
| `AnimatePlotDriver.py` | `CAnimateDriver`（step_load 逐 K 线动画，依赖 IPython） |

## 六、与其他模块的协作

- **上游**：`Chan.CChan`（提供 `chan[lv]` 的 `CKLine_List` 及 `lv_list`、`step_load`）；
  算法对象来自 `Bi/Seg/ZS/BuySellPoint/KLine/Math.Demark`。
- **枚举依赖**：`Common.CEnum`（`FX_TYPE/KLINE_DIR/BI_DIR/KL_TYPE/TREND_TYPE`）、`Common.CTime`、
  `Common.ChanException(PLOT_ERR)`。
- **被调用**：`MainChan.py`（analyze/backtest 出图）、`Strategy.Backtester.plot`
  （把成交 `trade_history` 与 `bsp_decisions` 转成 `draw_marker` 的 markers 叠加到结构图上）。
- **输出**：`save2img` / `figure.savefig` 落 PNG，供命令行/报告使用。
