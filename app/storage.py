# app/storage.py

import logging
from datetime import datetime
from typing import List, Dict, Any
import pytz

# 예측 결과를 저장할 최대 길이
MAX_HISTORY: int = 30

# 최근 예측 결과를 저장하는 전역 리스트
# 각 원소: {"timestamp": datetime, "prob_ng": float}
PREDICTION_HISTORY: List[Dict[str, Any]] = []

logging.info("[INFO] 전역 데이터 저장소 (storage.py) 초기화 완료.")


def add_prediction_result(prob_ng: float) -> None:
    """
    새로운 예측 결과를 저장소에 추가하고 최대 길이를 유지합니다.

    Args:
        prob_ng: 모델이 반환한 불량 확률 (0.0 ~ 1.0)
    """

    # KST 시간대 객체 생성
    KST = pytz.timezone('Asia/Seoul')

    record = {
        "timestamp": datetime.now(KST),  # 서버 현재 시각
        "prob_ng": float(prob_ng),
    }
    PREDICTION_HISTORY.append(record)

    # 최대 길이 초과 시 가장 오래된 데이터 제거 (FIFO 큐처럼 작동)
    if len(PREDICTION_HISTORY) > MAX_HISTORY:
        PREDICTION_HISTORY.pop(0)
