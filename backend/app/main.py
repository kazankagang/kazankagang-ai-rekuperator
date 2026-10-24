"""AI-Рекуператор: API и раздача фронтенда.

Запуск из корня репозитория:
    uvicorn backend.app.main:app --reload
"""
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import dashboard, llm
from .claims import template_claim
from .models import AnalysisResult, ClaimRequest, ClaimResponse, ScanRequest, ScanResponse
from .rules import detect
from .statement import StatementError, parse_csv

ROOT = Path(__file__).resolve().parents[2]
DEMO_CSV = ROOT / "data" / "demo_statement.csv"
FRONTEND = ROOT / "frontend"
MAX_UPLOAD = 2 * 1024 * 1024

app = FastAPI(title="AI-Рекуператор", version="0.2.0")
# Android-приложение открывает страницы со своего адреса (https://localhost) и ходит в API отсюда.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _analyze(text: str, source: str) -> AnalysisResult:
    try:
        txs = parse_csv(text)
    except StatementError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return AnalysisResult(source=source, transactions=txs, cases=detect(txs))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ai_enabled": llm.ai_enabled(), "model": llm.MODEL}


@app.get("/api/demo", response_model=AnalysisResult)
def demo() -> AnalysisResult:
    return _analyze(DEMO_CSV.read_text(encoding="utf-8"), "demo")


@app.post("/api/analyze", response_model=AnalysisResult)
async def analyze(file: UploadFile = File(...)) -> AnalysisResult:
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Файл больше 2 МБ.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1251", errors="replace")
    return _analyze(text, file.filename or "upload.csv")


@app.post("/api/claim", response_model=ClaimResponse)
def claim(req: ClaimRequest) -> ClaimResponse:
    evidence = [t for t in req.transactions if t.id in set(req.case.evidence)]
    if not llm.ai_enabled():
        return ClaimResponse(text=template_claim(req.case, evidence), source="template",
                             note="Ключ Claude API не задан, показан шаблон.")
    try:
        return ClaimResponse(text=llm.generate_claim(req.case, evidence), source="ai")
    except (anthropic.APIError, RuntimeError) as e:
        return ClaimResponse(text=template_claim(req.case, evidence), source="template",
                             note=f"ИИ недоступен ({e.__class__.__name__}), показан шаблон.")


@app.post("/api/ai-scan", response_model=ScanResponse)
def ai_scan(req: ScanRequest) -> ScanResponse:
    if not llm.ai_enabled():
        raise HTTPException(status_code=503, detail="Доп. проверка ИИ недоступна: не задан ключ Claude API.")
    try:
        return ScanResponse(cases=llm.scan_statement(req.transactions, req.cases))
    except anthropic.RateLimitError as e:
        raise HTTPException(status_code=429, detail="Слишком много запросов к ИИ. Попробуйте через минуту.") from e
    except (anthropic.APIError, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=f"ИИ не ответил: {e}") from e


@app.get("/api/dashboard")
def bank_dashboard() -> dict:
    return dashboard.build()


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
