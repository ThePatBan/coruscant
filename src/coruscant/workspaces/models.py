"""Workspace models."""

from __future__ import annotations

from pydantic import BaseModel, Field

ITEM_TYPES = {"note", "bookmark", "thesis", "comment", "collection"}


class WorkspaceItem(BaseModel):
    id: str
    type: str
    title: str
    body: str = ""
    ref: str | None = None  # optional pointer: canonical_id, company slug, entity key
    author_email: str
    created_at: str


class Workspace(BaseModel):
    id: str
    name: str
    owner_email: str
    members: list[str] = Field(default_factory=list)
    created_at: str
    items: list[WorkspaceItem] = Field(default_factory=list)
