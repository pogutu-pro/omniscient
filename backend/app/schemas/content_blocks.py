"""Generative UI content blocks.

The model is never allowed to emit free-form UI — that would mean trusting
it to produce safe, well-formed markup, which breaks the same rule the
rest of this codebase already enforces for data and authorization (see
tools/registry.py). Instead, every block here is built deterministically
in `agents/content_blocks.py` from a tool's own typed, already-validated
result. The LLM only ever sees the same tool results and writes the prose
that accompanies them; it never constructs a block itself.

Each block type is intentionally small and generic (a table, a card, a
list, ...) rather than one bespoke shape per tool, so the frontend has a
fixed, closed set of renderers to maintain no matter how many tools exist.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class TableColumn(BaseModel):
    key: str
    label: str
    align: Literal["left", "right"] = "left"


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str | None = None
    columns: list[TableColumn]
    rows: list[dict]


class ListItem(BaseModel):
    title: str
    description: str = ""
    meta: str | None = None
    badge: str | None = None


class ListBlock(BaseModel):
    type: Literal["list"] = "list"
    title: str | None = None
    items: list[ListItem]


class FieldItem(BaseModel):
    label: str
    value: str


class BlockAction(BaseModel):
    label: str
    href: str


class CardBlock(BaseModel):
    type: Literal["card"] = "card"
    title: str
    subtitle: str | None = None
    image_url: str | None = None
    badge: str | None = None
    badge_tone: Literal["neutral", "verified", "warning", "error", "info"] = "neutral"
    fields: list[FieldItem] = Field(default_factory=list)
    actions: list[BlockAction] = Field(default_factory=list)


class ComparisonBlock(BaseModel):
    type: Literal["comparison"] = "comparison"
    title: str | None = None
    items: list[CardBlock]


class FileItem(BaseModel):
    name: str
    url: str
    kind: Literal["pdf", "image", "document", "other"] = "other"
    description: str | None = None


class FileBlock(BaseModel):
    type: Literal["file"] = "file"
    title: str | None = None
    files: list[FileItem]


class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    url: str
    alt: str = ""
    caption: str | None = None


class ChartSeriesItem(BaseModel):
    label: str
    value: float


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    chart_type: Literal["bar"] = "bar"
    title: str | None = None
    unit: str | None = None
    series: list[ChartSeriesItem]


ContentBlock = Annotated[
    Union[TableBlock, ListBlock, CardBlock, ComparisonBlock, FileBlock, ImageBlock, ChartBlock],
    Field(discriminator="type"),
]
