"""
多级别联立 + 跨级别背驰归属 — 缠论"级别"的操作化

【原文出处】《市场哲学的数学原理》(缠中说禅)
  - 第16课《中小资金的高效买卖法》、第21课区间套: 多级别联立是操作前提，
    级别从大到小递归(月→周→日→30分…)，高级别定方向、低级别定精确点。
  - 第17/18课: 走势中枢与走势类型的级别定义 —— 一个级别的"背驰完成"，
    在更高级别看来可能只是一次次级别回调。
  - 第24/27课: 背驰(走势终完美)必须"归属"到它所在的级别；级别不同，
    同一个背驰信号的操作含义完全不同。

【为什么需要"级别归属"】
  低级别(如日线)出现的顶背驰，如果发生在更高级别(周线/月线)上涨走势
  【尚未完成】的阶段，那它只是大级别上涨中的一段次级别回调，大级别趋势
  会继续 —— 此时按日线卖点平多/做空就是被"假卖点"洗出、逆大势开空。
  反之，若高级别上涨走势本身也已完美(高级别顶背驰)，日线卖点才是真反转。

【算法实现思路】
  1. MultiLevelContext.update(chan): 对 lv_list 中每个级别，取其笔中枢序列
     zs_list，用 CTrendAnalyzer.classify_by_zs_list 得到走势类型(趋势/盘整/
     未完成)，用 is_zoushi_perfect 得到"是否终完美"，汇成 LevelState。
  2. attribute_reversal(is_buy): 跨级别背驰归属 —— 对操作级别的一个反转信号，
     自高向低扫描"更高级别"，判断该反转真正归属哪一级别、是否被高级别背书:
       - 高级别同向趋势未完成(逆势)  → 归属=次级别回调, 不背书 → 持有/禁反手;
       - 高级别走势已完美 或 已转同向趋势 → 背书 → 允许离场/顺势开仓;
       - 高级别盘整/未完成(方向不明) → 回落到操作级别自身判定。
  3. 输出 ReversalAttribution，供策略层统一决定 allow_exit / allow_short /
     allow_open，把"级别"真正变成可执行的操作纪律。

  单级别(lv_list 只有操作级别)时 higher_levels 为空，归属逻辑自动退化为
  "只看操作级别自身完美与否"，与旧行为兼容。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from Common.CEnum import KL_TYPE
from Trend.TrendAnalyzer import CTrendAnalyzer, ZoushiType


@dataclass
class LevelState:
    """单个级别的走势类型状态快照"""
    lv: KL_TYPE
    zoushi_type: ZoushiType = ZoushiType.UNDEFINED
    is_perfect: bool = False
    zs_count: int = 0
    divergence_ratio: Optional[float] = None
    last_close: Optional[float] = None
    last_zs_low: Optional[float] = None
    last_zs_high: Optional[float] = None

    @property
    def is_up_trend(self) -> bool:
        return self.zoushi_type == ZoushiType.UP_TREND

    @property
    def is_down_trend(self) -> bool:
        return self.zoushi_type == ZoushiType.DOWN_TREND

    def __str__(self):
        name = {
            ZoushiType.UP_TREND: "上涨趋势",
            ZoushiType.DOWN_TREND: "下跌趋势",
            ZoushiType.CONSOLIDATION: "盘整",
            ZoushiType.UNDEFINED: "未完成",
        }[self.zoushi_type]
        return f"{self.lv.name}:{name}({self.zs_count}中枢{'·完美' if self.is_perfect else ''})"


@dataclass
class ReversalAttribution:
    """一个操作级别反转信号的跨级别归属结论"""
    is_buy: bool                       # True=考虑做多/平空的买点; False=卖点
    effective_lv: KL_TYPE              # 背驰真正归属的级别
    endorsed_by_higher: bool           # 是否被更高级别背书
    higher_active_trend: Optional[str] # 更高级别进行中的趋势方向 'up'/'down'/None
    higher_perfect: bool               # 更高级别同向走势是否已完美
    allow_exit: bool                   # 是否允许按此信号平掉顺势仓位
    allow_open: bool                   # 是否允许按此信号开新仓(顺势方向)
    allow_short: bool                  # 是否允许做空(仅对卖点有意义)
    reason: str = ""
    level_trace: List[str] = field(default_factory=list)


class MultiLevelContext:
    """
    多级别联立上下文 — 每根 K 线更新一次，缓存各级别走势状态与归属结论。

    参数:
      lv_list      : 全部级别(从大到小, 如 [K_MON, K_WEEK, K_DAY])
      operating_lv : 操作级别(信号产生级别, 通常是 lv_list 最小级别)
      min_trend_zs : 判定"趋势"所需的最少同向中枢数(书中定义趋势=≥2中枢)
    """

    def __init__(self, lv_list: List[KL_TYPE], operating_lv: KL_TYPE, min_trend_zs: int = 2):
        self.lv_list = list(lv_list) if lv_list else [operating_lv]
        self.operating_lv = operating_lv
        self.min_trend_zs = min_trend_zs
        self.states: Dict[KL_TYPE, LevelState] = {}

    # --- 更高级别(比操作级别大) 列表, 从大到小 ---
    def higher_levels(self) -> List[KL_TYPE]:
        return [lv for lv in self.lv_list if self._rank(lv) > self._rank(self.operating_lv)]

    @staticmethod
    def _rank(lv: KL_TYPE) -> int:
        order = {
            KL_TYPE.K_1M: 1, KL_TYPE.K_3M: 2, KL_TYPE.K_5M: 3, KL_TYPE.K_15M: 4,
            KL_TYPE.K_30M: 5, KL_TYPE.K_60M: 6, KL_TYPE.K_DAY: 7, KL_TYPE.K_WEEK: 8,
            KL_TYPE.K_MON: 9, KL_TYPE.K_QUARTER: 10, KL_TYPE.K_YEAR: 11,
        }
        return order.get(lv, 0)

    def update(self, chan, bsp_conf) -> "MultiLevelContext":
        """
        扫描每个级别, 计算 LevelState。bsp_conf 用于走势终完美(背驰)判定,
        传买点或卖点配置皆可(此处只做结构/力度是否衰竭的对称判断)。
        """
        self.states = {}
        for lv in self.lv_list:
            self.states[lv] = self._analyze_level(chan, lv, bsp_conf)
        return self

    def _analyze_level(self, chan, lv: KL_TYPE, bsp_conf) -> LevelState:
        st = LevelState(lv=lv)
        try:
            kl = chan[lv]
        except Exception:
            return st
        # 最新价
        try:
            if len(kl) > 0 and len(kl[-1]) > 0:
                st.last_close = kl[-1][-1].close
        except Exception:
            pass
        # 笔中枢序列 → 走势类型
        try:
            zs_seq = kl.zs_list.zs_lst
            valid = [z for z in zs_seq if not z.is_one_bi_zs()]
            st.zs_count = len(valid)
            if valid:
                st.last_zs_low = valid[-1].low
                st.last_zs_high = valid[-1].high
            zoushi_type, _ = CTrendAnalyzer.classify_by_zs_list(zs_seq, self.min_trend_zs)
            st.zoushi_type = zoushi_type
            # 终完美: 末中枢离开段背驰
            ratio = self._perfect_ratio(valid, bsp_conf)
            if ratio is not None:
                st.divergence_ratio = ratio
                st.is_perfect = True
        except Exception:
            pass
        return st

    @staticmethod
    def _perfect_ratio(valid_zs, bsp_conf) -> Optional[float]:
        """末中枢离开段是否背驰; 背驰返回比值, 否则 None"""
        if not valid_zs:
            return None
        last_zs = valid_zs[-1]
        if last_zs.bi_out is None:
            return None
        try:
            is_diver, ratio = last_zs.is_divergence(bsp_conf)
            return ratio if is_diver else None
        except Exception:
            return None

    def state(self, lv: KL_TYPE) -> Optional[LevelState]:
        return self.states.get(lv)

    def operating_state(self) -> Optional[LevelState]:
        return self.states.get(self.operating_lv)

    def attribute_reversal(self, is_buy: bool) -> ReversalAttribution:
        """
        跨级别背驰归属 — 决定一个操作级别反转信号能否被执行。

        is_buy=True : 这是一个"看涨反转"(下跌背驰买点) → 关心高级别是否还在下跌;
        is_buy=False: 这是一个"看跌反转"(上涨背驰卖点) → 关心高级别是否还在上涨。

        规则(自高向低扫描更高级别):
          - 若存在更高级别处于【与信号相反方向的趋势且未完美】
            (买点遇到高级别下跌趋势未完 / 卖点遇到高级别上涨趋势未完) —— 说明大级别
            顺势仍在进行, 该操作级信号只是次级别回调 → 不背书: 不许开逆势新仓、
            不许据此平掉顺势仓(持有)、卖点时禁止做空。
          - 若更高级别【同向走势已完美】或【已转为信号方向的趋势】 → 背书: 放行。
          - 若更高级别只是盘整/未完成(方向不明) → 回落到操作级别自身完美判定。
        """
        attr = ReversalAttribution(
            is_buy=is_buy, effective_lv=self.operating_lv,
            endorsed_by_higher=False, higher_active_trend=None, higher_perfect=False,
            allow_exit=True, allow_open=True, allow_short=not is_buy,
        )
        op = self.operating_state()
        if op is not None:
            attr.level_trace.append(str(op))

        # 信号方向: 买点看涨(up), 卖点看跌(down)
        signal_dir = "up" if is_buy else "down"
        # 与信号相反的高级别趋势 = 阻挡
        blocking = ZoushiType.DOWN_TREND if is_buy else ZoushiType.UP_TREND
        endorsing = ZoushiType.UP_TREND if is_buy else ZoushiType.DOWN_TREND

        for lv in self.higher_levels():
            hst = self.states.get(lv)
            if hst is None:
                continue
            attr.level_trace.append(str(hst))

            if hst.zoushi_type == blocking:
                if not hst.is_perfect:
                    # 高级别逆势趋势仍在进行 → 操作级信号降级为次级别回调
                    attr.effective_lv = self.operating_lv
                    attr.endorsed_by_higher = False
                    attr.higher_active_trend = "down" if is_buy else "up"
                    attr.allow_exit = False      # 顺势仓(多/空)不被假反转洗出
                    attr.allow_open = False      # 不开逆势新仓
                    attr.allow_short = is_buy    # 卖点且高级别上涨未完 → 禁做空; 买点场景允许平空
                    attr.reason = (
                        f"{lv.name}级别{'下跌' if is_buy else '上涨'}趋势未完成，"
                        f"操作级别背驰归属为次级别回调，持有不逆势"
                    )
                    return attr
                else:
                    # 高级别逆势趋势已完美 → 转折成立, 背书
                    attr.higher_perfect = True
            elif hst.zoushi_type == endorsing:
                # 高级别已转同向趋势 → 强背书
                attr.higher_active_trend = signal_dir
                attr.endorsed_by_higher = True
            # CONSOLIDATION / UNDEFINED: 方向不明, 继续看更高级别或回落

        # 没有任何高级别阻挡: 若某高级别已完美则背书, 否则回落操作级别自身
        if attr.higher_perfect:
            attr.endorsed_by_higher = True
            attr.effective_lv = self.higher_levels()[0] if self.higher_levels() else self.operating_lv
            attr.reason = "更高级别同向走势已完美(高级别背驰)，转折获级别背书"
        elif op is not None and op.is_perfect:
            attr.reason = "操作级别走势已完美(本级别背驰)，按操作级别执行"
        else:
            attr.reason = "高级别方向不明，回落操作级别自身走势判定"
        return attr
