"""Схемы данных API."""
from datetime import date

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    id: str
    date: date
    desc: str
    amount: float = Field(description="Списание > 0, поступление < 0")
    cat: str = ""
    details: str = ""


class ClaimPart(BaseModel):
    label: str
    sum: float


class Factor(BaseModel):
    """Что повлияло на шанс успеха: подпись и вклад в процентных пунктах."""
    label: str
    impact: int


class CaseOut(BaseModel):
    """Найденный случай: что вернуть, сколько, на каком основании и кому писать."""
    id: str
    kind: str
    title: str
    sub: str
    parts: list[ClaimPart]
    basis: list[str]
    evidence: list[str] = []
    chance: int = 0
    to: str
    deadline: str = ""
    ai: bool = False
    amount: float = 0
    ml: bool = False  # найден ML-сканером, а не правилом
    confidence: float = 0  # уверенность сканера, 0..1
    chance_source: str = "expert"  # "expert" (вес по типу дела) или "ml" (модель скоринга)
    expert_chance: int = 0
    factors: list[Factor] = []


class AnalysisResult(BaseModel):
    source: str
    transactions: list[Transaction]
    cases: list[CaseOut]


class ClaimRequest(BaseModel):
    case: CaseOut
    transactions: list[Transaction] = []


class ClaimResponse(BaseModel):
    text: str
    source: str  # "ai" или "template"
    note: str = ""


class ScanRequest(BaseModel):
    transactions: list[Transaction]
    cases: list[CaseOut] = []


class ScanResponse(BaseModel):
    cases: list[CaseOut]


class ScoreRequest(BaseModel):
    cases: list[CaseOut]
    transactions: list[Transaction] = []


class ScoreResponse(BaseModel):
    cases: list[CaseOut]
