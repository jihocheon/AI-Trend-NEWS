from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    external_id: str
    kind: str
    title: str
    url: str
    text: str
    published: str


@dataclass(frozen=True)
class Analysis:
    topic: str
    category: str
    summary: str
    decision: str
    target_id: int | None = None
    reason: str = ""
