"""
单级别缠论计算总调度器 (K线 → 分型 → 笔 → 线段 → 中枢 → 买卖点)

【原文出处】贯穿全篇的计算流水线；第18课级别递归：把线段当笔可算出"线段的线段"
  与父级别中枢，实现走势类型的递归定义。

【算法实现思路】
  CKLine_List 是一个级别的中枢，持有并串联所有阶段结果：
    lst(合并K线) / bi_list(笔) / seg_list+segseg_list(线段+段段) /
    zs_list+segzs_list(笔中枢+段中枢) / bs_point_lst+seg_bs_point_lst(买卖点)。
  - add_single_klu(klu): 喂入每根新K线 → set_metric(挂指标) → try_add 合并进末CKLine
    → UP/DOWN 时新建 CKLine → 对 lst[-2] 更新分型 → update_bi 增量更新笔；
    支持 triger_step 逐K线回放 与 批量两种模式。
  - cal_seg_and_zs(): 全量重算 —— 虚笔 → 线段(cal_seg) → 笔中枢(zs_list.cal_bi_zs)
    → update_zs_in_seg → 再上一层算 段段/段中枢(级别递归) → 回填笔的 klc_lst
    → 最后算买卖点(先段级后笔级)。
  - get_seglist_instance(): 构造线段算法实例（目前仅 chan 特征序列算法；seg_algo 合法性在 CSegConfig 校验）。
  - cal_seg()/update_zs_in_seg(): 笔→线段归属映射；中枢→线段归属并回填 bi_in/bi_out。
"""
from typing import List, Union, overload

from Bi.Bi import CBi
from Bi.BiList import CBiList
from BuySellPoint.BSPointList import CBSPointList
from ChanConfig import CChanConfig
from Common.CEnum import KLINE_DIR, SEG_TYPE
from Seg.Seg import CSeg
from Seg.SegConfig import CSegConfig
from Seg.SegListComm import CSegListComm
from ZS.ZSList import CZSList

from .KLine import CKLine
from .KLineUnit import CKLine_Unit


def get_seglist_instance(seg_config: CSegConfig, lv) -> CSegListComm:
    # seg_algo 已在 CSegConfig 校验；目前仅实现 chan，新增算法时在此按 seg_config.seg_algo 分派
    from Seg.SegListChan import CSegListChan
    return CSegListChan(seg_config, lv)


class CKLine_List:
    def __init__(self, kl_type, conf: CChanConfig):
        self.kl_type = kl_type
        self.config = conf
        self.lst: List[CKLine] = []  # K线列表，可递归  元素KLine类型
        self.bi_list = CBiList(bi_conf=conf.bi_conf)
        self.seg_list: CSegListComm[CBi] = get_seglist_instance(seg_config=conf.seg_conf, lv=SEG_TYPE.BI)
        self.segseg_list: CSegListComm[CSeg[CBi]] = get_seglist_instance(seg_config=conf.seg_conf, lv=SEG_TYPE.SEG)

        self.zs_list = CZSList(zs_config=conf.zs_conf)
        self.segzs_list = CZSList(zs_config=conf.zs_conf)

        self.bs_point_lst = CBSPointList[CBi, CBiList](bs_point_config=conf.bs_point_conf)
        self.seg_bs_point_lst = CBSPointList[CSeg, CSegListComm](bs_point_config=conf.seg_bs_point_conf)

        self.metric_model_lst = conf.GetMetricModel()

        self.step_calculation = self.need_cal_step_by_step()

    @overload
    def __getitem__(self, index: int) -> CKLine: ...

    @overload
    def __getitem__(self, index: slice) -> List[CKLine]: ...

    def __getitem__(self, index: Union[slice, int]) -> Union[List[CKLine], CKLine]:
        return self.lst[index]

    def __len__(self):
        return len(self.lst)

    def cal_seg_and_zs(self):
        if not self.step_calculation:
            self.bi_list.try_add_virtual_bi(self.lst[-1])
        cal_seg(self.bi_list, self.seg_list)
        self.zs_list.cal_bi_zs(self.bi_list, self.seg_list)
        update_zs_in_seg(self.bi_list, self.seg_list, self.zs_list)  # 计算seg的zs_lst，以及中枢的bi_in, bi_out

        cal_seg(self.seg_list, self.segseg_list)
        self.segzs_list.cal_bi_zs(self.seg_list, self.segseg_list)
        update_zs_in_seg(self.seg_list, self.segseg_list, self.segzs_list)  # 计算segseg的zs_lst，以及中枢的bi_in, bi_out

        self.update_klc_in_bi()  # 计算每一笔里面的 klc列表

        # 计算买卖点
        self.seg_bs_point_lst.cal(self.seg_list, self.segseg_list)  # 线段线段买卖点
        self.bs_point_lst.cal(self.bi_list, self.seg_list)  # 再算笔买卖点

    def need_cal_step_by_step(self):
        return self.config.triger_step

    def add_single_klu(self, klu: CKLine_Unit):
        klu.set_metric(self.metric_model_lst)
        if len(self.lst) == 0:
            self.lst.append(CKLine(klu, idx=0))
        else:
            _dir = self.lst[-1].try_add(klu)
            if _dir != KLINE_DIR.COMBINE:  # 不需要合并K线
                self.lst.append(CKLine(klu, idx=len(self.lst), _dir=_dir))
                if len(self.lst) >= 3:
                    self.lst[-2].update_fx(self.lst[-3], self.lst[-1])
                if self.bi_list.update_bi(self.lst[-2], self.lst[-1], self.step_calculation) and self.step_calculation:
                    self.cal_seg_and_zs()
            elif self.step_calculation and self.bi_list.try_add_virtual_bi(self.lst[-1], need_del_end=True):  # 这里的必要性参见issue#175
                self.cal_seg_and_zs()

    def klu_iter(self, klc_begin_idx=0):
        for klc in self.lst[klc_begin_idx:]:
            yield from klc.lst

    def update_klc_in_bi(self):
        for bi in self.bi_list:
            bi.set_klc_lst(self[bi.begin_klc.idx:bi.end_klc.idx+1])


def cal_seg(bi_list, seg_list):
    seg_list.update(bi_list)
    # 计算每一笔属于哪个线段
    bi_seg_idx_dict = {}
    for seg_idx, seg in enumerate(seg_list):
        for i in range(seg.start_bi.idx, seg.end_bi.idx+1):
            bi_seg_idx_dict[i] = seg_idx
    for bi in bi_list:
        bi.set_seg_idx(bi_seg_idx_dict.get(bi.idx, len(seg_list)))  # 找不到的应该都是最后一个线段的


def update_zs_in_seg(bi_list, seg_list, zs_list):
    for seg in seg_list:
        seg.clear_zs_lst()
        for zs in zs_list:
            if zs.is_inside(seg):
                seg.add_zs(zs)
            assert zs.begin_bi.idx > 0
            zs.set_bi_in(bi_list[zs.begin_bi.idx-1])
            if zs.end_bi.idx+1 < len(bi_list):
                zs.set_bi_out(bi_list[zs.end_bi.idx+1])
            zs.set_bi_lst(list(bi_list[zs.begin_bi.idx:zs.end_bi.idx+1]))
