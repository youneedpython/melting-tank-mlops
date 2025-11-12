import os
import logging
import joblib
from dotenv import load_dotenv
from tensorflow import keras
from fastapi import FastAPI, Header, Depends, HTTPException, status
from fastapi import BackgroundTasks
from typing import Annotated
from app.dashboard import router as dashboard_router

# --- 프로젝트 모듈 임포트 ---
# utils는 인증, 환경 변수 로드, 알림 등 보조 기능 담당
from app import utils
# schemas는 데이터 유효성 검사 및 규격 정의 담당
from app.schemas import PredictRequest, PredictResponse
# inference는 모델 추론 로직 담당
from app.inference import predict_prob, post_process, VERSION

#########################################
# 로그 생성
logger = logging.getLogger()

# 로그의 출력 기준 설정
logger.setLevel(logging.INFO)

# log 출력 형식
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#########################################


## =================================================================
# 1. 환경 변수 로드 및 초기 설정
## =================================================================
# .env 파일 또는 AWS 환경 변수에서 값 로드
# .env 파일을 읽어 시스템 환경 변수로 로드
API_KEY = os.getenv("API_KEY", "happy")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
THRESHOLD = float(os.getenv("PREDICTION_THRESHOLD", 0.5)) # 임계값 로드

## =================================================================
## 2. 모델 및 스케일러 전역 로드 (서버 시작 시 단 1회)
## MLOps 성능 최적화
## MLOps 환경에서 가장 중요하며, API의 응답 속도(Latency)를 보장합
## =================================================================
MODEL_PATH = "model/best_model.keras"         ## 모델 파일 경로
SCALER_PATH = "artifacts/minmax_scaler.joblib"    ## 스케일러 파일 경로

try:
    ## 모델과 스케일러를 메모리에 로드
    MODEL = keras.models.load_model(MODEL_PATH, compile=False)
    SCALER = joblib.load(SCALER_PATH)
    logging.info(f"[INFO] 모델({MODEL_PATH}) 및 스케일러 로드 완료.")
except Exception as e:
    ## 파일이 없거나 로드 오류 발생 시 서버 시작을 중단하여 배포 실패를 명확히
    logging.info(f"[ERROR] 모델/스케일러 로드 실패! 서버를 시작할 수 없습니다. 에러: {e}")
    ## 배포 환경에서는 파일이 없을 때 서버가 시작되지 않도록 예외 발생
    raise RuntimeError(f"Failed to load ML assets: {e}")

## =================================================================
# 3. FastAPI 앱 인스턴스 및 인증 의존성
## =================================================================
def get_api_key(x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None):
    """API Key를 추출하고 인증 로직을 utils.py에 위임"""
    if not utils.authenticate_api_key(x_api_key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Unauthorized: Invalid API Key"
        )

# API 인증을 전역 의존성으로 설정하여 모든 엔드포인트에 적용 (선택 사항)
app = FastAPI(
    title="Melting Tank Quality API",
    version=VERSION,
    # dependencies=[Depends(get_api_key)] # 모든 API 요청에 인증 적용
)

## 대시보드 라우터 등록
app.include_router(dashboard_router)

## =================================================================
# 4. 엔드포인트 정의
## =================================================================
@app.get("/")
def root():
    """상태 확인 및 버전 정보 제공 (Health Check)"""
    return {"message": "Melting Tank Quality API is running", "version": VERSION}

@app.post("/predict", dependencies=[Depends(get_api_key)], response_model=PredictResponse)
def predict(req: PredictRequest, background: BackgroundTasks):
    """
    실시간 센서 데이터로 불량률을 예측하고, 임계값 초과 시 알림을 전송합니다.
    """
    # 1. 예측 실행: 전역 로드된 MODEL과 SCALER를 inference 함수에 전달
    try:
        prob_ng = predict_prob(
            readings=[r.model_dump() for r in req.readings], 
            model=MODEL, 
            scaler=SCALER
        )
    except ValueError as e:
        # 데이터 길이 미달 등 inference.py에서 발생한 유효성 검사 에러 처리
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # 기타 예측 오류
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Prediction failed due to server error.")

    # 2. 예측 후처리 및 라벨 결정
    label, th = post_process(prob_ng, THRESHOLD)

    # 3. MLOps 알림 로직 (utils.py 사용)
    if label == "NG":
        message = f"🚨 불량 감지 경고! 예측 확률: {prob_ng:.2f} (임계값: {th})"
        background.add_task(utils.send_alert_notification, message, SLACK_WEBHOOK_URL)
        
    # 4. 결과 로깅 (운영 환경에서는 비동기적으로 처리)
    # utils.log_prediction_result(req.readings, prob_ng, label, VERSION) # 비동기 로깅 구현 시 사용

    return PredictResponse(prob_ng=prob_ng, label=label, threshold=th, version=VERSION)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/readyz")
def readyz():
    try:
        _ = SCALER  # 로드 여부 확인
        _ = MODEL   # 로드 여부 확인
        return {"ready": True, "version": VERSION}
    except Exception:
        raise HTTPException(status_code=503, detail="Not ready")