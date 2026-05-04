from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Score = Annotated[int, Field(ge=0, le=100, description="Скоринг лида 0–100")]


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    REJECTED = "rejected"
    CONVERTED = "converted"


class Lead(BaseModel):
    """Доменный контракт лида (Pydantic). Схема БД — migrations/001–003."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: UUID | None = None
    source: str = Field(..., min_length=1, max_length=64)
    external_id: str = Field(..., min_length=1, max_length=256)
    status: LeadStatus = LeadStatus.NEW
    score: Score = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source_listing_uuid: UUID | None = None
    price_total_usd: int | None = Field(default=None, ge=0)
    price_m2_usd: int | None = Field(default=None, ge=0)
    published_at: datetime | None = None
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = None
    district: str | None = None
    area_m2: Decimal | None = Field(default=None, ge=0)
    rooms: int | None = Field(default=None, ge=0)
    floor: str | None = Field(default=None, max_length=64)
    description: str | None = None
    is_owner: bool = False
