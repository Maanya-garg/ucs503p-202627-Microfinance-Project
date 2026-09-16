from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    admin, anomalies, auth, dashboard, geo, individuals, lenders, links, loan_requests,
    offers, shgs,
)

app = FastAPI(
    title="Dual-Path Microfinance Credit Scoring API",
    description=(
        "Individual credit scoring bootstrapped from SHG group trust (or a flat "
        "independent base), an XGBoost+SHAP scoring engine, SHG-lender linkage, "
        "and a lender-matching marketplace."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo project -- tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(individuals.router)
app.include_router(shgs.router)
app.include_router(lenders.router)
app.include_router(links.router)
app.include_router(offers.router)
app.include_router(loan_requests.router)
app.include_router(geo.router)
app.include_router(anomalies.router)
app.include_router(dashboard.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {"status": "ok", "message": "Microfinance credit scoring API is live. See /docs for the full API."}
