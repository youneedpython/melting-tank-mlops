# app/dashboard.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import plotly.graph_objs as go
from plotly.subplots import make_subplots

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def show_dashboard():
    timestamps = list(range(10))
    prob_ng = [0.12, 0.18, 0.23, 0.31, 0.48, 0.52, 0.60, 0.74, 0.80, 0.90]

    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(
        go.Scatter(x=timestamps, y=prob_ng, mode="lines+markers", name="NG 확률")
    )
    fig.update_yaxes(range=[0, 1], title="NG Probability")
    fig.update_xaxes(title="Time")
    fig.update_layout(title="실시간 불량 확률 추이", height=500, margin=dict(l=40, r=20, t=60, b=40))

    html = fig.to_html(full_html=False)
    return HTMLResponse(f"<h2>Melting Tank Dashboard</h2>{html}")
