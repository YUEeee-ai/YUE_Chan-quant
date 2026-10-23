"""
缠论完整策略引擎 — 严格遵循《市场哲学的数学原理》(缠中说禅)

核心规则:
1. 走势终完美: 任何级别的任何走势类型终要完成，完成后转化为其他走势类型
2. 中枢定义: 某级别走势类型中，被至少三个连续次级别走势类型所重叠的部分
3. 趋势 vs 盘整: 趋势=至少2个同方向中枢; 盘整=恰好1个中枢
4. 三类买卖点:
   - 第一类: 趋势背驰点 (必须有≥2同向中枢的趋势末端)
   - 第二类: 第一类后的次级别回调不创新极值
   - 第三类: 中枢突破后次级别回抽不回中枢
5. 区间套: 高级别定方向，低级别定精确入场
6. MACD辅助背驰: 比较进/出中枢笔的MACD力度
7. 操作纪律: 买点买、卖点卖，不测而测
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

from BuySellPoint.BSPoint import CBS_Point
from Chan import CChan
from Common.CEnum import BSP_TYPE, FX_TYPE, KL_TYPE
from Trend import (  # 11 个分析器统一从包入口导入
    CTrendAnalyzer, ZoushiType, ZoushiState,
    MultiLevelContext, ReversalAttribution,
    SameLevelDecomposer, DecomposePiece, holding_signal,
    MiddleYinDetector, MiddleYinState,
    MATrendEvaluator, MATrendState,
    SmallTurnBigDetector, SmallTurnBigState,
    ZSOscillationMonitor, ZSOscillationState,
    ReboundPlanner, ReboundPlan,
    InsideOutsideAnalyzer, InsideOutsideState,
    FugueDecomposer, FugueState,
    EnergyEvaluator, EnergyState,
)


class PositionState(Enum):
    """持仓状态 — 缠论多空对称"""
    EMPTY = auto()          # 空仓
    LONG_PARTIAL = auto()   # 做多轻仓
    LONG_FULL = auto()      # 做多重仓
    SHORT_PARTIAL = auto()  # 做空轻仓 (试探)
    SHORT_FULL = auto()     # 做空重仓 (确认)


class TrendType(Enum):
    """走势类型 (书中定义) — 保留兼容别名，实际状态机见 Trend/TrendAnalyzer.py"""
    UP_TREND = "上涨趋势"       # ≥2个向上中枢
    DOWN_TREND = "下跌趋势"     # ≥2个向下中枢
    CONSOLIDATION = "盘整"      # 恰好1个中枢
    UNDEFINED = "未完成"        # 走势尚未完成


# 兼容别名: 新的走势类型状态机 (第17/18课"走势终完美")
ZoushiTypeAlias = ZoushiType


@dataclass
class TradeRecord:
    """单笔交易记录"""
    time: str
    action: str           # "BUY" / "SELL" / "SHORT" / "COVER"
    price: float
    bsp_type: str         # 触发的买卖点类型
    bsp_level: str        # 触发级别
    position_ratio: float # 本次仓位比例 (正=开仓, 负=平仓)
    reason: str           # 交易原因说明
    stop_loss: float = 0.0  # 止损价
    take_profit: float = 0.0
    direction: str = ""   # "LONG" / "SHORT" / "" (平仓)


@dataclass
class BspDecision:
    """一个结构买卖点的最终去向(供回测图标注 veto 原因)"""
    time: str
    is_buy: bool
    bsp_type: str          # 结构类型, 如 "2"/"2s"/"1"/"3a"
    outcome: str           # TRADE/PENDING/OPEN_*/EXIT_*/SKIP/VETO/HOLD/COOLDOWN
    reason: str = ""       # 未成交时: 被哪一层挡下的说明
    middle_yin: bool = False  # 当时是否处于中阴阶段(降权)


@dataclass
class StrategyConfig:
    """
    策略配置 — 对应书中操作规则
    
    关键参数:
    - operating_lv: 操作级别 (书中反复强调必须先确定操作级别)
    - nested_lv: 区间套的次级别列表
    - min_trend_zs: 趋势最少中枢数 (书中定义趋势=≥2中枢)
    - divergence_rate: 背驰比率阈值
    - position_l1: 一类买卖点仓位比例
    - position_l2: 二类买卖点加仓比例
    - position_l3: 三类买卖点加仓比例
    """
    # 级别设置
    operating_lv: KL_TYPE = KL_TYPE.K_DAY
    lv_list: List[KL_TYPE] = field(default_factory=list)  # 全部联立级别(从大到小); 空=仅操作级别
    nested_lv: List[KL_TYPE] = field(default_factory=lambda: [KL_TYPE.K_30M])

    # 中枢/趋势参数 (书中核心定义)
    min_trend_zs: int = 2           # 趋势最少需要2个同向中枢 (书中严格定义)
    divergence_rate: float = 0.9    # 背驰判定: out_metric/in_metric < 此值则背驰
    min_zs_cnt: int = 1             # 盘整背驰最少中枢数

    # 仓位管理 (书中实战策略篇)
    position_l1: float = 0.3        # 第一类买卖点: 试探仓 30%
    position_l2: float = 0.4        # 第二类买卖点: 确认加仓 40%
    position_l3: float = 0.3        # 第三类买卖点: 趋势追入 30%

    # 止损规则 (多空非对称: 空头风险无限必须保护, 多头让利润奔跑靠卖点离场)
    stop_loss_long: bool = False    # 多头: 默认不设机械止损, 只靠卖点离场(缠论"卖点卖"+让利润奔跑)
    stop_loss_short: bool = True    # 空头: 默认保留保护性止损(空头亏损无限, 单边行情里防穿仓)
    stop_buffer: float = 0.02       # 止损缓冲 2% (止损位 = 笔低/笔高 × (1∓buffer))

    # 操作纪律
    require_fx_confirm: bool = True # 等分型确认再入场 (书中强调不预测)
    enable_short: bool = True       # 允许做空 (缠论多空完美对称)
    flip_short: bool = False        # False=卖点只平多不反手开空(忠实"卖点卖=离场", 不预测下跌)
    flip_long: bool = False         # False=买点只平空不反手开多(对称, 不预测上涨); 一律先回空仓
    only_trend_bsp1: bool = True    # 严格模式: 一类买卖点必须≥2中枢的趋势中产生
    require_t1_before_t2: bool = False  # 二类必须在一类之后 (BSP引擎已保证结构)
    cooldown_bars: int = 5          # 止损后等待N根K线再入场 (防连续止损)
    hold_trend_until_perfect: bool = True # 趋势持有: 只在操作级别走势终完美才平顺势仓 (第24/27课)

    # === ① 多级别联立 + 跨级别背驰归属 (第16/21课, 第24/27课) ===
    use_level_linkage: bool = True  # 日→周→月联立: 操作级信号须被高级别背书, 否则视为次级别回调
    trend_filter_short: bool = False  # 兼容旧开关: 放大级别上涨未完美则禁做空(级别联立已覆盖此意)
    short_gate_lv: object = None    # 兼容旧字段: 单独的做空确认级别; None=用 lv_list 高级别
    short_gate_min_zs: int = 1      # 兼容旧字段: 做空门控的下跌趋势最少中枢数

    # === ② 同级别分解 (第37/38课) ===
    use_same_level_decompose: bool = True  # 用同级别走势类型是否完美决定持有, 不被次级别波动洗出

    # === ③ 中阴阶段 (第89课) ===
    use_middle_yin: bool = True     # 转折后模糊期对新开仓降权
    middle_yin_scale: float = 0.5   # 中阴阶段新开仓仓位缩放系数(0~1)
    middle_yin_max_bars: int = 30   # 中阴最长时限(合并K线数), 超时视为已消化

    # === ④ 均线强弱辅助 (第106课) ===
    use_ma_filter: bool = True      # 用均线系统判断走势强弱
    ma_short: int = 5
    ma_mid: int = 10
    ma_long: int = 20
    ma_veto_short_in_bull: bool = True   # 多头排列(强势上涨)时禁止逆势做空
    ma_veto_long_in_bear: bool = False   # 空头排列(强势下跌)时是否禁止做多(默认关, 保留抄背驰底)

    # === ⑤ 小转大 (第44课) ===
    use_small_turn_big: bool = True     # 小级别背驰+大级别结构破坏时, 放行早期反转仓
    small_turn_big_scale: float = 0.3   # 小转大早期反转仓的仓位缩放

    # === ⑥ 中枢震荡监视器 (第92课) ===
    use_zs_oscillation: bool = True     # 中枢震荡市中高抛低吸(区间下沿放行盘整背驰低吸)
    zs_osc_scale: float = 0.3           # 震荡市低吸/高抛的仓位缩放

    # === ⑦ 短线反弹 (第107课) ===
    use_rebound: bool = True            # 急跌后抢反弹(独立小仓位计划, 目标/止损机械离场)
    rebound_scale: float = 0.2          # 反弹仓位比例
    rebound_drop_pct: float = 12.0      # 急跌阈值: 窗口内自高点回落百分比
    rebound_window: int = 20            # 急跌观察窗口(K线数)

    # === ⑧ 两重表里关系 (第91/93/99课) ===
    use_inside_outside: bool = True     # 里级别走势 × 表级别当前段的配合判据

    # === ⑨ 多重赋格 (第40课) ===
    use_fugue: bool = True              # 多级别同步同级别分解, 声部齐奏加权/冲突禁开
    fugue_boost: float = 1.25           # 声部齐奏且同向时的仓位加权系数

    # === ⑩ 能量动力结构 (第104课) ===
    use_energy: bool = False            # MACD能量度量, 能量背驰=许可性离场/否决追势信号
                                        # 默认关闭: 独立贡献平均-34.4pp, 最坏-695pp≫最好+281pp (RESEARCH 第十二节)
    energy_decay: float = 0.8           # 能量背驰阈值: 进出能量比低于此值
    energy_veto_only: bool = False      # 变体: 只保留"否决追势开仓", 关闭"许可性提前离场"
                                        # 更贴原作(第24课背驰定理+第104课"几何结构说了算"):
                                        # 背驰用于过滤入场, 离场仍交几何卖点; 可避开长牛复利被打断


class ChanStrategy:
    """
    缠论完整策略引擎 — 多空对称 + 多级别联立版

    缠论核心对称性 (书中"走势终完美"不分多空):
    - 下跌趋势背驰买点 → 做多入场     ←→  上涨趋势背驰卖点 → 做空入场
    - 二类买点(回调不破) → 做多加仓   ←→  二类卖点(反弹不过) → 做空加仓
    - 三类买点(上破不回) → 趋势追多   ←→  三类卖点(下破不回) → 趋势追空

    在基础三类买卖点之上, 叠加十层缠论"级别/走势"纪律 (均可分别开关):
      ① 多级别联立 + 跨级别背驰归属: 操作级反转信号须被更高级别背书, 否则视为
         次级别回调(持有不逆势、不开逆势新仓、卖点不做空);
      ② 同级别分解: 以操作级别当前走势类型是否"终完美"决定持有;
      ③ 中阴阶段: 转折后模糊期对新开仓降权;
      ④ 均线强弱: 强势多头排列抑制逆势做空、强化顺势持有。

    反手默认关闭: 任何反向信号先回到空仓, 新方向由空仓下的新买卖点决定(不测而测)。
    """

    def __init__(self, config: StrategyConfig = None, market_cap=None):
        if config is None:
            config = StrategyConfig()
        self.config = config
        # 市场能力 (None = 不限制, 兼容旧调用)
        self.market_cap = market_cap
        # 若市场不支持做空 (如 A 股零售), 强制禁用
        if market_cap is not None and not market_cap.support_short:
            self._effective_short = False
        else:
            self._effective_short = config.enable_short
        # 多头仓位
        self.long_ratio = 0.0
        self.long_entry = 0.0
        self.long_stop = 0.0
        # 空头仓位
        self.short_ratio = 0.0
        self.short_entry = 0.0
        self.short_stop = 0.0
        # 交易记录
        self.trade_history: List[TradeRecord] = []
        # 结构买卖点决策记录(供回测图标注 veto)
        self.bsp_decisions: List[BspDecision] = []
        # 内部状态
        self._last_bsp_idx = -1
        self._cooldown_until = -1
        self._bar_count = 0
        self._pending_signal = None

        # === 走势分析器 (①~④: 级别联立/同级别分解/中阴/均线) ===
        lv_list = config.lv_list or [config.operating_lv]
        if config.operating_lv not in lv_list:
            lv_list = lv_list + [config.operating_lv]
        self._ml_ctx = MultiLevelContext(lv_list, config.operating_lv, config.min_trend_zs)
        self._decomposer = SameLevelDecomposer(config.min_trend_zs)
        self._middle_yin_det = MiddleYinDetector()
        self._ma_eval = MATrendEvaluator(config.ma_short, config.ma_mid, config.ma_long)
        # === 新增分析器 (小转大/中枢震荡/短线反弹/表里关系/多重赋格/能量动力) ===
        self._stb_det = SmallTurnBigDetector()
        self._zs_osc_mon = ZSOscillationMonitor()
        self._rebound_planner = ReboundPlanner(drop_window=config.rebound_window,
                                               drop_pct=config.rebound_drop_pct)
        self._io_analyzer = InsideOutsideAnalyzer(config.min_trend_zs)
        self._fugue_decomposer = FugueDecomposer(config.min_trend_zs)
        self._energy_eval = EnergyEvaluator(config.energy_decay)
        # 每根K线刷新的分析缓存
        self._pieces: List[DecomposePiece] = []
        self._middle_yin: MiddleYinState = MiddleYinState()
        self._ma_state: MATrendState = MATrendState()
        self._attr_cache: dict = {}
        self._stb_buy: SmallTurnBigState = SmallTurnBigState(is_buy=True)
        self._stb_sell: SmallTurnBigState = SmallTurnBigState(is_buy=False)
        self._zs_osc: ZSOscillationState = ZSOscillationState()
        self._rebound_plan: ReboundPlan = ReboundPlan()
        self._io_state: InsideOutsideState = InsideOutsideState()
        self._fugue: FugueState = FugueState()
        self._energy: EnergyState = EnergyState()
        # 门控放行时的仓位缩放(小转大/中枢震荡低吸), 每次 _can_open_* 调用时重置
        self._open_scale = 1.0
        # 短线反弹持仓计划(目标/止损机械离场)
        self._rebound_pos: Optional[dict] = None

    def _refresh_context(self, chan: CChan):
        """每根K线刷新十层分析上下文(级别联立/同级别分解/中阴/均线 + 新增六层)"""
        cfg = self.config
        self._attr_cache = {}
        try:
            bsp_conf = chan.conf.bs_point_conf.GetBSConfig(False)  # 结构/力度衰竭对称判定
        except Exception:
            bsp_conf = None
        if cfg.use_level_linkage:
            try:
                self._ml_ctx.update(chan, bsp_conf)
            except Exception:
                pass
        if cfg.use_same_level_decompose:
            try:
                self._pieces = self._decomposer.decompose(chan, cfg.operating_lv, bsp_conf)
            except Exception:
                self._pieces = []
        if cfg.use_middle_yin:
            try:
                self._middle_yin = self._middle_yin_det.detect(
                    chan, cfg.operating_lv, max_bars=cfg.middle_yin_max_bars)
            except Exception:
                self._middle_yin = MiddleYinState()
        if cfg.use_ma_filter:
            try:
                self._ma_state = self._ma_eval.evaluate(chan, cfg.operating_lv)
            except Exception:
                self._ma_state = MATrendState()

        # --- 新增六层分析 (独立开关, 互不干扰) ---
        # 父级别 = 比操作级别大一级的最近级别; 次级别 = nested_lv[0](区间套下挂级别)
        higher = self._ml_ctx.higher_levels()
        parent_lv = higher[-1] if higher else None
        sub_lv = cfg.nested_lv[0] if cfg.nested_lv else None

        if cfg.use_small_turn_big and parent_lv is not None and sub_lv is not None:
            try:
                bsp_conf_buy = chan.conf.bs_point_conf.GetBSConfig(True)
                bsp_conf_sell = chan.conf.bs_point_conf.GetBSConfig(False)
                self._stb_buy = self._stb_det.detect_buy(chan, parent_lv, sub_lv, bsp_conf_buy)
                self._stb_sell = self._stb_det.detect_sell(chan, parent_lv, sub_lv, bsp_conf_sell)
            except Exception:
                self._stb_buy = SmallTurnBigState(is_buy=True)
                self._stb_sell = SmallTurnBigState(is_buy=False)
        if cfg.use_zs_oscillation:
            try:
                self._zs_osc = self._zs_osc_mon.detect(chan, cfg.operating_lv)
            except Exception:
                self._zs_osc = ZSOscillationState()
        if cfg.use_rebound:
            try:
                self._rebound_plan = self._rebound_planner.plan(chan, cfg.operating_lv)
            except Exception:
                self._rebound_plan = ReboundPlan()
        if cfg.use_inside_outside and parent_lv is not None:
            try:
                self._io_state = self._io_analyzer.analyze(chan, cfg.operating_lv, parent_lv, bsp_conf)
            except Exception:
                self._io_state = InsideOutsideState()
        if cfg.use_fugue:
            try:
                self._fugue = self._fugue_decomposer.decompose(chan, self._ml_ctx.lv_list, bsp_conf)
            except Exception:
                self._fugue = FugueState()
        if cfg.use_energy:
            try:
                self._energy = self._energy_eval.evaluate(chan, cfg.operating_lv)
            except Exception:
                self._energy = EnergyState()

    def _attribution(self, is_buy: bool) -> ReversalAttribution:
        """取(并缓存)某方向反转信号的跨级别背驰归属结论"""
        if is_buy not in self._attr_cache:
            self._attr_cache[is_buy] = self._ml_ctx.attribute_reversal(is_buy)
        return self._attr_cache[is_buy]

    @property
    def short_enabled(self) -> bool:
        """做空是否生效 (市场支持 AND 策略允许)"""
        return self._effective_short

    @property
    def position_state(self) -> PositionState:
        """当前综合持仓状态"""
        if self.long_ratio > 0.001 and self.short_ratio > 0.001:
            return PositionState.LONG_FULL  # 对冲中(罕见)
        if self.long_ratio > 0.001:
            return PositionState.LONG_FULL if self.long_ratio >= 0.7 else PositionState.LONG_PARTIAL
        if self.short_ratio > 0.001:
            return PositionState.SHORT_FULL if self.short_ratio >= 0.7 else PositionState.SHORT_PARTIAL
        return PositionState.EMPTY

    def on_bar(self, chan: CChan) -> Optional[TradeRecord]:
        """每根K线调用，返回交易信号"""
        self._bar_count += 1

        # 刷新十层走势分析上下文
        self._refresh_context(chan)

        # ⑦ 短线反弹持仓管理: 目标位/止损位机械离场(先于买卖点处理)
        rebound_record = self._manage_rebound_pos(chan)
        if rebound_record:
            return rebound_record

        # 先检查待确认信号
        if self._pending_signal:
            record = self._try_confirm_pending(chan)
            if record:
                self._pending_signal = None
                return record
            # _try_confirm_pending 可能在门控拒绝时已把 _pending_signal 置 None
            if self._pending_signal and self._bar_count - self._pending_signal["detected_bar"] > 10:
                self._pending_signal = None

        # 多级别安全: 信号取自操作级别(而非要求单级别的 chan.get_bsp())
        bsp_list = sorted(chan[self.config.operating_lv].bs_point_lst.lst, key=lambda x: x.klu.time)
        if not bsp_list:
            return None

        new_bsps = [bsp for bsp in bsp_list if bsp.klu.idx > self._last_bsp_idx]
        if not new_bsps:
            return None

        self._last_bsp_idx = bsp_list[-1].klu.idx

        for bsp in new_bsps:
            diag_outcome, diag_reason = self._diagnose_bsp(chan, bsp)
            in_cooldown = self._bar_count < self._cooldown_until
            pend_before = self._pending_signal
            record = None if in_cooldown else self._process_bsp(chan, bsp)
            # 记录该结构买卖点的最终去向(供回测图标注 veto 原因)
            if record is not None:
                outcome, reason = "TRADE", ""
            elif in_cooldown:
                outcome, reason = "COOLDOWN", "止损冷却期"
            elif (self._pending_signal is not None and self._pending_signal is not pend_before
                  and self._pending_signal.get("bsp") is bsp):
                outcome, reason = "PENDING", "待分型确认"
            else:
                outcome, reason = diag_outcome, diag_reason
            self.bsp_decisions.append(BspDecision(
                time=str(bsp.klu.time), is_buy=bsp.is_buy, bsp_type=bsp.type2str(),
                outcome=outcome, reason=reason,
                middle_yin=self.config.use_middle_yin and self._middle_yin.in_middle_yin,
            ))
            if record:
                return record

        return None

    def _diagnose_bsp(self, chan: CChan, bsp: CBS_Point):
        """只读诊断: 该结构买卖点若此刻处理, 会成交/被哪一层挡下 (不改变任何状态)"""
        cfg = self.config
        if bsp.is_buy:
            if self.short_ratio > 0.001:  # 持空遇买点 → 平空
                ok = self._should_exit_short(chan, bsp)
                return ("EXIT_SHORT", "") if ok else ("HOLD", "下跌走势未完→持空不平(级别/同级别)")
            if self.long_ratio >= 0.7:  # 已满仓持多 → 买点不追
                return ("SKIP", "已满仓持多,买点不加仓")
            if not self._can_open_long(chan):
                return ("VETO", self._veto_open_long_reason(chan))
            return ("OPEN_LONG", "")
        else:  # 卖点
            if self.long_ratio > 0.001:  # 持多遇卖点 → 平多
                ok = self._should_exit_long(chan, bsp)
                return ("EXIT_LONG", "") if ok else ("HOLD", "上涨走势未完→持多不卖(级别/同级别)")
            if self.short_ratio >= 0.7:  # 已满仓持空 → 卖点不加
                return ("SKIP", "已满仓持空,卖点不加仓")
            if not self._can_short(chan):
                return ("VETO", self._veto_short_reason(chan))
            return ("OPEN_SHORT", "")

    def _veto_short_reason(self, chan: CChan) -> str:
        cfg = self.config
        if cfg.use_level_linkage:
            attr = self._attribution(is_buy=False)
            if not attr.allow_short:
                if cfg.use_small_turn_big and self._stb_sell.active:
                    return ""  # 小转大放行, 不是否决
                if cfg.use_zs_oscillation and self._zs_osc.active and self._zs_osc.in_high_band:
                    return ""  # 中枢震荡高抛放行
                return "级别归属:" + (attr.reason or "高级别上涨未完成,禁逆势做空")
        if cfg.use_ma_filter and cfg.ma_veto_short_in_bull and self._ma_state.bull_alignment:
            return "均线多头排列,禁逆势做空"
        if cfg.use_inside_outside and not self._io_state.allow_open_short:
            return f"表里关系:{self._io_state.reason}"
        if cfg.use_fugue and self._fugue.consensus_dir == "up" and self._fugue.aligned:
            return "多重赋格:声部齐奏向上,禁开空"
        if cfg.use_energy and self._energy.divergence_energy and self._energy_down_side():
            return f"能量动力:{self._energy.reason}"
        return "做空门控拒绝"

    def _veto_open_long_reason(self, chan: CChan) -> str:
        cfg = self.config
        if cfg.use_level_linkage:
            attr = self._attribution(is_buy=True)
            if not attr.allow_open:
                if cfg.use_small_turn_big and self._stb_buy.active:
                    return ""
                if cfg.use_zs_oscillation and self._zs_osc.active and self._zs_osc.in_low_band:
                    return ""
                return "级别归属:" + (attr.reason or "高级别下跌未完成,禁逆势做多")
        if cfg.use_ma_filter and cfg.ma_veto_long_in_bear and self._ma_state.bear_alignment:
            return "均线空头排列,禁逆势做多"
        if cfg.use_inside_outside and not self._io_state.allow_open_long:
            return f"表里关系:{self._io_state.reason}"
        if cfg.use_fugue and self._fugue.consensus_dir == "down" and self._fugue.aligned:
            return "多重赋格:声部齐奏向下,禁开多"
        if cfg.use_energy and self._energy.divergence_energy and not self._energy_down_side():
            return f"能量动力:{self._energy.reason}"
        return "做多门控拒绝"

    def check_stop_loss(self, current_price: float) -> Optional[TradeRecord]:
        """
        双向止损检测 (只检测, 不修改内部状态) — 多空非对称
        - 多头: 仅当 stop_loss_long=True 才检测 (默认False → 只靠卖点离场, 让利润奔跑)
        - 空头: 仅当 stop_loss_short=True 才检测 (默认True → 空头亏损无限, 必设防穿仓保护)
        调用方确认可以执行后, 调 apply_stop(record) 提交状态变更。

        【非对称依据】多头最大亏损 100%、且卖点终会出现 → 不必机械止损;
        空头亏损理论无限、单边行情里"顶背驰卖点"迟迟不来 → 必须保留结构止损防穿仓。
        """
        # 多头止损 (默认关闭: 卖点离场)
        if self.config.stop_loss_long and self.long_ratio > 0.001 and self.long_stop > 0:
            if current_price <= self.long_stop:
                return TradeRecord(
                    time="STOP_LOSS", action="SELL", price=current_price,
                    bsp_type="STOP", bsp_level="",
                    position_ratio=-self.long_ratio,
                    reason=f"多头止损 (止损={self.long_stop:.2f})",
                    direction="LONG",
                )


        # 空头止损 (默认开启: 防穿仓)
        if self.config.stop_loss_short and self.short_ratio > 0.001 and self.short_stop > 0:
            if current_price >= self.short_stop:
                return TradeRecord(
                    time="STOP_LOSS", action="COVER", price=current_price,
                    bsp_type="STOP", bsp_level="",
                    position_ratio=-self.short_ratio,
                    reason=f"空头止损 (止损={self.short_stop:.2f})",
                    direction="SHORT",
                )

        return None

    def apply_stop(self, record: TradeRecord):
        """
        提交止损状态变更 (在 check_stop_loss 之后由调用方触发)
        - 若 T+1 阻挡, 调用方可选择不调用此方法, 下一 K 线重新检查
        """
        if record.direction == "LONG":
            self._close_long()
        elif record.direction == "SHORT":
            self._close_short()
        self._set_cooldown()
        self.trade_history.append(record)

    # === 买卖点处理 (多空对称) ===

    def _process_bsp(self, chan: CChan, bsp: CBS_Point) -> Optional[TradeRecord]:
        if BSP_TYPE.T1 in bsp.type or BSP_TYPE.T1P in bsp.type:
            return self._handle_bsp1(chan, bsp)
        if BSP_TYPE.T2 in bsp.type or BSP_TYPE.T2S in bsp.type:
            return self._handle_bsp2(chan, bsp)
        if BSP_TYPE.T3A in bsp.type or BSP_TYPE.T3B in bsp.type:
            return self._handle_bsp3(chan, bsp)
        return None

    def _get_zoushi(self, chan: CChan, bsp: CBS_Point) -> Optional[ZoushiState]:
        """
        取买卖点所在线段的走势类型状态 (第17/18课"走势终完美")
        返回 ZoushiState(类型/是否完美/中枢数/方向)，失败返回 None
        """
        try:
            kl_list = chan[self.config.operating_lv]
            seg_list = kl_list.seg_list
            if len(seg_list) == 0:
                return None
            # 定位买卖点所属线段 (bsp.bi.seg_idx)
            seg_idx = getattr(bsp.bi, "seg_idx", None)
            if seg_idx is not None and 0 <= seg_idx < len(seg_list):
                seg = seg_list[seg_idx]
            else:
                seg = seg_list[-1]
            bsp_conf = chan.conf.bs_point_conf.GetBSConfig(bsp.is_buy)
            return CTrendAnalyzer.analyze(seg, bsp_conf)
        except Exception:
            return None

    def _level_allows_short(self, chan: CChan, lv, bsp_conf) -> bool:
        """
        严格级别门控做空 (兼容旧路径: 指定 short_gate_lv 时启用)

        只在以下两种【明确看空依据】下允许做空, 其余一律禁止:
        - DOWN_TREND: 放大级别处于下跌趋势(≥2同向下跌中枢) → 顺势做空
        - UP_TREND 且 终完美: 放大级别上涨走势背驰完成(真顶) → 反手做空
        禁止做空的情形: 盘整/中枢不足(结构未明)/未定义/上涨但未完美的趋势
        (即"看不清或还在涨, 就不开空")。
        """
        try:
            kl = chan[lv]
            zs_seq = kl.zs_list.zs_lst
            if len(zs_seq) == 0:
                return False  # 高级别无中枢 = 结构未明, 不开空
            zoushi_type, _ = CTrendAnalyzer.classify_by_zs_list(zs_seq, self.config.min_trend_zs)
            if zoushi_type == ZoushiType.DOWN_TREND:
                return True
            if zoushi_type == ZoushiType.UP_TREND:
                return CTrendAnalyzer.is_zoushi_perfect(zs_seq, bsp_conf)
            # CONSOLIDATION/UNDEFINED: 放宽——若该级别最新收盘已跌破最后一个中枢下沿(主动下跌段), 准空
            valid = [z for z in zs_seq if not z.is_one_bi_zs()]
            if valid and len(kl) > 0 and len(kl[-1]) > 0:
                cur_close = kl[-1][-1].close
                if cur_close < valid[-1].low:
                    return True
            return False
        except Exception:
            return False

    def _can_short(self, chan: CChan) -> bool:
        """
        做空门控 — 缠论"级别"解法 (第17/18/24/27课 + 多级别联立 + 均线强弱
        + 两重表里关系 + 多重赋格 + 能量动力)

        【核心】小级别的顶背驰若发生在【更高级别上涨走势未完成】时, 只是大级别
        上涨中的一段次级别回调, 大级别趋势会延续 → 逆势做空必被碾压。故做空须:
          ① 级别联立背书: 跨级别背驰归属判定该卖点被高级别认可(高级别上涨已完美
             或已转下跌趋势), 否则视为次级别回调, 禁做空;
             但⑤小转大已确认(大级别无背驰+次级别顶背驰+结构破坏)时放行早期反转空;
             ⑥中枢震荡高抛区放行区间高抛单;
          ④ 均线强弱: 强势多头排列时禁止逆势做空;
          ⑧ 表里关系: 里级别上涨未完美(表级别反弹=中继)时禁逆势做空;
          ⑨ 多重赋格: 声部共识向上时禁开空;
          ⑩ 能量: 下跌能量背驰(空头力量衰竭)时否决追空。
        兼容旧开关 trend_filter_short / short_gate_lv(单独级别放大确认)。
        """
        cfg = self.config
        self._open_scale = 1.0
        # ① 多级别联立: 跨级别背驰归属
        if cfg.use_level_linkage:
            attr = self._attribution(is_buy=False)
            if not attr.allow_short:
                # ⑤ 小转大: 大级别无背驰但被次级别顶背驰+结构破坏逆转 → 放行(缩仓)
                if cfg.use_small_turn_big and self._stb_sell.active:
                    self._open_scale = cfg.small_turn_big_scale
                # ⑥ 中枢震荡: 区间高抛区允许盘整背驰高抛(震荡市策略)
                elif cfg.use_zs_oscillation and self._zs_osc.active and self._zs_osc.in_high_band:
                    self._open_scale = cfg.zs_osc_scale
                else:
                    return False
        # ④ 均线强弱: 多头排列(强势上涨)禁逆势做空
        if cfg.use_ma_filter and cfg.ma_veto_short_in_bull and self._ma_state.bull_alignment:
            return False
        # ⑧ 两重表里关系: 里级别上涨未完美, 表级别反弹是中继 → 禁逆势做空
        if cfg.use_inside_outside and not self._io_state.allow_open_short:
            return False
        # ⑨ 多重赋格: 声部共识向上 → 禁开空(对位不和)
        if cfg.use_fugue and self._fugue.consensus_dir == "up" and self._fugue.aligned:
            return False
        # ⑩ 能量动力: 下跌侧能量背驰 = 空头力量衰竭, 不追空
        if cfg.use_energy and self._energy.divergence_energy and self._energy_down_side():
            return False
        # 兼容旧路径: 显式 trend_filter_short
        if cfg.trend_filter_short:
            bsp_conf = chan.conf.bs_point_conf.GetBSConfig(False)
            if cfg.short_gate_lv is not None:
                return self._level_allows_short(chan, cfg.short_gate_lv, bsp_conf)
            try:
                kl_list = chan[cfg.operating_lv]
                zs_seq = None
                if hasattr(kl_list, "segzs_list") and len(kl_list.segzs_list.zs_lst) >= cfg.min_trend_zs:
                    zs_seq = kl_list.segzs_list.zs_lst
                elif hasattr(kl_list, "zs_list") and len(kl_list.zs_list.zs_lst) > 0:
                    zs_seq = kl_list.zs_list.zs_lst
                if not zs_seq:
                    return True
                zoushi_type, _ = CTrendAnalyzer.classify_by_zs_list(zs_seq, cfg.min_trend_zs)
                if zoushi_type == ZoushiType.UP_TREND:
                    return CTrendAnalyzer.is_zoushi_perfect(zs_seq, bsp_conf)
                return True
            except Exception:
                return True
        return True

    def _can_open_long(self, chan: CChan) -> bool:
        """
        做多门控 — 与 _can_short 对称 (跨级别背驰归属 + 均线强弱
        + 两重表里关系 + 多重赋格 + 能量动力 + 小转大/中枢震荡放行)

        小级别的底背驰若发生在【更高级别下跌走势未完成】时, 只是大级别下跌中的
        一段次级别反弹 → 逆势做多(接飞刀)风险大; 除非高级别下跌已完美或已转上涨。
        例外: ⑤小转大确认 / ⑥中枢震荡低吸区, 按各自缩放系数放行。
        """
        cfg = self.config
        self._open_scale = 1.0
        if cfg.use_level_linkage:
            attr = self._attribution(is_buy=True)
            if not attr.allow_open:
                # ⑤ 小转大: 大级别无背驰但被次级别底背驰+结构破坏逆转 → 放行(缩仓)
                if cfg.use_small_turn_big and self._stb_buy.active:
                    self._open_scale = cfg.small_turn_big_scale
                # ⑥ 中枢震荡: 区间低吸区允许盘整背驰低吸
                elif cfg.use_zs_oscillation and self._zs_osc.active and self._zs_osc.in_low_band:
                    self._open_scale = cfg.zs_osc_scale
                else:
                    return False
        if cfg.use_ma_filter and cfg.ma_veto_long_in_bear and self._ma_state.bear_alignment:
            return False
        # ⑧ 两重表里关系: 里级别下跌未完美, 表级别反弹是中继 → 禁逆势做多
        if cfg.use_inside_outside and not self._io_state.allow_open_long:
            return False
        # ⑨ 多重赋格: 声部共识向下 → 禁开多(对位不和)
        if cfg.use_fugue and self._fugue.consensus_dir == "down" and self._fugue.aligned:
            return False
        # ⑩ 能量动力: 上涨侧能量背驰 = 多头力量衰竭, 不追多
        if cfg.use_energy and self._energy.divergence_energy and not self._energy_down_side():
            return False
        return True

    def _energy_down_side(self) -> bool:
        """能量背驰发生在下跌侧(空头力量衰竭)还是上涨侧(多头力量衰竭)"""
        return bool(self._energy.divergence_down)

    def _scale_middle_yin(self, ratio: float) -> float:
        """③ 中阴阶段降权: 转折后模糊期对新开仓按系数缩放"""
        if self.config.use_middle_yin and self._middle_yin.in_middle_yin:
            return max(0.0, ratio * self.config.middle_yin_scale)
        return ratio

    def _fugue_boost_ratio(self, ratio: float, want_dir: str) -> float:
        """⑨ 多重赋格齐奏加权: 声部齐奏且与开仓方向一致 → 仓位加权(第40课)"""
        if not self.config.use_fugue:
            return ratio
        if self._fugue.aligned and self._fugue.consensus_dir == want_dir:
            return min(1.0, ratio * self.config.fugue_boost)
        return ratio

    def _should_exit_long(self, chan: CChan, bsp: CBS_Point) -> bool:
        """
        趋势持有 (第24/27课 + 级别联立 + 同级别分解): 持多时, 只有当反转信号
        获得级别背书、且操作级别当前走势类型已完美, 才平多。
        - ① 级别联立: 高级别上涨趋势未完美 → 操作级卖点是次级别回调 → 持有;
        - ② 同级别分解: 当前同级别上涨走势类型未完美 → 持有(不被次级别波动洗出);
        - 关闭以上模块时退化为旧结构判据(中枢新生 / 线段走势未完美)。
        hold_trend_until_perfect=False 时退回"任何卖点即平多"。
        """
        cfg = self.config
        if not cfg.hold_trend_until_perfect:
            return True
        # ⑩ 能量动力(第104课, 许可性): 上涨侧能量背驰=多头力量已衰竭, 允许先于几何卖点离场
        # energy_veto_only 变体关闭此许可性离场(更贴原作: 离场交还几何卖点)
        if cfg.use_energy and not cfg.energy_veto_only and self._energy.divergence_energy and not self._energy_down_side():
            return True
        # ① 跨级别背驰归属: 高级别上涨未完成 → 持有
        if cfg.use_level_linkage:
            attr = self._attribution(is_buy=False)
            if not attr.allow_exit:
                return False
        # ② 同级别分解: 当前上涨走势类型未完美 → 持有
        if cfg.use_same_level_decompose and holding_signal(self._pieces, is_long=True):
            return False
        # ⑧ 两重表里关系(第91/93/99课): 表阴里阳=中继 → 持有; 转折确认 → 放行
        if cfg.use_inside_outside:
            if self._io_state.relation == "pullback":
                return False
            if self._io_state.relation == "reversal_confirm":
                return True
        # ⑨ 多重赋格(第40课): 声部齐奏向上 → 强化持有
        if cfg.use_fugue and self._fugue.aligned and self._fugue.consensus_dir == "up":
            return False
        # 退化路径(未启用级别联立时的旧结构判据)
        if not cfg.use_level_linkage:
            if BSP_TYPE.T1 in bsp.type:
                return True
            if self._trend_continuing_on_operating_lv(chan, up=True):
                return False
            zs = self._get_zoushi(chan, bsp)
            if zs is not None and zs.zoushi_type == ZoushiType.UP_TREND and not zs.is_perfect:
                return False
        return True

    def _should_exit_short(self, chan: CChan, bsp: CBS_Point) -> bool:
        """
        持空时对称: 只有底背驰获级别背书、且操作级别当前下跌走势类型已完美才平空;
        高级别下跌未完成时的买点是次级别反弹, 拿住空单。
        """
        cfg = self.config
        if not cfg.hold_trend_until_perfect:
            return True
        # ⑩ 能量动力(第104课, 许可性): 下跌侧能量背驰=空头力量已衰竭, 允许先于几何买点平空
        # energy_veto_only 变体关闭此许可性平空(更贴原作)
        if cfg.use_energy and not cfg.energy_veto_only and self._energy.divergence_energy and self._energy_down_side():
            return True
        if cfg.use_level_linkage:
            attr = self._attribution(is_buy=True)
            if not attr.allow_exit:
                return False
        if cfg.use_same_level_decompose and holding_signal(self._pieces, is_long=False):
            return False
        # ⑧ 两重表里关系: 里级别下跌未完美, 表级别反弹是中继 → 持空不平
        if cfg.use_inside_outside:
            if self._io_state.relation == "pullback":
                return False
            if self._io_state.relation == "reversal_confirm":
                return True
        # ⑨ 多重赋格: 声部齐奏向下 → 强化持空
        if cfg.use_fugue and self._fugue.aligned and self._fugue.consensus_dir == "down":
            return False
        if not cfg.use_level_linkage:
            if BSP_TYPE.T1 in bsp.type:
                return True
            if self._trend_continuing_on_operating_lv(chan, up=False):
                return False
            zs = self._get_zoushi(chan, bsp)
            if zs is not None and zs.zoushi_type == ZoushiType.DOWN_TREND and not zs.is_perfect:
                return False
        return True


    def _trend_continuing_on_operating_lv(self, chan: CChan, up: bool) -> bool:
        """
        第20课 中枢新生判定: 操作级别最新中枢相对前一个是否同向"新生"(趋势延续)。
        up=True 查上涨新生(newborn_up), up=False 查下跌新生(newborn_down)。
        """
        try:
            kl = chan[self.config.operating_lv]
            rel = CTrendAnalyzer.zs_evolution(kl.zs_list.zs_lst)
            if not rel:
                return False
            return rel[-1] == ('newborn_up' if up else 'newborn_down')
        except Exception:
            return False

    def _handle_bsp1(self, chan: CChan, bsp: CBS_Point) -> Optional[TradeRecord]:
        """
        一类买卖点 (趋势/盘整背驰) — 多空对称 + 走势终完美校验

        原著第17/18/27课:
        - 真正的第一类买卖点 = 趋势(≥2同向中枢)背驰点，走势完成后反转
        - 盘整背驰(单中枢) → T1P，力度较弱
        本方法用 CTrendAnalyzer 显式判定走势类型，只有"下跌趋势已完美"才接受买点T1，
        "上涨趋势已完美"才接受卖点T1，落实"走势终完美、买点买卖点卖"纪律。

        买点 → 平空(如有) + 开多
        卖点 → 平多(如有) + 开空 (反手)
        """
        is_t1p = BSP_TYPE.T1P in bsp.type
        # ⑥ 中枢震荡低吸区: 放行盘整背驰T1P作为高抛低吸的低吸单(第92课)
        osc_absorb = (self.config.use_zs_oscillation and self._zs_osc.active
                      and self._zs_osc.in_low_band and bsp.is_buy)
        osc_dump = (self.config.use_zs_oscillation and self._zs_osc.active
                    and self._zs_osc.in_high_band and not bsp.is_buy)
        if self.config.only_trend_bsp1 and is_t1p and not (osc_absorb or osc_dump):
            return None

        # 走势类型状态机校验 (第17课"走势终完美")
        zoushi = self._get_zoushi(chan, bsp)
        label = "T1(盘整)" if is_t1p else "T1(趋势)"
        zoushi_tag = f" [{zoushi}]" if zoushi is not None else ""

        # 严格模式: 非盘整T1P 的一类买点，必须是"下跌趋势已完美"才成立
        if not is_t1p and zoushi is not None and self.config.only_trend_bsp1:
            if bsp.is_buy:
                # 买点要求前置走势是下跌趋势(或至少非上涨)且已完成
                valid = zoushi.zoushi_type in (ZoushiType.DOWN_TREND, ZoushiType.CONSOLIDATION)
            else:
                # 卖点要求前置走势是上涨趋势(或至少非下跌)且已完成
                valid = zoushi.zoushi_type in (ZoushiType.UP_TREND, ZoushiType.CONSOLIDATION)
            if not valid:
                return None  # 走势类型与买卖点方向不符，放弃

        if bsp.is_buy:
            reason = f"{'盘整' if is_t1p else '趋势'}背驰一类买点{zoushi_tag}"
            # 持空 → 平空(默认不反手); 仅 flip_long=True 才直接开多
            if self.short_ratio > 0.001:
                if not self._should_exit_short(chan, bsp):
                    return None  # 趋势持有: 下跌未完的假买点, 拿住空单
                if self.config.flip_long:
                    return self._execute_flip(chan, bsp, label, reason, to_long=True)
                else:
                    return self._close_short_signal(chan, bsp, label, reason + "(不反手)")
            # 空仓 → 开多
            if self.long_ratio < 0.001:
                # ⑦ 短线反弹(第107课): 急跌窗口内的第一类买点 = 独立小仓位反弹计划
                if (self.config.use_rebound and self.short_ratio < 0.001
                        and self._rebound_plan.setup
                        and self._rebound_planner.entry_allowed(self._rebound_plan, bsp)):
                    return self._open_rebound_long(chan, bsp)
                ratio = self.config.zs_osc_scale if osc_absorb else self.config.position_l1
                return self._open_long(chan, bsp, label, reason, ratio)
        else:
            reason = f"{'盘整' if is_t1p else '趋势'}背驰一类卖点{zoushi_tag}"
            # 持多 → 反手平多开空
            if self.long_ratio > 0.001:
                if not self._should_exit_long(chan, bsp):
                    return None  # 趋势持有: 上涨未完的假卖点, 拿住多单不被洗出
                if self.short_enabled and self.config.flip_short:
                    return self._execute_flip(chan, bsp, label, reason, to_long=False)
                else:
                    return self._close_long_signal(chan, bsp, label, reason)
            # 空仓 → 直接开空
            if self.short_enabled and self.short_ratio < 0.001:
                ratio = self.config.zs_osc_scale if osc_dump else self.config.position_l1
                return self._open_short(chan, bsp, label, reason, ratio)

        return None

    def _handle_bsp2(self, chan: CChan, bsp: CBS_Point) -> Optional[TradeRecord]:
        """
        二类买卖点 (一类后回调/反弹确认)
        
        二类买点 → 做多加仓 / 平空
        二类卖点 → 做空加仓 / 平多
        """
        if bsp.is_buy:
            # 持空 → 平空
            if self.short_ratio > 0.001:
                if not self._should_exit_short(chan, bsp):
                    return None  # 趋势持有: 假买点拿住空单
                return self._close_short_signal(chan, bsp, "T2", "二类买点，空头止盈/反手")
            # 持多轻仓 → 加仓
            if 0 < self.long_ratio < 0.7:
                return self._open_long(chan, bsp, "T2", "二类买点确认，做多加仓", self.config.position_l2)
            # 空仓 → 开多 (二类比一类更安全)
            if self.long_ratio < 0.001:
                return self._open_long(chan, bsp, "T2", "二类买点(一类后回调确认)，直接做多",
                                       self.config.position_l1 + self.config.position_l2)
        else:
            # 持多 → 平多
            if self.long_ratio > 0.001:
                if not self._should_exit_long(chan, bsp):
                    return None  # 趋势持有: 假卖点拿住多单不被洗出
                if self.short_enabled and self.config.flip_short:
                    return self._execute_flip(chan, bsp, "T2", "二类卖点确认，反手做空", to_long=False)
                else:
                    return self._close_long_signal(chan, bsp, "T2", "二类卖点，反弹不过前高，平多")
            # 持空轻仓 → 加仓
            if 0 < self.short_ratio < 0.7:
                return self._open_short(chan, bsp, "T2", "二类卖点确认，做空加仓", self.config.position_l2)
            # 空仓 → 直接开空
            if self.short_enabled and self.short_ratio < 0.001:
                return self._open_short(chan, bsp, "T2", "二类卖点(一类后反弹确认)，直接做空",
                                        self.config.position_l1 + self.config.position_l2)
        return None

    def _handle_bsp3(self, chan: CChan, bsp: CBS_Point) -> Optional[TradeRecord]:
        """
        三类买卖点 (中枢突破回抽确认) — 趋势追入
        
        三类买点 → 重仓做多 (上涨趋势确认)
        三类卖点 → 重仓做空 (下跌趋势确认)
        """
        if bsp.is_buy:
            # 持空 → 平空
            if self.short_ratio > 0.001:
                if not self._should_exit_short(chan, bsp):
                    return None  # 趋势持有: 假买点拿住空单
                return self._close_short_signal(chan, bsp, "T3", "三类买点(中枢上破)，空头止损")
            # 开多/加仓到满仓
            pos = self.config.position_l1 + self.config.position_l2 + self.config.position_l3 - self.long_ratio
            if pos > 0.01:
                return self._open_long(chan, bsp, "T3", "三类买点(中枢上破回抽确认)，趋势做多", pos)
        else:
            # 持多 → 平多+反手
            if self.long_ratio > 0.001:
                if not self._should_exit_long(chan, bsp):
                    return None  # 趋势持有: 假卖点拿住多单不被洗出
                if self.short_enabled and self.config.flip_short:
                    return self._execute_flip(chan, bsp, "T3", "三类卖点(中枢下破)，反手做空", to_long=False)
                else:
                    return self._close_long_signal(chan, bsp, "T3", "三类卖点(中枢下破回抽)，趋势转空平多")
            # 开空/加仓到满仓
            if self.short_enabled:
                pos = self.config.position_l1 + self.config.position_l2 + self.config.position_l3 - self.short_ratio
                if pos > 0.01:
                    return self._open_short(chan, bsp, "T3", "三类卖点(中枢下破回抽确认)，趋势做空", pos)
        return None

    # === 执行层: 开多/开空/平多/平空/反手 ===

    def _fill_close(self, chan: CChan) -> float:
        """确认 bar 的收盘价：所有成交统一按信号被确认的当根收盘价，
        不再取买卖点那根历史极值价 (bsp.klu.close)，以消除未来函数。"""
        return chan[self.config.operating_lv][-1][-1].close

    def _open_long(self, chan, bsp, label, reason, ratio) -> Optional[TradeRecord]:
        """开多/加多 (受做多门控 + 中阴降权 + 门控放行缩放⑤⑥ + 赋格齐奏加权⑨)"""
        if not self._can_open_long(chan):
            return None  # 级别联立: 高级别下跌未完成, 不逆势接飞刀做多
        ratio = self._scale_middle_yin(ratio)  # ③ 中阴阶段降权
        ratio *= self._open_scale              # ⑤小转大/⑥中枢震荡 放行时的仓位缩放
        ratio = self._fugue_boost_ratio(ratio, want_dir="up")
        if ratio <= 0.001:
            return None
        if self.config.require_fx_confirm:
            self._pending_signal = {
                "bsp": bsp, "action": "BUY", "bsp_type_label": label,
                "position_ratio": ratio, "reason": reason,
                "detected_bar": self._bar_count, "is_buy": True,
            }
            return None
        price = self._fill_close(chan)
        stop = self._calc_long_stop(bsp)
        record = TradeRecord(
            time=str(bsp.klu.time), action="BUY", price=price,
            bsp_type=label, bsp_level=str(self.config.operating_lv),
            position_ratio=ratio, reason=reason, stop_loss=stop, direction="LONG",
        )
        self.long_ratio = min(1.0, self.long_ratio + ratio)
        self.long_entry = price
        self.long_stop = stop
        self.trade_history.append(record)
        return record

    def _open_short(self, chan, bsp, label, reason, ratio) -> Optional[TradeRecord]:
        """开空/加空 (受做空门控 + 中阴降权 + 门控放行缩放⑤⑥ + 赋格齐奏加权⑨)"""
        if not self._can_short(chan):
            return None  # 级别联立/均线: 高级别上涨未完成或强势多头排列, 不逆势猜顶做空
        ratio = self._scale_middle_yin(ratio)  # ③ 中阴阶段降权
        ratio *= self._open_scale              # ⑤小转大/⑥中枢震荡 放行时的仓位缩放
        ratio = self._fugue_boost_ratio(ratio, want_dir="down")
        if ratio <= 0.001:
            return None
        if self.config.require_fx_confirm:
            self._pending_signal = {
                "bsp": bsp, "action": "SHORT", "bsp_type_label": label,
                "position_ratio": ratio, "reason": reason,
                "detected_bar": self._bar_count, "is_buy": False,
            }
            return None
        price = self._fill_close(chan)
        stop = self._calc_short_stop(bsp)
        record = TradeRecord(
            time=str(bsp.klu.time), action="SHORT", price=price,
            bsp_type=label, bsp_level=str(self.config.operating_lv),
            position_ratio=ratio, reason=reason, stop_loss=stop, direction="SHORT",
        )
        self.short_ratio = min(1.0, self.short_ratio + ratio)
        self.short_entry = price
        self.short_stop = stop
        self.trade_history.append(record)
        return record

    def _close_long_signal(self, chan, bsp, label, reason) -> TradeRecord:
        """平多"""
        price = self._fill_close(chan)
        record = TradeRecord(
            time=str(bsp.klu.time), action="SELL", price=price,
            bsp_type=label, bsp_level=str(self.config.operating_lv),
            position_ratio=-self.long_ratio, reason=reason, direction="LONG",
        )
        self._close_long()
        self.trade_history.append(record)
        return record

    def _close_short_signal(self, chan, bsp, label, reason) -> TradeRecord:
        """平空"""
        price = self._fill_close(chan)
        record = TradeRecord(
            time=str(bsp.klu.time), action="COVER", price=price,
            bsp_type=label, bsp_level=str(self.config.operating_lv),
            position_ratio=-self.short_ratio, reason=reason, direction="SHORT",
        )
        self._close_short()
        self.trade_history.append(record)
        return record

    def _execute_flip(self, chan, bsp, label, reason, to_long: bool) -> TradeRecord:
        """
        反手: 一个信号内完成 平旧仓+开新仓
        书中"走势终完美" — 一个走势完成就是另一个走势开始
        """
        price = self._fill_close(chan)
        if to_long:
            # 平空 → 开多
            close_record = TradeRecord(
                time=str(bsp.klu.time), action="COVER", price=price,
                bsp_type=label, bsp_level=str(self.config.operating_lv),
                position_ratio=-self.short_ratio, reason=reason + "，空头反手", direction="SHORT",
            )
            self._close_short()
            self.trade_history.append(close_record)
            # 立即开多
            open_record = self._open_long(chan, bsp, label, reason + "，反手做多", self.config.position_l1)
            return open_record or close_record
        else:
            # 平多 → 开空
            close_record = TradeRecord(
                time=str(bsp.klu.time), action="SELL", price=price,
                bsp_type=label, bsp_level=str(self.config.operating_lv),
                position_ratio=-self.long_ratio, reason=reason + "，多头反手", direction="LONG",
            )
            self._close_long()
            self.trade_history.append(close_record)
            # 立即开空
            open_record = self._open_short(chan, bsp, label, reason + "，反手做空", self.config.position_l1)
            return open_record or close_record

    # === 分型确认 (pending signal) ===

    def _try_confirm_pending(self, chan: CChan) -> Optional[TradeRecord]:
        """检查待确认信号是否出现确认分型"""
        if not self._pending_signal:
            return None

        pending = self._pending_signal
        lv_klines = chan[self.config.operating_lv]
        if len(lv_klines) < 3:
            return None

        # 检查最近3根合并K线是否有对应分型
        confirmed = False
        for look_back in range(1, min(4, len(lv_klines))):
            klc = lv_klines[-look_back]
            if pending["is_buy"] and klc.fx == FX_TYPE.BOTTOM:
                confirmed = True
                break
            elif not pending["is_buy"] and klc.fx == FX_TYPE.TOP:
                confirmed = True
                break

        if not confirmed:
            return None

        # 分型确认，执行
        bsp = pending["bsp"]
        price = lv_klines[-1][-1].close  # 用最新价入场
        action = pending["action"]
        ratio = pending["position_ratio"]
        label = pending["bsp_type_label"]
        reason = pending["reason"] + " [分型确认]"

        if action == "BUY":
            # 分型确认时重新校验做多门控: 若这1-3根内高级别转为下跌未完成, 放弃做多
            if not self._can_open_long(chan):
                self._pending_signal = None
                return None
            stop = self._calc_long_stop(bsp)
            record = TradeRecord(
                time=str(bsp.klu.time), action="BUY", price=price,
                bsp_type=label, bsp_level=str(self.config.operating_lv),
                position_ratio=ratio, reason=reason, stop_loss=stop, direction="LONG",
            )
            self.long_ratio = min(1.0, self.long_ratio + ratio)
            self.long_entry = price
            self.long_stop = stop
        elif action == "SHORT":
            # 分型确认时重新校验做空门控: 若这1-3根内趋势转涨, 放弃做空
            if not self._can_short(chan):
                self._pending_signal = None
                return None
            stop = self._calc_short_stop(bsp)
            record = TradeRecord(
                time=str(bsp.klu.time), action="SHORT", price=price,
                bsp_type=label, bsp_level=str(self.config.operating_lv),
                position_ratio=ratio, reason=reason, stop_loss=stop, direction="SHORT",
            )
            self.short_ratio = min(1.0, self.short_ratio + ratio)
            self.short_entry = price
            self.short_stop = stop
        elif action == "SELL":
            record = TradeRecord(
                time=str(bsp.klu.time), action="SELL", price=price,
                bsp_type=label, bsp_level=str(self.config.operating_lv),
                position_ratio=-self.long_ratio, reason=reason, direction="LONG",
            )
            self._close_long()
        elif action == "COVER":
            record = TradeRecord(
                time=str(bsp.klu.time), action="COVER", price=price,
                bsp_type=label, bsp_level=str(self.config.operating_lv),
                position_ratio=-self.short_ratio, reason=reason, direction="SHORT",
            )
            self._close_short()
        else:
            return None

        self.trade_history.append(record)
        return record

    # === 辅助 ===

    def _calc_long_stop(self, bsp: CBS_Point) -> float:
        """多头止损: 笔低点下方"""
        return bsp.bi._low() * (1 - self.config.stop_buffer)

    def _calc_short_stop(self, bsp: CBS_Point) -> float:
        """空头止损: 笔高点上方"""
        return bsp.bi._high() * (1 + self.config.stop_buffer)

    def _open_rebound_long(self, chan, bsp) -> Optional[TradeRecord]:
        """
        ⑦ 短线反弹入场 (第107课) — 独立小仓位计划:
        急跌窗口内的第一类买点轻仓参与, 目标位=上方压力, 止损位=窗口最低价,
        到位/破位机械离场(见 on_bar 中的 _rebound_pos 管理)。
        该路径刻意【绕过趋势门控】(级别联立/表里关系/均线), 因为抢反弹本身就是
        逆里级别大势的短线交易, 靠小仓位+目标/止损纪律控制风险。
        """
        plan = self._rebound_plan
        ratio = max(0.0, min(1.0, self.config.rebound_scale))
        if ratio <= 0.001:
            return None
        price = self._fill_close(chan)
        reason = (f"短线反弹买点(急跌{plan.drop_pct:.1f}%/{plan.drop_bars}K后), "
                  f"目标{plan.target_price:.2f} 止损{plan.stop_price:.2f}")
        record = TradeRecord(
            time=str(bsp.klu.time), action="BUY", price=price,
            bsp_type="RB(107课)", bsp_level=str(self.config.operating_lv),
            position_ratio=ratio, reason=reason, stop_loss=plan.stop_price,
            direction="LONG",
        )
        self.long_ratio = min(1.0, self.long_ratio + ratio)
        self.long_entry = price
        self.long_stop = plan.stop_price
        self._rebound_pos = {"target": plan.target_price, "stop": plan.stop_price}
        self.trade_history.append(record)
        return record

    def _manage_rebound_pos(self, chan: CChan) -> Optional[TradeRecord]:
        """⑦ 短线反弹持仓管理: 到目标位或破止损位 → 机械离场(每根K线检查)"""
        if not (self.config.use_rebound and self._rebound_pos and self.long_ratio > 0.001):
            return None
        try:
            last_klu = chan[self.config.operating_lv][-1][-1]
            cur_close, cur_time = last_klu.close, str(last_klu.time)
        except Exception:
            return None
        if cur_close >= self._rebound_pos["target"]:
            reason = f"短线反弹到达目标位{self._rebound_pos['target']:.2f}, 机械离场"
        elif cur_close <= self._rebound_pos["stop"]:
            reason = f"短线反弹跌破止损位{self._rebound_pos['stop']:.2f}, 认赔离场"
        else:
            return None
        record = TradeRecord(
            time=cur_time, action="SELL", price=cur_close,
            bsp_type="RB-EXIT", bsp_level=str(self.config.operating_lv),
            position_ratio=-self.long_ratio, reason=reason, direction="LONG",
        )
        self._close_long()
        self.trade_history.append(record)
        return record

    def _close_long(self):
        self.long_ratio = 0.0
        self.long_entry = 0.0
        self.long_stop = 0.0
        self._rebound_pos = None

    def _close_short(self):
        self.short_ratio = 0.0
        self.short_entry = 0.0
        self.short_stop = 0.0

    def _set_cooldown(self):
        self._cooldown_until = self._bar_count + self.config.cooldown_bars


class ChanNestedStrategy:
    """
    区间套策略 (原著第21课《缠中说禅买卖点的完备性》核心操作技术)

    【原文出处】第21课：
      "用 MACD 辅助判断，背驰点精确定位靠区间套。比如日线级别的背驰，
       可以在日线背驰段内，用 30 分钟级别找它的背驰点；30 分钟的背驰段内，
       再用 5 分钟找背驰……层层夹逼，最后定位到最低级别的那个转折点，
       这个点就是精确的买卖点。"

    【算法实现思路】
    1. 高级别(operating_lv, 如日线)出现买卖点 → 确定走势方向和转折时间窗；
    2. 依次下钻每个次级别(nested_lv, 如30分→5分)：在该级别中，找出方向一致、
       且时间落在"上一层转折点"之前的最后一个背驰买卖点，作为更精确的入场点；
    3. 用这一层的时间点收紧下一层的搜索上界，实现"层层夹逼"；
    4. 最终最低级别命中的买卖点价格 = 精确入场价，级别路径记录在 bsp_level。

    与旧实现区别: 旧版只取"次级别最新价"，非真正区间套；本版严格按背驰点逐层收敛。
    """

    def __init__(self, config: StrategyConfig = None, market_cap=None):
        if config is None:
            config = StrategyConfig()
        self.config = config
        self.market_cap = market_cap
        self.base_strategy = ChanStrategy(config, market_cap=market_cap)

    @property
    def trade_history(self) -> List[TradeRecord]:
        """委托给基础策略 (回测器需要访问)"""
        return self.base_strategy.trade_history

    @property
    def bsp_decisions(self) -> List["BspDecision"]:
        """委托给基础策略的结构买卖点决策记录"""
        return self.base_strategy.bsp_decisions

    @property
    def short_enabled(self) -> bool:
        return self.base_strategy.short_enabled

    def check_stop_loss(self, current_price: float) -> Optional[TradeRecord]:
        """委托给基础策略的双向止损检测"""
        return self.base_strategy.check_stop_loss(current_price)

    def apply_stop(self, record):
        """委托给基础策略提交止损状态"""
        return self.base_strategy.apply_stop(record)

    def _get_high_bsp(self, chan: CChan, is_buy: bool):
        """取高级别(operating_lv)最后一个同向买卖点对象(其 bi 即背驰段)"""
        try:
            kl = chan[self.config.operating_lv]
            for b in reversed(kl.bs_point_lst.lst):
                if b.is_buy == is_buy:
                    return b
        except Exception:
            pass
        return None

    @staticmethod
    def _bsp_window(bsp):
        """取一个买卖点的背驰段时间窗 [begin_ts, end_ts](其 bi 笔的时间跨度)"""
        try:
            lo = bsp.bi.get_begin_klu().time.ts
            hi = bsp.bi.get_end_klu().time.ts
            return (min(lo, hi), max(lo, hi))
        except Exception:
            return None

    def _nested_locate(self, chan: CChan, record: TradeRecord):
        """
        第21课真·区间套: 父背驰段时间窗内, 递归找子级别背驰段, 层层夹逼

        1. 高级别最后同向 BSP 的 bi = 父背驰段, 得时间窗 [w_lo, w_hi]
        2. 依次下钻每个次级别: 在该级别找【时间落进当前窗】且同向的最后一个背驰 BSP
        3. 用该子 BSP 的 bi 时间跨度收紧窗口, 递归到更低级别
        4. 最深命中的子背驰点 = 精确入场价/时间
        """
        target_is_buy = (record.action == "BUY")
        precise_price = record.price
        precise_time = record.time
        level_path: List[str] = []

        hi_bsp = self._get_high_bsp(chan, target_is_buy)
        win = self._bsp_window(hi_bsp) if hi_bsp is not None else None
        if win is None:
            return precise_price, precise_time, level_path  # 退化: 无父背驰段, 保持原价

        w_lo, w_hi = win
        for sub_lv in self.config.nested_lv:
            try:
                sub_kl = chan[sub_lv]
            except Exception:
                continue
            if len(sub_kl) == 0 or not hasattr(sub_kl, "bs_point_lst"):
                continue

            # 在该次级别中找: 方向一致 + 时间落进[父背驰段窗口] 的最后一个背驰 BSP
            matched = None
            for b in reversed(sub_kl.bs_point_lst.lst):
                if b.is_buy != target_is_buy:
                    continue
                t = b.klu.time.ts
                if t < w_lo or t > w_hi:
                    continue  # 不在父背驰段内, 不是本轮区间套的子背驰
                matched = b
                break

            if matched is None:
                continue  # 该级别无子背驰, 保持上一层结果继续试更低级别

            sub_win = self._bsp_window(matched)
            precise_price = sub_kl[-1][-1].close  # 用当前次级别收盘价，不用历史极值价(未来函数)
            precise_time = str(matched.klu.time)
            level_path.append(f"{sub_lv.name}@{precise_time[:10]}")
            if sub_win is not None:
                w_lo, w_hi = sub_win  # 收紧窗口, 下一层在子背驰段内继续夹逼

        return precise_price, precise_time, level_path

    def on_bar(self, chan: CChan) -> Optional[TradeRecord]:
        """
        区间套处理:
        1. 基础策略产生高级别买卖点信号 (含 pending 分型确认)
        2. 若是开仓动作(BUY/SHORT)且配置了次级别 → 逐层背驰夹逼精确定位入场
        """
        record = self.base_strategy.on_bar(chan)
        if record is None:
            return None

        if record.action in ("BUY", "SHORT") and self.config.nested_lv and len(chan.lv_list) > 1:
            precise_price, precise_time, level_path = self._nested_locate(chan, record)
            if level_path:
                record.price = precise_price
                record.time = precise_time
                record.bsp_level += "+区间套[" + "→".join(level_path) + "]"

        return record
