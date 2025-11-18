import numpy as np
import pandas as pd
import time, os, json, requests
import boto3
from typing import List, Dict, Optional
from sklearn.preprocessing import MinMaxScaler
from pandas.errors import EmptyDataError


# S3 클라이언트 초기화 (전역으로 두면 성능 최적화)
S3_CLIENT = boto3.client('s3')


# ----------------------------------------------------------------------
# A. 시퀀스 윈도우 변환 함수 (데이터 엔지니어링 핵심)
# ----------------------------------------------------------------------
def prepare_lstm_input(
    df_raw: pd.DataFrame, 
    scaler: MinMaxScaler, 
    sequence_length: int
) -> np.ndarray:
    """
    [책임: LSTM 입력 데이터 변환]
    API 입력 데이터(DataFrame)를 정규화하고 LSTM 추론에 필요한 3D 시퀀스로 변환합니다.

    Args:
        df_raw: 추론에 사용될 특징 데이터 (Feature DataFrame).
        scaler: 훈련 시 사용된 MinMaxScaler 객체.
        sequence_length: LSTM 윈도우 크기.

    Returns:
        (1, sequence_length, n_features) 형태의 3D NumPy 배열.
    """
    # 1. 데이터 타입 유효성 검사 및 정규화
    if df_raw.empty:
        raise EmptyDataError("Input DataFrame is empty.")
    
    # 훈련 시와 동일한 방식으로 정규화 (성능 최적화)
    try:
        data_scaled = scaler.transform(df_raw.values)
    except ValueError as e:
        # 데이터프레임 컬럼 수 불일치 등의 오류 방지
        raise ValueError(f"Normalization failed: Input features mismatch. Original error: {e}")

    # 2. LSTM 시퀀스 윈도우 변환 (클린 코드: 로직 분리)
    # schemas.py에서 이미 길이 검사를 했으나, 내부 로직 안정성 확보
    if data_scaled.shape[0] < sequence_length:
         raise ValueError(f"Insufficient data points ({data_scaled.shape[0]}) for sequence length {sequence_length}.")
        
    # 마지막 윈도우 만큼 슬라이싱하여 3D 형태로 변환
    X_inference = data_scaled[-sequence_length:].reshape(1, sequence_length, data_scaled.shape[1])
    
    return X_inference


# ----------------------------------------------------------------------
# B. API 인증 및 보안 함수 (MLOps 보안)
# ----------------------------------------------------------------------
def authenticate_api_key(received_key: Optional[str], expected_key: str) -> bool:
    """
    API Key를 검증하여 인증 여부를 반환합니다.
    """
    if not received_key:
        return False
        
    # MLOps 보안: 환경 변수에서 로드된 키와 비교
    return received_key == expected_key


# ----------------------------------------------------------------------
# C. 알림 트리거 함수 (MLOps 자동화)
# ----------------------------------------------------------------------
def send_alert_notification(message: str, webhook_url: Optional[str]):
    """
    [책임: 외부 알림 전송]
    Slack Webhook을 사용하여 불량 감지 경고 알림을 비동기적으로 전송합니다.
    (실제 운영에서는 별도 비동기 작업 큐를 사용해야 성능에 영향이 없음)
    """
    if not webhook_url:
        print("[WARNING] SLACK_WEBHOOK_URL is not set. Skipping notification.")
        return
        
    payload = {
        "text": f"🚨 [MELT TANK MLOPS ALERT] {message}",
        "username": "MeltingTank-AI-Monitor",
        "icon_emoji": ":warning:"
    }
    
    try:
        # 실제 운영에서는 requests 대신 asyncio/httpx를 사용하여 비동기로 처리해야 
        # API 응답 속도(Latency)에 영향을 주지 않습니다. (성능 최적화 지점)
        response = requests.post(webhook_url, json=payload, timeout=5) # 타임아웃 설정
        response.raise_for_status() 
        print(f"[INFO] Slack alert sent successfully at {time.strftime('%H:%M:%S')}")
    except requests.exceptions.Timeout:
        print(f"[ERROR] Slack alert failed: Request timed out.")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to send Slack alert: {e}")


# ----------------------------------------------------------------------
# D. 로깅 함수 (MLOps 모니터링) - 실제 구현 시 DynamoDB/S3 연동 필요
# ----------------------------------------------------------------------
def log_prediction_result(
    input_data: List[Dict], 
    prob_ng: float, 
    label: str, 
    version: str,
    s3_bucket: str = os.getenv("S3_LOG_BUCKET"), 
    s3_prefix: str = os.getenv("S3_LOG_PREFIX", "melting_tank_logs")
):
    """
    [책임: 예측 결과 로깅]
    예측 결과를 로깅합니다. 실제 운영 환경에서는 DB/S3에 비동기 저장합니다.
    """
    # [수정] pd.Timestamp.now() 사용을 위해 pandas 임포트 확인 (코드 최상단에서 처리)
    import pandas as pd 
    
    log_entry = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "model_version": version,
        "prediction_probability": prob_ng,
        "prediction_label": label,
        "input_summary": f"Data points: {len(input_data)}",
        # 운영 시는 데이터 용량을 줄여 핵심 값만 로깅해야 합니다.
    }

    # S3 저장 호출
    if s3_bucket:
        log_data = { ... } # 위에서 생성한 최종 로그 데이터
        save_log_to_s3(log_data, s3_bucket, s3_prefix, "inference")
    
    # 현재는 단순 콘솔 출력 (실제 운영 시: Save to DynamoDB or S3)
    print(f"[LOG] Prediction recorded: {json.dumps(log_entry)}")


# ----------------------------------------------------------------------
# E. 예측 결과를 S3에 JSON 파일로 저장
# ----------------------------------------------------------------------
def save_log_to_s3(log_data: dict, bucket_name: str, prefix: str, source: str):
    """
    예측 결과를 S3에 JSON 파일로 저장합니다. (비동기 처리 권장)
    
    Args:
        log_data: 저장할 로그 데이터 딕셔너리.
        bucket_name: 대상 S3 버킷 이름.
        prefix: 버킷 내 저장 경로 접두사 (예: logs/yyyy/mm/dd/).
    """
    # 1. 파일 이름 및 경로 정의 (데이터 엔지니어링 표준)
    # yyyy/mm/dd/source/timestamp.json 형태로 저장하여 Athena 분석 용이하게 함
    current_time = pd.Timestamp.now()
    timestamp_str = current_time.strftime("%Y%m%d%H%M%S")
    
    s3_key = (
        f"{prefix}/year={current_time.year}/month={current_time.month}/day={current_time.day}/"
        f"{source}_{timestamp_str}_{int(time.time()*1000)}.json"
    )
    
    # 2. JSON 직렬화
    json_data = json.dumps(log_data).encode('UTF-8')
    
    # 3. S3에 업로드
    try:
        S3_CLIENT.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json_data,
            ContentType='application/json'
        )
        print(f"[INFO] Log saved to S3: s3://{bucket_name}/{s3_key}")
    except Exception as e:
        # S3 오류 발생 시 서버 다운을 막기 위해 예외 처리
        print(f"[ERROR] Failed to save log to S3: {e}")