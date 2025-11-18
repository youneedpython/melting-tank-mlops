# app/storage.py

import logging
from typing import List

# 예측 결과를 저장할 최대 길이
MAX_HISTORY: int = 30
# 실제 예측 확률(0.0 ~ 1.0)을 저장할 전역 리스트
PREDICTION_HISTORY: List[float] = []

logging.info(f"[INFO] 전역 데이터 저장소 (storage.py) 초기화 완료.")

def add_prediction_result(prob_ng: float):
    """
    새로운 예측 결과를 저장소에 추가하고 최대 길이를 유지합니다.
    """
    PREDICTION_HISTORY.append(prob_ng)
    
    # 최대 길이 초과 시 가장 오래된 데이터 제거 (FIFO 큐처럼 작동)
    if len(PREDICTION_HISTORY) > MAX_HISTORY:
        PREDICTION_HISTORY.pop(0)