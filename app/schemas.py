from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


## --- 1. LSTM 시퀀스 길이 정의 ---
## 이 값은 inference.py의 SEQUENCE_LENGTH와 일치
LSTM_SEQUENCE_LENGTH = 10

## --- 2. 입력 데이터 유효성 검사를 위한 Base Model ---
## 입력 데이터 규격: 단일 시점의 센서 데이터
class Reading(BaseModel):
    """
    [책임: 입력 데이터 규격화]
    단일 시점의 센서 데이터 입력 규격 정의 및 타입 힌트 강화.
    """
    # 6초 단위 최근 N개(예: 10개) 샘플
    # 모든 센서 데이터를 float 타입으로 명시하여 데이터 유효성 검사 강화
    MELT_TEMP: float = Field(..., description="용해 온도 (섭씨)")
    MOTORSPEED: float = Field(..., description="모터 교반 속도 (RPM)")
    MELT_WEIGHT: float = Field(..., description="용해탱크 내용량 (중량)")
    INSP: float = Field(..., description="생산품 수분 함유량")

    ## 여기에 추가적인 특징(예: 통계적 특징)이 있다면 추가
    ## 예: MELT_TEMP_MEAN: float = Field(..., description="1분 평균 용해 온도")


# --- 3. API 요청 규격 (시퀀스 길이 유효성 검사) ---
class PredictRequest(BaseModel):
    """
    [책임: 요청 데이터 유효성 검사]
    모델 추론을 위한 전체 시퀀스 데이터 리스트 규격 정의.
    """
    readings: List[Reading] = Field(..., description=f"LSTM 모델 추론을 위한 {LSTM_SEQUENCE_LENGTH}개 데이터 포인트 시퀀스")

    # [보강] 시퀀스 길이 유효성 검사 (@validator) - API 레이어에서의 책임 분리
    # 성능 최적화: 유효하지 않은 요청은 모델 추론 전에 빠르게 거절합니다.
    @field_validator('readings')
    def validate_sequence_length(cls, readings: List[Reading]):
        """입력된 데이터의 길이가 LSTM이 요구하는 시퀀스 길이와 일치하는지 검사합니다."""
        if len(readings) != LSTM_SEQUENCE_LENGTH:
            raise ValueError(
                f"Data integrity error: LSTM model requires exactly {LSTM_SEQUENCE_LENGTH} data points. "
                f"Received {len(readings)}."
            )
        return readings

# --- 4. API 응답 규격 ---
class PredictResponse(BaseModel):
    """
    [책임: 응답 데이터 규격화]
    불량률 예측 API의 응답 규격 정의.
    """
    prob_ng: float = Field(..., description="불량 확률 (0.0 ~ 1.0)")
    label: str = Field(..., description="최종 불량 판정 (OK 또는 NG)")
    threshold: float = Field(..., description="판정에 사용된 임계값")
    version: str = Field(..., description="API 버전")
