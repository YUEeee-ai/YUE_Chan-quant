"""
走势类型状态机 — 缠论"走势终完美"的显式实现

【原文出处】
《市场哲学的数学原理》(缠中说禅)：
- 第17课《走势中枢定义再研究》：走势中枢 = 某级别走势类型中，被至少三个连续
  次级别走势类型所重叠的部分。
- 第18课《走势中枢的级别与走势类型》：
    · 盘整 = 只包含一个走势中枢的走势类型；
    · 趋势 = 至少包含两个同向、且互不重叠的走势中枢的走势类型
      （上涨趋势：中枢依次抬高；下跌趋势：中枢依次降低）。
- 第20课《缠中说禅走势中枢定义》：走势中枢的延伸、扩展、新生。
- 第24课《MACD对背弛的辅助判断》+ 第27课：
    · 走势终完美 = 任何级别的任何走势类型终要完成，完成后必然转化为其他走势类型；
    · 趋势背驰：趋势中最后一个中枢的"离开段"力度 < "进入段"力度 → 走势完成；
    · 盘整背驰：单中枢的离开段背驰 → 盘整完成。

【算法实现思路】
1. classify(seg)：统计一个线段内的有效中枢(排除单笔中枢)数量与排列：
     0个 → UNDEFINED(走势未完成)；1个 → CONSOLIDATION(盘整)；
     ≥2个且相邻中枢不重叠并依次抬高/降低 → UP_TREND/DOWN_TREND(趋势)；
     ≥2个但有重叠 → CONSOLIDATION(中枢扩展，视为更大级别盘整)。
2. is_perfect(seg, config)：走势终完美判定 —— 取最后一个多笔中枢，
     若其离开段背驰(is_divergence) → 该走势类型完成(PERFECT)。
3. analyze(seg, config)：返回 ZoushiState(类型 + 是否完美 + 中枢数 + 方向)，
     供策略层做"只在走势完成时入场"的纪律控制(买点买、卖点卖，不测而测)。
"""
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional


class ZoushiType(Enum):
    """走势类型 (原著第18课)"""
    UP_TREND = auto()       # 上涨趋势: ≥2个依次抬高且不重叠的中枢
    DOWN_TREND = auto()     # 下跌趋势: ≥2个依次降低且不重叠的中枢
    CONSOLIDATION = auto()  # 盘整: 恰好1个中枢, 或多中枢重叠(扩展)
    UNDEFINED = auto()      # 走势未完成: 尚无有效中枢


class ZoushiStatus(Enum):
    """走势完成状态 (原著"走势终完美")"""
    PERFECT = auto()        # 已完美(完成): 末中枢离开段背驰
    IMPERFECT = auto()      # 未完美(进行中)


@dataclass
class ZoushiState:
    """一个走势类型的完整状态描述"""
    zoushi_type: ZoushiType
    status: ZoushiStatus
    zs_count: int           # 有效中枢数(排除单笔中枢)
    direction: str          # "up" / "down" / "" (盘整/未定义)
    divergence_ratio: Optional[float] = None  # 末中枢背驰比 out/in

    @property
    def is_perfect(self) -> bool:
        return self.status == ZoushiStatus.PERFECT

    @property
    def is_trend(self) -> bool:
        return self.zoushi_type in (ZoushiType.UP_TREND, ZoushiType.DOWN_TREND)

    def __str__(self):
        type_name = {
            ZoushiType.UP_TREND: "上涨趋势",
            ZoushiType.DOWN_TREND: "下跌趋势",
            ZoushiType.CONSOLIDATION: "盘整",
            ZoushiType.UNDEFINED: "未完成",
        }[self.zoushi_type]
        status_name = "已完美" if self.is_perfect else "进行中"
        return f"{type_name}({self.zs_count}中枢,{status_name})"


class CTrendAnalyzer:
    """
    走势类型分析器 — 静态方法集合，输入 CSeg(线段)，输出走势类型状态。

    既可用于笔线段(seg.zs_lst 为笔中枢)，也可用于"线段的线段"(seg.zs_lst 为段中枢)，
    因为 CSeg 是泛型递归结构。
    """

    @staticmethod
    def _valid_zs_list(seg) -> List:
        """取线段内所有有效中枢(排除单笔中枢 one_bi_zs)"""
        return [zs for zs in seg.zs_lst if not zs.is_one_bi_zs()]

    @staticmethod
    def classify(seg) -> ZoushiType:
        """
        走势类型分类 (原著第18课)
        - 0 中枢 → UNDEFINED
        - 1 中枢 → CONSOLIDATION (盘整)
        - ≥2 不重叠同向中枢 → UP_TREND / DOWN_TREND (趋势)
        - ≥2 但有重叠 → CONSOLIDATION (中枢扩展，视为更大级别盘整)
        """
        zs_list = CTrendAnalyzer._valid_zs_list(seg)
        if len(zs_list) == 0:
            return ZoushiType.UNDEFINED
        if len(zs_list) == 1:
            return ZoushiType.CONSOLIDATION

        # 判断相邻中枢是否不重叠且方向一致
        up_trend = True
        down_trend = True
        for i in range(len(zs_list) - 1):
            cur, nxt = zs_list[i], zs_list[i + 1]
            # 上涨趋势: 后中枢低点 > 前中枢高点 (完全抬高，不重叠)
            if not (nxt.low > cur.high):
                up_trend = False
            # 下跌趋势: 后中枢高点 < 前中枢低点 (完全降低，不重叠)
            if not (nxt.high < cur.low):
                down_trend = False

        if up_trend:
            return ZoushiType.UP_TREND
        if down_trend:
            return ZoushiType.DOWN_TREND
        # 中枢有重叠 → 盘整/中枢扩展
        return ZoushiType.CONSOLIDATION

    @staticmethod
    def direction_of(seg) -> str:
        """走势方向 (供策略判断多空)"""
        zt = CTrendAnalyzer.classify(seg)
        if zt == ZoushiType.UP_TREND:
            return "up"
        if zt == ZoushiType.DOWN_TREND:
            return "down"
        # 盘整/未完成: 用线段自身方向兜底
        if hasattr(seg, "is_down"):
            return "down" if seg.is_down() else "up"
        return ""

    @staticmethod
    def is_perfect(seg, bsp_config) -> bool:
        """
        走势终完美判定 (原著第24/27课)
        取线段最后一个多笔中枢，若其离开段背驰 → 走势完成。
        bsp_config: CPointConfig (提供 macd_algo / divergence_rate)
        """
        zs_list = CTrendAnalyzer._valid_zs_list(seg)
        if len(zs_list) == 0:
            return False
        last_zs = zs_list[-1]
        if last_zs.bi_out is None:
            return False
        try:
            is_diver, _ = last_zs.is_divergence(bsp_config)
            return bool(is_diver)
        except Exception:
            return False

    @staticmethod
    def analyze(seg, bsp_config=None) -> ZoushiState:
        """完整分析一个线段的走势类型状态"""
        zt = CTrendAnalyzer.classify(seg)
        zs_count = len(CTrendAnalyzer._valid_zs_list(seg))
        direction = CTrendAnalyzer.direction_of(seg)

        status = ZoushiStatus.IMPERFECT
        ratio = None
        if bsp_config is not None and zs_count > 0:
            last_zs = CTrendAnalyzer._valid_zs_list(seg)[-1]
            if last_zs.bi_out is not None:
                try:
                    is_diver, ratio = last_zs.is_divergence(bsp_config)
                    if is_diver:
                        status = ZoushiStatus.PERFECT
                except Exception:
                    pass

        return ZoushiState(
            zoushi_type=zt,
            status=status,
            zs_count=zs_count,
            direction=direction,
            divergence_ratio=ratio,
        )

    # === 中枢序列级别分析 (正确粒度: 走势类型跨多个中枢, 用于"级别放大"确认) ===

    @staticmethod
    def classify_by_zs_list(zs_seq, min_trend_zs: int = 2):
        """
        从【中枢序列】判断当前走势类型 (原著第18课: 趋势=≥2同向不重叠中枢)

        与 classify(seg) 的区别: classify 看单个线段内的中枢(通常0-1个, 粒度太细);
        本方法看整个级别的中枢序列(zs_list.zs_lst 或 放大级别的 segzs_list.zs_lst),
        从最后一个中枢往前数"连续同向且不重叠"的中枢个数, 才是走势类型的正确粒度。

        返回: (ZoushiType, last_zs)
        """
        valid = [zs for zs in zs_seq if not zs.is_one_bi_zs()]
        if len(valid) == 0:
            return ZoushiType.UNDEFINED, None
        last_zs = valid[-1]
        if len(valid) < min_trend_zs:
            return ZoushiType.CONSOLIDATION, last_zs

        # 从末尾往前数连续上移(后中枢完全在前中枢之上)的中枢个数
        up_cnt = 1
        for i in range(len(valid) - 1, 0, -1):
            if valid[i].low > valid[i - 1].high:
                up_cnt += 1
            else:
                break
        # 从末尾往前数连续下移(后中枢完全在前中枢之下)的中枢个数
        down_cnt = 1
        for i in range(len(valid) - 1, 0, -1):
            if valid[i].high < valid[i - 1].low:
                down_cnt += 1
            else:
                break

        if up_cnt >= min_trend_zs:
            return ZoushiType.UP_TREND, last_zs
        if down_cnt >= min_trend_zs:
            return ZoushiType.DOWN_TREND, last_zs
        return ZoushiType.CONSOLIDATION, last_zs

    @staticmethod
    def is_zoushi_perfect(zs_seq, bsp_config) -> bool:
        """
        走势终完美判定 (中枢序列版): 最后一个中枢的离开段背驰 → 走势完成。
        用于"级别放大"确认: 放大级别走势已完美, 小级别背驰才是真反转。
        """
        valid = [zs for zs in zs_seq if not zs.is_one_bi_zs()]
        if len(valid) == 0:
            return False
        last_zs = valid[-1]
        if last_zs.bi_out is None:
            return False
        try:
            is_diver, _ = last_zs.is_divergence(bsp_config)
            return bool(is_diver)
        except Exception:
            return False

    # === 中枢级别扩张: 新生 / 扩展 / 延伸 (原著第20课) ===

    @staticmethod
    def zs_relation(prev_zs, next_zs) -> str:
        """
        判断相邻两个中枢的演化关系 (第20课《缠中说禅走势中枢级别扩张及第三类买卖点》)

        缠师原文: 中枢有三种演化 ——
          - 延伸: 同一中枢区间内震荡, 笔数增加(9段以内), 区间不变;
          - 扩展: 相邻两中枢【区间重叠】(没出现第三类买卖点), 合并成更大级别中枢 → 盘整扩大;
          - 新生: 出现【第三类买卖点】→ 旧中枢结束, 新方向长出新中枢 → 这才是趋势延续。
        本方法区分"新生(不重叠)"与"扩展(重叠)":
          - 后中枢完全在前之上 → 'newborn_up'(上涨趋势延续)
          - 后中枢完全在前之下 → 'newborn_down'(下跌趋势延续)
          - 区间重叠 → 'expansion'(中枢扩展, 转更大级别盘整)
        """
        from Common.FuncUtil import has_overlap
        if has_overlap(prev_zs.low, prev_zs.high, next_zs.low, next_zs.high, equal=True):
            return 'expansion'
        if next_zs.low > prev_zs.high:
            return 'newborn_up'
        if next_zs.high < prev_zs.low:
            return 'newborn_down'
        return 'expansion'

    @staticmethod
    def zs_evolution(zs_seq):
        """返回相邻中枢演化关系序列 (第20课)"""
        valid = [z for z in zs_seq if not z.is_one_bi_zs()]
        return [CTrendAnalyzer.zs_relation(valid[i - 1], valid[i]) for i in range(1, len(valid))]

    @staticmethod
    def is_trend_continuing(zs_seq) -> bool:
        """
        当前是否处于"趋势延续"(中枢连续新生、不重叠同向) —— 第20课。
        用于趋势持有: 只要最新中枢相对前一个是同向'新生'(没出现扩展/重叠),
        说明趋势还在生长、顶/底未真正完成 → 不应被小级别假卖点洗出。
        """
        rel = CTrendAnalyzer.zs_evolution(zs_seq)
        if not rel:
            return False
        return rel[-1] in ('newborn_up', 'newborn_down')
