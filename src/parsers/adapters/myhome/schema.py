"""Pydantic-схемы ответов api-statements.tnet.ge (список и карточка).

Каждое описанное поле следует шаблону: «JSON API → колонка Lead / JSONB»
(канонический индекс соответствий — ``myhome_api_schema.csv`` в этом пакете).
Остальные ключи допускаются через ``extra='allow'`` и сохраняются в ``myhome_statement_json``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MyHomeListItem(BaseModel):
    """Элемент ``data.data[]`` из GET ``/v1/statements/``."""

    model_config = ConfigDict(extra="allow")

    id: int = Field(description="Уникальный ID объявления → Lead.external_id (строкой)")
    uuid: str | None = Field(
        default=None,
        description="Публичный UUID карточки → source_listing_uuid",
    )
    price: dict[str, Any] | None = Field(
        default=None,
        description="Цены по валютам: ``1``=GEL (price_gel), ``2``=USD (price_usd / price_m2_usd)",
    )
    created_at: Any | None = Field(default=None, description="ISO или timestamp → published_at")
    last_updated: str | None = Field(
        default=None,
        description="Строковый локальный timestamp списка",
    )


class MyHomeStatementPayload(BaseModel):
    """Объект ``data.statement`` из GET ``/v1/statements/{id}``."""

    model_config = ConfigDict(extra="allow")

    id: int = Field(description="Числовой ID → Lead.external_id")
    uuid: str | None = Field(default=None, description="UUID карточки → source_listing_uuid")
    deal_type_id: int | None = Field(default=None, description="Тип сделки (справочник API)")
    real_estate_type_id: int | None = Field(default=None, description="Тип недвижимости")
    status_id: int | None = Field(default=None, description="Статус объявления в API")
    address: str | None = Field(default=None, description="Текст адреса → address")
    district_name: str | None = Field(default=None, description="Район → district")
    city_name: str | None = Field(default=None, description="Город (оставляется в JSON snapshot)")
    comment: str | None = Field(default=None, description="Описание → description")
    area: float | int | None = Field(default=None, description="Площадь м² → area_m2")
    floor: int | None = Field(default=None, description="Этаж (часть floor)")
    total_floors: int | None = Field(default=None, description="Этажность дома (часть floor)")
    lat: float | None = Field(default=None, description="Широта → geo_lat")
    lng: float | None = Field(default=None, description="Долгота → geo_lng")
    views: int | None = Field(default=None, description="Просмотры → listing_views")
    is_owner: bool | None = Field(default=None, description="Признак собственника → is_owner")
    created_at: str | None = Field(
        default=None,
        description="Дата создания записи API → published_at",
    )
    last_updated: str | None = Field(default=None, description="Строковое время обновления в GMT+4")
    price: dict[str, Any] | None = Field(
        default=None,
        description="Цены по валютам: ``1``=GEL, ``2``=USD (основная валюта — currency_id)",
    )
    images: list[Any] | None = Field(default=None, description="Галерея (сырой JSON)")
    nearby_places: dict[str, Any] | None = Field(default=None, description="Инфраструктура рядом")
    parameters: list[Any] | None = Field(default=None, description="Доп. параметры карточки")
    user_phone_number: str | None = Field(
        default=None,
        description="Маскированный телефон из API; не подставлять в Lead.phone",
    )
    owner_name: str | None = Field(
        default=None,
        description="Имя владельца в API (PII — только snapshot)",
    )
