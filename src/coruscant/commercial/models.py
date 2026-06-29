"""Organization, plan, usage, and billing models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Plan(BaseModel):
    name: str
    label: str
    max_watchlists: int
    max_api_calls_per_day: int


PLANS: dict[str, Plan] = {
    "free": Plan(name="free", label="Free", max_watchlists=3, max_api_calls_per_day=100),
    "pro": Plan(name="pro", label="Pro", max_watchlists=50, max_api_calls_per_day=10_000),
    "enterprise": Plan(
        name="enterprise", label="Enterprise", max_watchlists=100_000, max_api_calls_per_day=1_000_000
    ),
}
DEFAULT_PLAN = "free"


class Organization(BaseModel):
    id: str
    name: str
    owner_email: str
    plan: str = DEFAULT_PLAN
    members: list[str] = Field(default_factory=list)
    created_at: str


class UsageSummary(BaseModel):
    actions: dict[str, int] = Field(default_factory=dict)
    total: int = 0


class BillingSummary(BaseModel):
    organization_id: str
    plan: Plan
    members: int
    usage: UsageSummary
    api_calls: int
    within_limits: bool
