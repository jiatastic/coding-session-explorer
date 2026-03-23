from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import Session


class BaseCrawler(ABC):
    @abstractmethod
    def discover(self) -> list[str]: ...

    @abstractmethod
    def parse(self, path: str) -> Session | None: ...

    def crawl_all(self) -> list[Session]:
        sessions: list[Session] = []
        for path in self.discover():
            try:
                session = self.parse(path)
                if session:
                    sessions.append(session)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] skipping {path}: {exc}")
        return sessions
