from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Resource:
    id: str
    name: str
    title: str


@dataclass(frozen=True)
class Slot:
    start_time: datetime
    resources: list[Resource]
