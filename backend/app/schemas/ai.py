from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    suggestions: list[str] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    memories_used: list[str] = Field(default_factory=list)


class PurchaseAnalyzeRequest(BaseModel):
    item: str
    price: float
    currency: str = "RUB"
    notes: str = ""


class PurchaseAnalyzeResponse(BaseModel):
    item: str
    price: float
    capital_pct: float
    work_hours: float
    life_days: float
    months_of_savings: float
    coffee_equivalent: int
    goal_impact: str
    alternatives: list[str]
    wait_advice: str
    recommendation: str
    score: int  # 0-100 buy readiness
    postpone_available: bool = True
    challenge_questions: list[str] = Field(default_factory=list)
    twin_opinion: str = ""
    related_memory: str = ""


class PostponePurchaseRequest(BaseModel):
    item: str
    price: float
    hours: int = 24


class FraudAlert(BaseModel):
    transaction_id: int
    title: str
    reason: str
    severity: str
    amount: float
    merchant: str


class OCRResult(BaseModel):
    date: str | None = None
    merchant: str | None = None
    total: float | None = None
    items: list[dict] = Field(default_factory=list)
    vat: float | None = None
    discounts: float | None = None
    payment_method: str | None = None
    confidence: float = 0.0
    needs_confirmation: bool = False
    conflicts: list[str] = Field(default_factory=list)
    raw_text: str = ""
