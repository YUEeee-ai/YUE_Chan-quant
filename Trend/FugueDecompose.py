"""
多重赋格 — 多级别同步同级别分解 (原著第40课)

【原文出处】《市场哲学的数学原理》(缠中说禅) 第40课《同级别分解的多重赋格》:
  同级别分解（第37/38课）固定一个操作级别把走势拆成一串同级别走势类型；
  "多重赋格"是把这条规则同时施加到多个级别上 —— 每个级别各自进行同级别分解，
  像赋格曲的多个声部一样同时进行。操作的"势"来自多个级别声部的对位关系：
  各级别当前段方向一致（对位齐奏）时趋势可靠、可重仓；声部方向冲突
  （对位不和）时说明大小级别在打架，应减仓观望。

【算法实现思路】
  对 lv_list 中的【每个级别】独立运行 SameLevelDecomposer，取各自当前段:
    1. voice: 每个级别当前段方向('up'/'down'/'')与其完美状态;
    2. consensus_dir: 各声部方向的多数共识('up'/'down'/'');
    3. aligned: 所有有声部方向的级别方向一致(齐奏);
    4. conflict: 声部方向冲突。
  输出 FugueState。策略层用法: 共识与开仓方向相反 → 禁开(对位不和);
  齐奏且同向 → 顺势仓位按 fugue_boost 加权(更强持有/加仓)。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from Common.CEnum import KL_TYPE
from Trend.SameLevelDecompose import SameLevelDecomposer, current_piece


@dataclass
class FugueVoice:
    """一个级别声部的当前同级别走势段"""
    lv: KL_TYPE
    direction: str          # 'up' / 'down' / ''
    is_perfect: bool
    zs_count: int

    def __str__(self):
        name = {"up": "上涨段", "down": "下跌段"}.get(self.direction, "方向未定")
        return f"{self.lv.name}:{name}{'·完美' if self.is_perfect else '·进行中'}({self.zs_count}中枢)"


@dataclass
class FugueState:
    """多级别同步分解(赋格)状态"""
    voices: List[FugueVoice] = field(default_factory=list)
    consensus_dir: str = ""     # 多数声部方向 'up'/'down'/''
    aligned: bool = False       # 所有有声部方向一致(齐奏)
    conflict: bool = False      # 声部方向冲突(对位不和)
    reason: str = ""

    @property
    def voice_count(self) -> int:
        return len(self.voices)

    def direction_of(self, lv: KL_TYPE) -> str:
        for v in self.voices:
            if v.lv == lv:
                return v.direction
        return ""

    def __str__(self):
        if not self.voices:
            return f"多重赋格:无声部({self.reason})"
        tag = "齐奏" if self.aligned else ("冲突" if self.conflict else "无共识")
        return (f"多重赋格:{tag} 共识={self.consensus_dir or '无'} | "
                + " ".join(str(v) for v in self.voices))


class FugueDecomposer:
    """多重赋格分解器 (第40课) — 多级别同步同级别分解"""

    def __init__(self, min_trend_zs: int = 2):
        self.min_trend_zs = min_trend_zs
        self._decomposer = SameLevelDecomposer(min_trend_zs)

    def decompose(self, chan, lv_list: List[KL_TYPE], bsp_conf) -> FugueState:
        st = FugueState()
        dirs: List[str] = []
        for lv in lv_list:
            try:
                pieces = self._decomposer.decompose(chan, lv, bsp_conf)
                cur = current_piece(pieces)
                if cur is None:
                    continue
                voice = FugueVoice(lv=lv, direction=cur.direction,
                                   is_perfect=cur.is_perfect, zs_count=cur.zs_count)
                st.voices.append(voice)
                if voice.direction:
                    dirs.append(voice.direction)
            except Exception:
                continue

        if not st.voices:
            st.reason = "各级别均尚无有效中枢"
            return st
        if not dirs:
            st.reason = "声部方向均未定"
            return st

        # 多数共识 + 齐奏/冲突判定
        up_n, down_n = dirs.count("up"), dirs.count("down")
        st.consensus_dir = "up" if up_n >= down_n else "down"
        st.aligned = (up_n == 0) != (down_n == 0)  # 只有单一方向
        st.conflict = not st.aligned
        if st.aligned:
            st.reason = f"{len(dirs)}个声部齐奏{st.consensus_dir}"
        else:
            st.reason = f"声部分裂 up×{up_n} vs down×{down_n}"
        return st
