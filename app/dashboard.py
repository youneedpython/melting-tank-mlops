# app/dashboard.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import plotly.graph_objs as go
from plotly.subplots import make_subplots
from fastapi.concurrency import run_in_threadpool
from .storage import PREDICTION_HISTORY


router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def show_dashboard():
    """멜팅 탱크 대시보드: 실시간 불량 확률 추이 시각화"""
    # --- 예시 하드코딩된 데이터 ---
    # timestamps = list(range(10))
    # prob_ng = [0.12, 0.18, 0.23, 0.31, 0.48, 0.52, 0.60, 0.74, 0.80, 0.90]

    # --- 하드코딩된 데이터 대신 실제 예측 데이터 사용 ---
    prob_ng = PREDICTION_HISTORY # <--- 2. 전역 리스트 사용
    timestamps = list(range(len(prob_ng))) # 데이터 길이에 맞게 타임스탬프 조정

    if not prob_ng:
        return HTMLResponse("<h2>Melting Tank Dashboard</h2><p>No predictions yet. Please send data to /predict.</p>")

    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(
        go.Scatter(x=timestamps, y=prob_ng, mode="lines+markers", name="NG 확률")
    )
    fig.update_yaxes(range=[0, 1], title="NG Probability")
    fig.update_xaxes(title="Time")
    fig.update_layout(title="실시간 불량 확률 추이", height=500, margin=dict(l=40, r=20, t=60, b=40))

    # html = fig.to_html(full_html=False)
    ## Plotly HTML 생성은 동기적 I/O 작업이므로 run_in_threadpool을 사용해 블로킹 방지
    html = await run_in_threadpool(fig.to_html, full_html=False)
    

    return HTMLResponse(f"<h2>Melting Tank Dashboard</h2>{html}")