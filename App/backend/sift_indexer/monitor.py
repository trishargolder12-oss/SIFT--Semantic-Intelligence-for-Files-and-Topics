"""Watcher hints plus periodic reconciliation for missed filesystem events."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .indexer import Indexer


log = logging.getLogger(__name__)


class _Handler(FileSystemEventHandler):
    def __init__(self, monitor: "Monitor", root_id: int):
        self.monitor = monitor
        self.root_id = root_id

    def on_any_event(self, event):
        if event.event_type in {"created", "modified", "deleted", "moved"}:
            self.monitor.schedule(self.root_id)


class Monitor:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        self.observer = Observer()
        self.stop = threading.Event()
        self.timers: dict[int, threading.Timer] = {}
        self.timer_generations: dict[int, int] = {}
        self.guard = threading.Lock()
        self.periodic = threading.Thread(target=self._periodic, daemon=True)

    def start(self) -> None:
        self.refresh()
        self.observer.start()
        self.periodic.start()

    def refresh(self) -> None:
        with self.guard:
            self.observer.unschedule_all()
            roots = self.indexer.roots()
            active_ids = {root["id"] for root in roots if root["state"] == "active"}
            for root_id in list(self.timers):
                if root_id not in active_ids:
                    self.timers.pop(root_id).cancel()
                    self.timer_generations[root_id] = self.timer_generations.get(root_id, 0) + 1
            for root in roots:
                path = Path(root["path"])
                if root["state"] == "active" and path.is_dir() and not path.is_symlink():
                    try:
                        self.observer.schedule(_Handler(self, root["id"]), str(path), recursive=True)
                    except OSError:
                        log.exception("Unable to watch approved folder %s", path)

    def schedule(self, root_id: int) -> None:
        with self.guard:
            if self.stop.is_set():
                return
            previous = self.timers.pop(root_id, None)
            if previous:
                previous.cancel()
            generation = self.timer_generations.get(root_id, 0) + 1
            self.timer_generations[root_id] = generation
            timer = threading.Timer(2.0, self._run_hint, args=(root_id, generation))
            timer.daemon = True
            self.timers[root_id] = timer
            timer.start()

    def _run_hint(self, root_id: int, generation: int) -> None:
        with self.guard:
            if self.timer_generations.get(root_id) != generation:
                return
            self.timers.pop(root_id, None)
        if not self.stop.is_set():
            try:
                self.indexer.start_scan(root_id, source="watcher")
            except ValueError:
                # The folder may have been paused or removed after the event fired.
                return

    def _periodic(self) -> None:
        while not self.stop.wait(60):
            for root in self.indexer.roots():
                if root["state"] == "active":
                    try:
                        self.indexer.start_scan(root["id"], source="reconciliation")
                    except ValueError:
                        continue

    def close(self) -> None:
        self.stop.set()
        with self.guard:
            timers, self.timers = self.timers, {}
            for timer in timers.values():
                timer.cancel()
            self.timer_generations = {root_id: generation + 1 for root_id, generation in self.timer_generations.items()}
        self.observer.stop()
        if self.observer.is_alive():
            self.observer.join(timeout=5)
        if self.periodic.is_alive() and self.periodic is not threading.current_thread():
            self.periodic.join(timeout=2)
