# main.py
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
import joblib, pandas as pd, numpy as np, os

# ── Security middleware ──────────────────────────────────────────────
VALID_API_KEY = os.environ["MCP_API_TOKEN"]   # set in Render dashboard, never in code

def verify_api_key(request: Request) -> bool:
    key = request.headers.get("x-api-key") or request.headers.get("authorization", "").replace("Bearer ", "")
    return key == VALID_API_KEY

# ── Load model ───────────────────────────────────────────────────────

model   = joblib.load("sla_classifier.joblib")
encoder = joblib.load("sla_classifier.joblib")

# ── FastMCP app ──────────────────────────────────────────────────────
mcp = FastMCP("SLA Risk Scorer")

@mcp.tool()
def score_sla_risk(
    priority: int,
    category: str,
    time_since_opened_hours: float,
    time_to_sla_breach_hours: float,
    assignment_group: str,
    hour_of_day: int,
    day_of_week: int,
    reassignment_count: int,
    reopen_count: int,
    description_length: int
) -> dict:
    """
    Predicts SLA breach probability for a ServiceNow incident.
    Returns risk_score (0.0-1.0) and risk_band (Low/Medium/High).
    """
    features = pd.DataFrame([{
        "priority": priority,
        "category": category,
        "time_since_opened": time_since_opened_hours,
        "time_to_sla_breach": time_to_sla_breach_hours,
        "assignment_group": assignment_group,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "reassignment_count": reassignment_count,
        "reopen_count": reopen_count,
        "description_length": description_length
    }])

    X = encoder.transform(features)
    prob = float(model.predict_proba(X)[0][1])
    band = "High" if prob >= 0.70 else "Medium" if prob >= 0.45 else "Low"

    importances = model.feature_importances_
    top3_idx    = np.argsort(importances)[-3:][::-1]
    top_features = list(encoder.get_feature_names_out()[top3_idx])

    return {
        "risk_score":    round(prob, 4),
        "risk_band":     band,
        "top_features":  top_features,
        "model_version": "rf_v2"
    }

@mcp.tool()
def health_check() -> dict:
    """Health check endpoint — returns model status."""
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "model_version": "rf_v2"
    }

# ── Mount with API key guard ─────────────────────────────────────────
# FastMCP streamable HTTP — middleware approach
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.applications import Starlette

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow health check without auth
        if request.url.path == "/health":
            return await call_next(request)
        if not verify_api_key(request):
            return JSONResponse(
                {"error": "Unauthorized — invalid or missing API key"},
                status_code=401
            )
        return await call_next(request)

# Get the underlying ASGI app from FastMCP with streamable-http transport
app = mcp.http_app(transport="streamable-http")
app.add_middleware(APIKeyMiddleware)

# Bare health route (no auth needed for Render health checks)
from starlette.routing import Route
async def health(request):
    return JSONResponse({"status": "ok"})
