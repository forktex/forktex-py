"""Base models shared across the entire ForkTex model graph."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ForkTexModel(BaseModel):
    """Root base for all ForkTex models.

    - extra="allow" so forward-compatible fields don't break deserialization
    - populate_by_name=True so both alias and field name work
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Identifiable(ForkTexModel):
    """Any model with id + name + description."""

    id: str
    name: str
    description: str = ""


class Versioned(ForkTexModel):
    """Any model with version tracking."""

    version: str = "1.0.0"
    status: Literal["draft", "active", "deprecated", "planning"] = "active"
    updated_at: datetime | None = None


class Tagged(ForkTexModel):
    """Any model with free-form tags."""

    tags: list[str] = []
