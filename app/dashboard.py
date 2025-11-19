# app/dashboard.py
import os
from datetime import datetime
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .storage import PREDICTION_HISTORY

router = APIRouter()

load_dotenv()
THRESHOLD = float(os.getenv("PREDICTION_THRESHOLD", "0.5"))
# 새로고침 주기(초) – 필요하면 .env 에 DASHBOARD_REFRESH_INTERVAL 로 조절 가능
REFRESH_INTERVAL_SEC = int(os.getenv("DASHBOARD_REFRESH_INTERVAL", "30"))
RECENT_WINDOW_DEFAULT = 10
STREAK_N = 3


def _build_dashboard_metrics() -> Dict[str, Any]:
    """PREDICTION_HISTORY를 기반으로 차트/지표 계산."""
    if not PREDICTION_HISTORY:
        return {
            "has_data": False,
            "timestamps": [],
            "prob_ng_percent": [],
            "threshold_percent": THRESHOLD * 100,
            "marker_colors": [],
            "last": None,
            "recent": None,
            "streak_ng": None,
        }

    timestamps: List[datetime] = [rec["timestamp"] for rec in PREDICTION_HISTORY]
    prob_ng_raw: List[float] = [float(rec["prob_ng"]) for rec in PREDICTION_HISTORY]

    prob_ng_percent: List[float] = [p * 100.0 for p in prob_ng_raw]
    threshold_percent: float = THRESHOLD * 100.0

    # NG 여부 및 색상
    is_ng_list: List[bool] = [p >= threshold_percent for p in prob_ng_percent]
    marker_colors: List[str] = ["#e74c3c" if flag else "#2980b9" for flag in is_ng_list]

    # 마지막 값
    last_prob = prob_ng_raw[-1]
    last_prob_percent = prob_ng_percent[-1]
    last_ts = timestamps[-1]

    status_label = "NG" if last_prob >= THRESHOLD else "OK"

    # 최근 N개 평균 (기본값 10개)
    window = min(RECENT_WINDOW_DEFAULT, len(prob_ng_percent))
    recent_slice = prob_ng_percent[-window:]
    avg_prob_percent = sum(recent_slice) / window
    ng_count_recent = sum(1 for p in recent_slice if p >= threshold_percent)
    ng_ratio_recent = (ng_count_recent / window) * 100.0 if window > 0 else 0.0

    # 연속 NG 경고 정보
    streak_info = None
    if len(is_ng_list) >= STREAK_N:
        recent_flags = is_ng_list[-STREAK_N:]
        if all(recent_flags):
            streak_info = {
                "streak_n": STREAK_N,
                "is_streak": True,
            }

    return {
        "has_data": True,
        "timestamps": [ts.isoformat() for ts in timestamps],
        "prob_ng_percent": prob_ng_percent,
        "threshold_percent": threshold_percent,
        "marker_colors": marker_colors,
        "last": {
            "prob_percent": last_prob_percent,
            "status_label": status_label,
            "timestamp": last_ts.isoformat(),
        },
        "recent": {
            "window": window,
            "avg_prob_percent": avg_prob_percent,
            "ng_ratio_recent": ng_ratio_recent,
            "ng_count_recent": ng_count_recent,
        },
        "streak_ng": streak_info,
    }


@router.get("/dashboard/data")
async def get_dashboard_data() -> Dict[str, Any]:
    """
    대시보드에 필요한 데이터를 JSON 형태로 반환.
    프런트에서는 이 데이터를 사용해서 KPI와 Plotly 그래프를 갱신한다.
    """
    return _build_dashboard_metrics()


@router.get("/dashboard", response_class=HTMLResponse)
async def show_dashboard() -> HTMLResponse:
    """
    대시보드 HTML: 한 번만 로드하고, 내부 JS가 /dashboard/data를 주기적으로 호출해서
    KPI/그래프를 부드럽게 갱신한다.
    """
    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="utf-8" />
    <title>Melting Tank Dashboard</title>
    <!-- 브라우저 쪽에서 Plotly를 직접 로딩 -->
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 0 24px 40px 24px;
            background-color: #ffffff;
        }}
        h1 {{
            text-align: center;
            font-size: 34px;
            margin-top: 40px;
            margin-bottom: 20px;
        }}
        .kpi-row {{
            display: flex;
            justify-content: center;
            gap: 16px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .kpi-card {{
            text-align: center;
            padding: 16px 24px;
            border-radius: 12px;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
            background-color: #fafafa;
            min-width: 260px;
        }}
        .kpi-card.main-value {{
            min-width: 280px;
        }}
        .kpi-card.ok {{
            background-color: #f5fff8;
        }}
        .kpi-card.ng {{
            animation: kpi-flash 1.4s ease-in-out 0s 2;
            background-color: #ffeaea;
        }}
        @keyframes kpi-flash {{
            0%   {{ background-color: #ffeaea; }}
            50%  {{ background-color: #ffffff; }}
            100% {{ background-color: #ffeaea; }}
        }}
        .warning-banner {{
            background:#fdeaea;
            border-left:6px solid #e74c3c;
            padding:12px 20px;
            margin:0 auto 16px auto;
            max-width:600px;
            text-align:center;
            font-size:16px;
            color:#c0392b;
        }}
        #chart-container {{
            width: 100%;
            margin: 0 auto;
            padding: 0;
        }}
    </style>
</head>
<body>
    <h1>실시간 불량 발생 확률 추이</h1>

    <div id="warning-container"></div>

    <div class="kpi-row">
        <div id="kpi-main" class="kpi-card main-value">
            <!-- JS에서 채워 넣음 -->
        </div>
        <div id="kpi-avg" class="kpi-card">
            <!-- JS에서 채워 넣음 -->
        </div>
    </div>

    <div id="chart-container">
        <div id="chart"></div>
    </div>

    <script>
        const REFRESH_INTERVAL_MS = {REFRESH_INTERVAL_SEC * 1000};

        async function fetchDashboardData() {{
            const resp = await fetch('/dashboard/data');
            if (!resp.ok) {{
                console.error('Failed to load dashboard data:', resp.status);
                return null;
            }}
            return await resp.json();
        }}

        function renderKpis(data) {{
            const kpiMain = document.getElementById('kpi-main');
            const kpiAvg = document.getElementById('kpi-avg');
            const warningContainer = document.getElementById('warning-container');

            if (!data || !data.has_data) {{
                warningContainer.innerHTML = '';
                kpiMain.className = 'kpi-card main-value';
                kpiAvg.className = 'kpi-card';

                kpiMain.innerHTML = '<div style="font-size:14px; color:#555;">마지막 예측값</div>'
                    + '<div style="font-size:24px; margin-top:4px;">데이터 없음</div>';

                kpiAvg.innerHTML = '<div style="font-size:14px; color:#555;">최근 평균 불량률</div>'
                    + '<div style="font-size:24px; margin-top:4px;">데이터 없음</div>';
                return;
            }}

            const last = data.last;
            const recent = data.recent; 

            const statusColor = last.status_label === 'NG' ? '#e74c3c' : '#2ecc71';
            const mainClass = last.status_label === 'NG'
                ? 'kpi-card main-value ng'
                : 'kpi-card main-value ok';

            // 화면에 보여줄 한글 라벨
            const displayStatus = last.status_label === 'NG' ? '불량' : '정상';

            kpiMain.className = mainClass;
            kpiMain.innerHTML = `
                <div style="font-size:14px; color:#555;">마지막 예측값</div>
                <div style="font-size:40px; font-weight:700; color:${{statusColor}}; margin-top:4px;">
                    ${{last.prob_percent.toFixed(1)}}% (${{displayStatus}})
                </div>
                <div style="font-size:12px; color:#777; margin-top:4px;">
                    기준 Threshold: ${{data.threshold_percent.toFixed(1)}}% · 시각: ${{new Date(last.timestamp).toLocaleString('ko-KR')}}
                </div>
            `;

            kpiAvg.className = 'kpi-card';
            kpiAvg.innerHTML = `
                <div style="font-size:14px; color:#555;">최근 ${{recent.window}}개 평균 불량률</div>
                <div style="font-size:28px; font-weight:700; color:#34495e; margin-top:4px;">
                    ${{recent.avg_prob_percent.toFixed(1)}}%
                </div>
                <div style="font-size:12px; color:#777; margin-top:4px;">
                    이 중 불량 비율: ${{recent.ng_ratio_recent.toFixed(1)}}% (${{recent.ng_count_recent}}/${{recent.window}}개 불량)
                </div>
            `;

            if (data.streak_ng && data.streak_ng.is_streak) {{
                warningContainer.innerHTML = `
                    <div class="warning-banner">
                        ⚠️ 불량 패턴이 연속으로 감지되었습니다 (최근 ${{data.streak_ng.streak_n}}/${{data.streak_ng.streak_n}} NG)
                    </div>
                `;
            }} else {{
                warningContainer.innerHTML = '';
            }}
        }}

        function renderChart(data, isInitial) {{
            const chartDiv = document.getElementById('chart');

            if (!data || !data.has_data || data.timestamps.length === 0) {{
                Plotly.purge(chartDiv);
                return;
            }}

            const x = data.timestamps;
            const y = data.prob_ng_percent;
            const threshold = data.threshold_percent;
            const markerColors = data.marker_colors;

            const traceProb = {{
                x: x,
                y: y,
                mode: 'lines+markers',
                name: '불량 발생 확률(%)',
                marker: {{ color: markerColors, size: 8 }},
                line: {{ color: '#2980b9' }},
                hovertemplate: '시간: %{{x}}<br>불량 발생 확률: %{{y:.1f}}%<extra></extra>',
            }};

            const traceThreshold = {{
                x: [x[0], x[x.length - 1]],
                y: [threshold, threshold],
                mode: 'lines',
                name: `Threshold (${{threshold.toFixed(1)}}%)`,
                line: {{ dash: 'dash', color: 'red' }},
                hovertemplate: `Threshold 기준값: ${{threshold.toFixed(1)}}%<extra></extra>`,
            }};

            const layout = {{
                margin: {{ l: 40, r: 40, t: 60, b: 40 }},
                height: 500,
                xaxis: {{ title: '시간', type: 'date' }},
                yaxis: {{ title: '불량 발생 확률(%)', range: [0, 100] }},
                legend: {{
                    orientation: 'h',
                    x: 0.5,
                    xanchor: 'center',
                    y: 1.1,
                }},
                shapes: [
                    {{
                        type: 'rect',
                        xref: 'x',
                        yref: 'y',
                        x0: x[0],
                        x1: x[x.length - 1],
                        y0: threshold,
                        y1: 100,
                        fillcolor: 'rgba(255, 0, 0, 0.1)',
                        line: {{ width: 0 }},
                        layer: 'below',
                    }}
                ],
            }};

            const config = {{
                responsive: true,
                displaylogo: false,
            }};

            if (isInitial) {{
                Plotly.newPlot(chartDiv, [traceProb, traceThreshold], layout, config);
            }} else {{
                Plotly.react(chartDiv, [traceProb, traceThreshold], layout, config);
            }}
        }}

        async function refreshDashboard(isInitial) {{
            try {{
                const data = await fetchDashboardData();
                renderKpis(data);
                renderChart(data, isInitial);
            }} catch (err) {{
                console.error('Dashboard refresh error:', err);
            }}
        }}

        // 초기 1회 렌더
        refreshDashboard(true);
        // 이후에는 지정한 주기로 KPI/그래프만 갱신 (페이지 깜빡임 없음)
        setInterval(() => refreshDashboard(false), REFRESH_INTERVAL_MS);
    </script>
</body>
</html>
    """
    return HTMLResponse(html)
