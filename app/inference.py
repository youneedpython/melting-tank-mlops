import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
from tensorflow import keras
from sklearn.preprocessing import MinMaxScaler
import os

# --- 프로젝트 모듈 임포트 ---
# utils에서 LSTM 시퀀스 변환 로직, 상수 등을 가져옴
from app import utils 
from app.schemas import LSTM_SEQUENCE_LENGTH 


# 버전 정보
VERSION = "1.0.0"

# 학습 시 사용한 window 크기
SEQUENCE_LENGTH = 10   

# --- 훈련 환경 설정 (데이터 무결성 및 일관성 확보) ---
# 훈련 시 사용된 컬럼 순서 및 이름을 명확히 정의
FEATURE_COLUMNS = ["MELT_TEMP", "MOTORSPEED"]


# ----------------------------------------------------------------------------------
# [핵심 로직] 불량 확률 예측 (predict_prob)
# ----------------------------------------------------------------------------------
def predict_prob(
    readings: List[Dict], 
    model: keras.Model, 
    scaler: MinMaxScaler 
) -> float:
    """
    [책임: 추론 수행]
    실시간 센서 데이터 리스트를 받아 정규화 및 윈도우링 후 LSTM 모델로 불량 확률을 예측합니다.
    """
    
    # 1. 데이터 유효성 검사 (Data Integrity Check)
    # FastAPI의 schemas.py에서 이미 리스트 길이를 검사했지만, 최종 확인
    if len(readings) != LSTM_SEQUENCE_LENGTH:
        raise ValueError(
            f"Data integrity error: Required sequence length is {LSTM_SEQUENCE_LENGTH}, "
            f"but received {len(readings)}."
        )

    # 2. 데이터 전처리 및 정렬 (Data Engineering)
    # Pandas DataFrame으로 변환 및 훈련 데이터와 동일한 순서로 컬럼 정렬
    df = pd.DataFrame(readings)
    df = df[FEATURE_COLUMNS] 

    # 3. 데이터 변환 (책임 분리: utils.py에 위임)
    # 훈련 시 스케일러와 윈도우링 로직을 utils에 위임하여 처리 효율성 및 클린 코드 준수
    X_inference = utils.prepare_lstm_input(df, scaler, LSTM_SEQUENCE_LENGTH)
    
    # 4. 모델 예측 (Prediction)
    # 성능 최적화: 모델이 메모리에 상주하므로 로드 과정 없이 바로 predict 호출
    prediction = model.predict(X_inference, verbose=0)
    prob_ng = prediction[0][0] # 불량 확률 추출

    # NumPy float32를 Python float으로 변환하여 API 직렬화 문제 방지
    return float(prob_ng)


# ----------------------------------------------------------------------------------
# [보조 로직] 예측 후처리 (post_process)
# ----------------------------------------------------------------------------------
def post_process(prob_ng: float, threshold: float) -> Tuple[str, float]:
    """
    [책임: 라벨 결정]
    불량 확률을 기반으로 최종 라벨 및 임계값 반환.
    """
    
    # 데이터 무결성: 임계값은 main.py에서 환경 변수를 통해 안전하게 전달됨
    if prob_ng >= threshold:
        label = "NG" # 불량 감지
    else:
        label = "OK" # 양품 예상
        
    return label, threshold