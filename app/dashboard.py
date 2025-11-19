# app/dashboard.py
import os
from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.concurrency import run_in_threadpool
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from .storage import PREDICTION_HISTORY

# -------------------------------------------------------------------
# 환경변수에서 Threshold 값 로드 (main.py와 동일한 로직)
# -------------------------------------------------------------------
load_dotenv()
THRESHOLD = float(os.getenv("PREDICTION_THRESHOLD", 0.5))

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def show_dashboard():

    # 데이터가 하나도 없을 때
    if not PREDICTION_HISTORY:
        return HTMLResponse("""
        <h1 style="text-align:center; font-size:32px; margin-top: 40px;">Melting Tank Dashboard</h1>
        <p style="text-align:center;">예측 데이터가 아직 없습니다.</p>
        """)

    # ------------------------------------------------------------------
    # 1) 저장된 예측값 분리
    # ------------------------------------------------------------------
    timestamps = [rec["timestamp"] for rec in PREDICTION_HISTORY]
    prob_ng_raw = [float(rec["prob_ng"]) for rec in PREDICTION_HISTORY]

    prob_ng_percent = [p * 100 for p in prob_ng_raw]   # 0~1 → 0~100(%)
    threshold_percent = THRESHOLD * 100

    # 각 포인트가 NG인지 여부 (Threshold 기준)
    is_ng_list = [p >= threshold_percent for p in prob_ng_percent]

    # 마커 색상: NG는 빨간색, 나머지는 파란색
    marker_colors = ["#e74c3c" if is_ng else "#2980b9" for is_ng in is_ng_list]

    # ------------------------------------------------------------------
    # 2) Plotly Figure 생성
    # ------------------------------------------------------------------
    fig = make_subplots(rows=1, cols=1)

    # (1) 불량 발생 확률 라인 + 마커
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=prob_ng_percent,
            mode="lines+markers",
            name="불량 발생 확률(%)",
            marker=dict(color=marker_colors, size=8),
            line=dict(color="#2980b9"),
            hovertemplate=(
                "시간: %{x}<br>"
                "불량 발생 확률: %{y:.1f}%"
                "<extra></extra>"
            ),
        )
    )

    # (2) Threshold 수평선 (별도 Trace로 Hover 텍스트 제공)
    fig.add_trace(
        go.Scatter(
            x=[timestamps[0], timestamps[-1]],
            y=[threshold_percent, threshold_percent],
            mode="lines",
            line=dict(dash="dash", color="red"),
            name=f"Threshold ({threshold_percent:.1f}%)",
            hovertemplate=(
                f"Threshold 기준값: {threshold_percent:.1f}%"
                "<extra></extra>"
            ),
        )
    )

    # (3) NG 영역 음영 – 전체 x축 범위로 확장
    fig.update_xaxes(range=[timestamps[0], timestamps[-1]])

    fig.add_shape(
        type="rect",
        xref="x",
        yref="y",
        x0=timestamps[0],
        x1=timestamps[-1],
        y0=threshold_percent,
        y1=100,
        fillcolor="rgba(255, 0, 0, 0.1)",
        layer="below",
        line=dict(width=0),
    )

    # ------------------------------------------------------------------
    # 3) 축 / 레이아웃 설정
    # ------------------------------------------------------------------
    fig.update_yaxes(range=[0, 100], title="불량 발생 확률(%)")
    fig.update_xaxes(title="시간")

    fig.update_layout(
        margin=dict(l=40, r=40, t=100, b=40),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.18,
        ),
        height=500,
    )

    # ------------------------------------------------------------------
    # 4) KPI 계산 (마지막 값 / 최근 10개 평균)
    # ------------------------------------------------------------------
    # 마지막 예측값
    last_prob = prob_ng_raw[-1]                 # 0~1
    last_prob_percent = prob_ng_percent[-1]     # 0~100
    last_ts = timestamps[-1].strftime("%Y-%m-%d %H:%M:%S")

    status_label = "NG" if last_prob >= THRESHOLD else "OK"
    status_color = "#e74c3c" if status_label == "NG" else "#2ecc71"

    # 최근 10개 평균 (데이터 개수가 10개 미만이면 있는 만큼만)
    window = min(10, len(prob_ng_percent))
    recent_slice = prob_ng_percent[-window:]
    avg_prob_percent = sum(recent_slice) / window

    # 최근 window 중 NG 비율 (참고용)
    ng_count_recent = sum(1 for p in recent_slice if p >= threshold_percent)
    ng_ratio_recent = (ng_count_recent / window) * 100

    # ------------------------------------------------------------------
    # 5) NG 연속 발생 여부에 따른 경고 배너
    # ------------------------------------------------------------------
    STREAK_N = 3
    warning_html = ""
    if len(is_ng_list) >= STREAK_N:
        recent_flags = is_ng_list[-STREAK_N:]
        if all(recent_flags):
            warning_html = f"""
            <div class="warning-banner">
                ⚠️ 불량 패턴이 연속으로 감지되었습니다 (최근 {STREAK_N}/{STREAK_N} NG)
            </div>
            """

    # ------------------------------------------------------------------
    # 6) HTML 헤더 + 스타일(CSS) + KPI 카드 + 그래프 조합
    # ------------------------------------------------------------------
    # KPI 카드 애니메이션 / 레이아웃 스타일 정의
    header_html = """
    <style>
    .kpi-row {
        display: flex;
        justify-content: center;
        gap: 16px;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }
    .kpi-card {
        text-align: center;
        padding: 16px 24px;
        border-radius: 12px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
        background-color: #fafafa;
        min-width: 260px;
    }
    .kpi-card.main-value {
        min-width: 280px;
    }
    .kpi-card.ng {
        animation: kpi-flash 1.4s ease-in-out 0s 2;
    }
    .kpi-card.ok {
        background-color: #f5fff8;
    }
    @keyframes kpi-flash {
        0%   { background-color: #ffeaea; }
        50%  { background-color: #ffffff; }
        100% { background-color: #ffeaea; }
    }
    .warning-banner {
        background:#fdeaea;
        border-left:6px solid #e74c3c;
        padding:12px 20px;
        margin:0 auto 16px auto;
        max-width:600px;
        text-align:center;
        font-size:16px;
        color:#c0392b;
    }
    </style>
    <h1 style="text-align:center; font-size:34px; margin-top: 40px; margin-bottom:20px;">
        실시간 불량 발생 확률 추이
    </h1>
    """

    # KPI 카드용 클래스 (NG면 애니메이션)
    kpi_main_class = "kpi-card main-value ng" if status_label == "NG" else "kpi-card main-value ok"

    kpi_html = f"""
    <div class="kpi-row">
        <!-- 메인 KPI: 마지막 예측값 -->
        <div class="{kpi_main_class}">
            <div style="font-size:14px; color:#555;">마지막 예측값</div>
            <div style="font-size:40px; font-weight:700; color:{status_color}; margin-top:4px;">
                {last_prob_percent:.1f}% ({status_label})
            </div>
            <div style="font-size:12px; color:#777; margin-top:4px;">
                기준 Threshold: {threshold_percent:.1f}% · 시각: {last_ts}
            </div>
        </div>

        <!-- 서브 KPI: 최근 10개 평균 -->
        <div class="kpi-card">
            <div style="font-size:14px; color:#555;">최근 {window}개 평균 불량률</div>
            <div style="font-size:28px; font-weight:700; color:#34495e; margin-top:4px;">
                {avg_prob_percent:.1f}%
            </div>
            <div style="font-size:12px; color:#777; margin-top:4px;">
                이 중 NG 비율: {ng_ratio_recent:.1f}% ({ng_count_recent}/{window}개 NG)
            </div>
        </div>
    </div>
    """

    html_graph = await run_in_threadpool(fig.to_html, full_html=False)

    # 헤더 → (경고 배너) → KPI → 그래프 순서로 출력
    return HTMLResponse(header_html + warning_html + kpi_html + html_graph)
