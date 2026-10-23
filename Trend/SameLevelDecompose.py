"""
同级别分解 — 缠论核心操作方法

【原文出处】《市场哲学的数学原理》(缠中说禅) 第37/38课《走势的同级别分解》:
  固定一个操作级别，把整段走势分解成一串【同级别的走势类型】(盘整或趋势)，
  每个走势类型"终完美"后必然接下一个走势类型；操作只在走势类型的边界(买卖点)
  上进行，而不必在每一个次级别波动里做递归判断。

【为什么需要同级别分解】
  级别递归(区间套)精度高但复杂、且低级别噪声多。同级别分解提供另一条正交路径:
  把注意力锁死在"操作级别这一段走势类型是否完成"，只要当前这段(比如日线的一段
  上涨趋势)没有完美，中途的次级别回调/盘整都不构成离场理由 —— 这正是"不被假卖点
  洗出"的可执行判据。

【算法实现思路】
  以操作级别的【笔中枢序列】(zs_list 去单笔中枢)为骨架，自左向右贪心分段:
    - 相邻中枢关系用 CTrendAnalyzer.zs_relation 判定:
        newborn_up / newborn_down = 中枢新生(不重叠, 趋势延伸或反转);
        expansion                 = 中枢扩展(重叠, 仍属同一段盘整)。
    - 维护"当前段" cur:
        · expansion            → 并入当前段(盘整/中枢扩展延续);
        · 与当前段方向一致的新生 → 并入当前段(趋势延伸), 段方向锁定;
        · 与当前段方向相反的新生 → 当前段结束, 另起新段(方向翻转)。
    - 段结束时判定类型: 同向不重叠中枢数 ≥ min_trend_zs → 趋势; 否则 → 盘整。
    - 段是否"完美": 取其末中枢 bi_out 是否背驰(is_divergence) → 走势终完美。
  输出 DecomposePiece 列表; 最后一个 piece 通常是"进行中的当前段"。

  策略层用法: current_piece() 为上涨趋势/上涨盘整且未完美 → 持有多单;
  已完美 → 当前同级别走势完成, 边界买卖点可执行。
"""
from dataclasses import dataclass, field
from typing import List, Optional

from Trend.TrendAnalyzer import CTrendAnalyzer, ZoushiType


@dataclass
class DecomposePiece:
    """同级别分解出的一段走势类型"""
    idx: int
    zoushi_type: ZoushiType          # UP_TREND / DOWN_TREND / CONSOLIDATION
    direction: str                   # 'up' / 'down' / ''
    zs_list: List = field(default_factory=list)
    is_perfect: bool = False         # 走势终完美(末中枢离开段背驰)
    divergence_ratio: Optional[float] = None
    begin_time: Optional[str] = None
    end_time: Optional[str] = None

    @property
    def zs_count(self) -> int:
        return len(self.zs_list)

    @property
    def is_up(self) -> bool:
        return self.direction == "up"

    @property
    def is_down(self) -> bool:
        return self.direction == "down"

    def __str__(self):
        name = {
            ZoushiType.UP_TREND: "上涨趋势",
            ZoushiType.DOWN_TREND: "下跌趋势",
            ZoushiType.CONSOLIDATION: "盘整",
        }.get(self.zoushi_type, "未完成")
        return f"#{self.idx}{name}({self.zs_count}中枢{'·完美' if self.is_perfect else '·进行中'})"


class SameLevelDecomposer:
    """同级别分解器 — 输入操作级别的中枢序列, 输出一串同级别走势类型"""

    def __init__(self, min_trend_zs: int = 2):
        self.min_trend_zs = min_trend_zs

    def decompose(self, chan, lv, bsp_conf) -> List[DecomposePiece]:
        """对 chan[lv] 做同级别分解, 返回 DecomposePiece 列表"""
        try:
            valid = [z for z in chan[lv].zs_list.zs_lst if not z.is_one_bi_zs()]
        except Exception:
            return []
        if not valid:
            return []

        pieces: List[DecomposePiece] = []
        cur_zs: List = [valid[0]]
        cur_dir: Optional[str] = self._single_direction(valid[0])

        for i in range(1, len(valid)):
            rel = CTrendAnalyzer.zs_relation(valid[i - 1], valid[i])
            if rel == "expansion":
                cur_zs.append(valid[i])          # 中枢扩展 → 同段盘整延续
                continue
            new_dir = "up" if rel == "newborn_up" else "down"
            if cur_dir is None:
                cur_dir = new_dir
                cur_zs.append(valid[i])
            elif new_dir == cur_dir:
                cur_zs.append(valid[i])          # 同向新生 → 趋势延伸
            else:
                # 方向翻转 → 收束当前段, 另起新段
                pieces.append(self._finalize(len(pieces), cur_zs, cur_dir, bsp_conf))
                cur_zs = [valid[i]]
                cur_dir = new_dir

        pieces.append(self._finalize(len(pieces), cur_zs, cur_dir, bsp_conf))
        return pieces

    @staticmethod
    def _single_direction(zs) -> Optional[str]:
        """单中枢段的方向: 取离开段 bi_out 方向(无则 None)"""
        try:
            if zs.bi_out is not None:
                return "down" if zs.bi_out.is_down() else "up"
        except Exception:
            pass
        return None

    def _finalize(self, idx: int, zs_list: List, direction: Optional[str], bsp_conf) -> DecomposePiece:
        """结算一段: 判定类型(趋势/盘整)、完美、时间窗、背驰比"""
        # 类型: 同向不重叠中枢数达标 → 趋势; 否则盘整
        same_dir_cnt = self._count_same_dir(zs_list, direction)
        if direction == "up" and same_dir_cnt >= self.min_trend_zs:
            zt = ZoushiType.UP_TREND
        elif direction == "down" and same_dir_cnt >= self.min_trend_zs:
            zt = ZoushiType.DOWN_TREND
        else:
            zt = ZoushiType.CONSOLIDATION

        # 完美: 末中枢离开段背驰
        is_perfect = False
        ratio = None
        last_zs = zs_list[-1]
        if last_zs.bi_out is not None:
            try:
                is_diver, ratio = last_zs.is_divergence(bsp_conf)
                is_perfect = bool(is_diver)
            except Exception:
                is_perfect = False

        begin_time = end_time = None
        try:
            begin_time = str(zs_list[0].begin.time)
            end_time = str(zs_list[-1].end.time)
        except Exception:
            pass

        return DecomposePiece(
            idx=idx, zoushi_type=zt, direction=direction or "",
            zs_list=zs_list, is_perfect=is_perfect, divergence_ratio=ratio,
            begin_time=begin_time, end_time=end_time,
        )

    @staticmethod
    def _count_same_dir(zs_list: List, direction: Optional[str]) -> int:
        """统计段内"朝 direction 依次不重叠推进"的中枢个数"""
        if not direction or len(zs_list) < 2:
            return len(zs_list)
        cnt = 1
        for i in range(1, len(zs_list)):
            prev, cur = zs_list[i - 1], zs_list[i]
            ok = (cur.low > prev.high) if direction == "up" else (cur.high < prev.low)
            if ok:
                cnt += 1
            else:
                break
        return cnt


def current_piece(pieces: List[DecomposePiece]) -> Optional[DecomposePiece]:
    """取当前(最后一个)进行中的同级别走势类型"""
    return pieces[-1] if pieces else None


def holding_signal(pieces: List[DecomposePiece], is_long: bool) -> bool:
    """
    同级别分解的"持有"判据:
      持多(is_long=True) 且当前段是上涨趋势/上涨盘整且未完美 → 应持有(True);
      持空(is_long=False) 且当前段是下跌趋势/下跌盘整且未完美 → 应持有(True);
      当前段已完美 或 方向相反 → 不强制持有(False)。
    """
    cur = current_piece(pieces)
    if cur is None:
        return False
    if cur.is_perfect:
        return False
    if is_long:
        return cur.is_up or (cur.zoushi_type == ZoushiType.CONSOLIDATION and cur.direction == "up")
    return cur.is_down or (cur.zoushi_type == ZoushiType.CONSOLIDATION and cur.direction == "down")
