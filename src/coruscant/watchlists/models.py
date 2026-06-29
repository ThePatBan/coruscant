"""Watchlist and notification models."""

from __future__ import annotations

from pydantic import BaseModel, Field

WATCH_TYPES = {
    "company",
    "industry",
    "executive",
    "topic",
    "keyword",
    "country",
    "supply_chain",
}


class WatchItem(BaseModel):
    type: str
    value: str


class Watchlist(BaseModel):
    id: str
    name: str
    items: list[WatchItem] = Field(default_factory=list)
    created_at: str


class Notification(BaseModel):
    id: str
    watchlist_id: str = ""
    watch_type: str
    watch_value: str
    kind: str  # "change" | "event"
    title: str
    detail: str
    category: str | None = None
    source_uri: str | None = None
    canonical_id: str | None = None
    created_at: str = ""
    read: bool = False
