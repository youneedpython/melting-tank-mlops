# mes_simulator.py
"""
MES 장비에서 주기적으로 불량 예측 API로 데이터를 보내는 시뮬레이터.

- CSV에서 센서 데이터를 읽어서 10개씩 끊어 전송
- /predict 엔드포인트 호출 (schemas.LSTM_SEQUENCE_LENGTH = 10 기준)
- 마지막까지 읽으면 다시 처음으로 돌아가 무한 반복
- AWS ECS Fargate 환경에서 별도 Task로 실행하는 것을 가정

사용 환경변수
------------
API_BASE_URL       : 예) http://localhost:8000  또는 http://<ALB-DNS>
API_KEY            : FastAPI에서 사용하는 x-api-key
CSV_PATH           : 기본값 'melting_tank.csv'
SIM_INTERVAL_SEC   : 요청 간격(초). 기본 30초
VERIFY_SSL         : HTTPS 인증서 검증 여부(true/false). 기본 true
"""

import os
import time
import json
import logging
from typing import List, Dict

import pandas as pd
import requests
from dotenv import load_dotenv


# -----------------------------
# 1. 환경변수 로드
# -----------------------------
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("API_KEY", "")
CSV_PATH = os.getenv("CSV_PATH", "data/mes_sample_data.csv")
SIM_INTERVAL_SEC = int(os.getenv("SIM_INTERVAL_SEC", "30"))
VERIFY_SSL_RAW = os.getenv("VERIFY_SSL", "true").lower()
VERIFY_SSL = VERIFY_SSL_RAW not in ("false", "0", "no")

PREDICT_ENDPOINT = f"{API_BASE_URL}/predict"

# LSTM 시퀀스 길이 (schemas.py와 동일하게 10으로 가정)
SEQUENCE_LENGTH = 10


# -----------------------------
# 2. 로깅 설정
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[MES_SIM] %(asctime)s %(levelname)s: %(message)s",
)


# -----------------------------
# 3. CSV 로딩 함수
# -----------------------------
def load_csv_data(path: str) -> pd.DataFrame:
    """
    CSV에서 센서 데이터를 읽어온다.
    필수 컬럼: MELT_TEMP, MOTORSPEED, MELT_WEIGHT, INSP
    (TAG 컬럼이 있어도 무시)
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV not found: {path}")

    df = pd.read_csv(path)

    required_cols = ["MELT_TEMP", "MOTORSPEED", "MELT_WEIGHT", "INSP"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    # 필요한 컬럼만 사용 (TAG 등은 있으면 무시)
    df = df[required_cols].copy()
    logging.info(f"Loaded CSV: {path}, rows={len(df)}, cols={df.columns.tolist()}")
    return df


# -----------------------------
# 4. 요청 payload 생성
# -----------------------------
def build_payload(window: pd.DataFrame) -> Dict:
    """
    10개 시퀀스를 읽어서 FastAPI /predict 요청 형식으로 변환.
    schemas.PredictRequest(readings: List[Reading]) 구조를 따름.
    """
    readings: List[Dict] = []
    for _, row in window.iterrows():
        readings.append(
            {
                "MELT_TEMP": float(row["MELT_TEMP"]),
                "MOTORSPEED": float(row["MOTORSPEED"]),
                "MELT_WEIGHT": float(row["MELT_WEIGHT"]),
                "INSP": float(row["INSP"]),
            }
        )

    return {"readings": readings}


# -----------------------------
# 5. API 호출 함수
# -----------------------------
def call_predict_api(payload: Dict) -> None:
    """
    /predict API를 호출하고 결과를 로그로 남긴다.
    인증 실패/서버 오류 등은 재시도 없이 로그만 출력.
    """
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
    }

    try:
        resp = requests.post(
            PREDICT_ENDPOINT,
            headers=headers,
            data=json.dumps(payload),
            timeout=10,
            verify=VERIFY_SSL,
        )
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return

    if not resp.ok:
        logging.error(f"API error {resp.status_code}: {resp.text}")
        return

    try:
        data = resp.json()
    except ValueError:
        logging.error(f"Invalid JSON response: {resp.text[:200]}")
        return

    prob = data.get("prob_ng")
    label = data.get("label")
    threshold = data.get("threshold")
    logging.info(
        f"Predict OK - prob_ng={prob:.4f} ({prob*100:.1f}%), "
        f"label={label}, threshold={threshold:.4f}"
    )


# -----------------------------
# 6. 메인 루프
# -----------------------------
def main():
    if not API_KEY:
        logging.warning(
            "API_KEY is empty. Please set API_KEY env var; "
            "otherwise /predict will return 401."
        )

    df = load_csv_data(CSV_PATH)

    if len(df) < SEQUENCE_LENGTH:
        raise ValueError(
            f"CSV row count ({len(df)}) is smaller than sequence length "
            f"{SEQUENCE_LENGTH}."
        )

    logging.info(
        f"Start MES simulation: base_url={API_BASE_URL}, "
        f"interval={SIM_INTERVAL_SEC}s, rows={len(df)}, window={SEQUENCE_LENGTH}"
    )

    while True:
        # 10개씩 끊어서(non-overlapping) 전송
        # MES에서 30초마다 10개 패킷을 보내는 구조라고 가정
        for start_idx in range(0, len(df), SEQUENCE_LENGTH):
            end_idx = start_idx + SEQUENCE_LENGTH
            window = df.iloc[start_idx:end_idx]

            # 마지막 윈도우가 10개 미만이면 버려도 되고, 다음 loop에서 다시 처음부터 시작
            if len(window) < SEQUENCE_LENGTH:
                break

            payload = build_payload(window)
            logging.info(
                f"Sending window rows [{start_idx}:{end_idx}) "
                f"to {PREDICT_ENDPOINT}"
            )
            call_predict_api(payload)

            logging.info(f"Sleep {SIM_INTERVAL_SEC} seconds...\n")
            time.sleep(SIM_INTERVAL_SEC)

        # 한 번 전체 데이터를 다 돌았으면 다시 처음부터 반복
        logging.info("Reached end of CSV. Restart simulation from the top.\n")


if __name__ == "__main__":
    main()
