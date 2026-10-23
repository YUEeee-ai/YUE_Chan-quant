from Common.CEnum import LEFT_SEG_METHOD
from Common.ChanException import CChanException, ErrCode


SUPPORTED_SEG_ALGO = ("chan",)  # 目前仅实现缠师原文的特征序列线段算法


class CSegConfig:
    def __init__(self, seg_algo="chan", left_method="peak"):
        if seg_algo not in SUPPORTED_SEG_ALGO:
            raise CChanException(f"unknown seg_algo={seg_algo}, only {SUPPORTED_SEG_ALGO} supported", ErrCode.PARA_ERROR)
        self.seg_algo = seg_algo
        if left_method == "all":
            self.left_method = LEFT_SEG_METHOD.ALL
        elif left_method == "peak":
            self.left_method = LEFT_SEG_METHOD.PEAK
        else:
            raise CChanException(f"unknown left_seg_method={left_method}", ErrCode.PARA_ERROR)
