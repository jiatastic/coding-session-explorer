from __future__ import annotations

from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class SessionEventHandler(FileSystemEventHandler):
    def __init__(self, callback) -> None:
        self.callback = callback

    def on_created(self, event: FileSystemEvent) -> None:  # noqa: ARG002
        if event.is_directory:
            return
        self._emit(event)

    def on_modified(self, event: FileSystemEvent) -> None:  # noqa: ARG002
        if event.is_directory:
            return
        self._emit(event)

    def _emit(self, event: FileSystemEvent) -> None:
        path = Path(str(event.src_path))
        if path.suffix not in {".jsonl", ".db"}:
            return
        self.callback(str(path))


def create_observer(paths, callback):
    observer = Observer()
    handler = SessionEventHandler(callback)
    for value in paths:
        observer.schedule(handler, str(value), recursive=True)
    return observer
