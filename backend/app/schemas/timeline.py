from pydantic import BaseModel, Field


class TimelineItem(BaseModel):
    id: str
    icon: str
    title: str
    amount: float | None = None
    color: str = "#94a3b8"
    time: str = ""


class TimelineGroup(BaseModel):
    label: str
    date: str
    items: list[TimelineItem] = Field(default_factory=list)
