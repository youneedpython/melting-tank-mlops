# Stage 1: 최종 런타임 환경 구축 (배포 최적화 및 보안 강화)

# 1. 베이스 이미지 설정: 작고 안정적인 Python 3.9 Slim 이미지 사용
FROM python:3.9-slim AS production

# 2. 필수 OS 의존성 설치 및 캐시 제거 (이미지 크기 최소화)
# 'gcc'는 일부 파이썬 라이브러리(Numpy 등) 컴파일에 필요
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 파이썬 의존성 설치
# requirements.txt 파일 복사
COPY requirements.txt .

# pip install: 
#   --no-cache-dir: 캐시 파일을 저장하지 않아 이미지 크기 감소
#   --upgrade pip: 최신 pip으로 업그레이드
RUN pip install --no-cache-dir -r requirements.txt

# 5. 보안 강화: root가 아닌 'appuser' 생성 및 전환
# 컨테이너 보안을 강화하는 필수 단계
RUN useradd --create-home appuser
USER appuser

# 6. 모델 아티팩트 및 코드 복사 (appuser의 홈 디렉토리로 복사)
# 코드 복사
COPY --chown=appuser:appuser ./app/ /app
# 'best_model.keras' 등의 모델 파일 포함
COPY --chown=appuser:appuser ./artifacts /app/artifacts 
# ./artifacts 폴더를 /app 아래에 복사 (모델 경로 일치)
COPY --chown=appuser:appuser ./model /app/model 


# 7. 포트 노출 (FastAPI 기본 포트)
EXPOSE 8000

# 8. 컨테이너 실행 명령어 (Gunicorn + Uvicorn Worker 사용 권장)
# MLOps 표준: Uvicorn 단독 대신 Gunicorn을 마스터 프로세스로 사용하여 안정성과 성능 최적화
# $PORT는 ECS/EKS 환경에서 동적으로 주입됩니다.
# CPU 코어 수에 맞춘 Worker 설정이 필요합니다. Fargate는 코어 수 기반으로 최적화됩니다.
CMD ["gunicorn", "main:app", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "60"] 
     
# 참고: Uvicorn 단독 사용 시: 
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]