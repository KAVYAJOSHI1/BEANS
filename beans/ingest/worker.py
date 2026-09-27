"""Continuous ingestion: pick up files from a folder, load them, and score the database in batches.

Why a worker inside the server process: DuckDB lets one *process* write a database file. A separate `beans watch` process
holds the file for the whole scoring run (seconds on a demo, minutes at a million rows), and the dashboard answers
HTTP 500 for all of that time. Inside the server process, the worker's connection and the API's connections share
one database instance, so the dashboard keeps working while the engines run (tested: 70 reads + writes during a 37 s
scoring run, none failed).

Why batches: scoring re-runs every engine over the whole database. Scoring after every file falls behind as soon as
one scoring run takes longer than the gap between files. The worker loads everything that is waiting, then scores
once, and never more often than `score_every` seconds; new files that arrive meanwhile are loaded and wait for the
next scoring run.

Files are moved to `processed/` (or `failed/`) after loading. Files that are still growing are left for the next scan.
The worker writes `watch.status` into the folder every scan, which the dashboard's Live Monitor reads.
"""
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

DATA_SUFFIXES = {".csv", ".json", ".ndjson", ".jsonl", ".xml"}


class IngestWorker:
    def __init__(self, inbox: Path, interval: float = 5.0, score_every: float = 60.0, mapping: Optional[Path] = None,
                 log: Callable[[str], None] = print):
        self.inbox, self.interval, self.score_every, self.mapping, self.log = Path(inbox), interval, score_every, mapping, log
        self.done_dir, self.failed_dir = self.inbox / "processed", self.inbox / "failed"
        self._stop = threading.Event()
        self._sizes: Dict[str, int] = {}
        self.unscored_rows = 0
        self.last_score = 0.0
        self.state = {"pid": os.getpid(), "folder": str(self.inbox), "interval_s": interval, "score_every_s": score_every,
                      "started_at": time.time(), "mode": "in-process", "files_done": 0, "files_failed": 0,
                      "rows_loaded": 0, "unscored_rows": 0, "scoring_runs": 0, "scoring": False, "last_file": None,
                      "last_rows": None, "last_alerts": None, "last_score_s": None, "last_error": None}

    # ------------------------------------------------------------------------------------------------ status
    def write_status(self) -> None:
        self.state.update(updated_at=time.time(), unscored_rows=self.unscored_rows)
        tmp = self.inbox / "watch.status.part"
        tmp.write_text(json.dumps(self.state))
        os.replace(tmp, self.inbox / "watch.status")

    # ------------------------------------------------------------------------------------------------ files
    def ready_files(self) -> List[Path]:
        """Data files whose size has not changed since the previous scan (a writer that renames atomically, like the
        collector, is ready at once: its file never appears half-written)."""
        ready, sizes = [], {}
        for f in sorted(self.inbox.iterdir()):
            if not f.is_file() or f.suffix.lower() not in DATA_SUFFIXES:
                continue
            size = f.stat().st_size
            sizes[f.name] = size
            if self._sizes.get(f.name) == size or time.time() - f.stat().st_mtime > 2 * self.interval:
                ready.append(f)
        self._sizes = sizes
        return ready

    def _move(self, f: Path, to: Path) -> None:
        to.mkdir(exist_ok=True)
        shutil.move(str(f), to / f"{time.strftime('%Y%m%d_%H%M%S')}_{f.name}")

    def load(self, files: List[Path]) -> int:
        """Load files without scoring; returns rows loaded."""
        from beans.ingest.pipeline import ForensicPipeline
        rows = 0
        for f in files:
            try:
                p = ForensicPipeline(mapping=self.mapping)
                p.execute_ml_pipeline = lambda *a: {"skipped": "scored in the next batch"}
                res = p.run_file_ingestion(f, "WATCH")
                n = int(res["records_ingested"])
                rows += n
                self.state.update(files_done=self.state["files_done"] + 1, last_file=f.name, last_rows=n,
                                  rows_loaded=self.state["rows_loaded"] + n, last_error=None)
                self.log(f"→ {f.name}: {n:,} rows, {res['rows_quarantined']:,} quarantined")
                self._move(f, self.done_dir)
            except Exception as e:   # a bad file never stops monitoring; it is set aside for inspection
                self.state.update(files_failed=self.state["files_failed"] + 1, last_error=f"{f.name}: {e}"[:300])
                self.log(f"→ {f.name}: failed ({e}); moved to failed/")
                try:
                    self._move(f, self.failed_dir)
                except OSError:
                    pass
        self.unscored_rows += rows
        return rows

    def score(self) -> dict:
        from beans.ingest.pipeline import ForensicPipeline
        self.state["scoring"] = True
        self.write_status()
        t = time.time()
        try:
            stats = ForensicPipeline().execute_ml_pipeline()
        finally:
            self.state["scoring"] = False
        self.last_score = time.time()
        self.unscored_rows = 0
        self.state.update(scoring_runs=self.state["scoring_runs"] + 1, last_score_s=round(self.last_score - t, 1),
                          last_alerts=stats.get("alerts_generated"), last_scored_at=self.last_score)
        self.log(f"  scored in {self.last_score - t:.1f} s: {stats.get('alerts_generated')} alerts, "
                 f"{stats.get('watch_events', 0)} watched-wallet movements")
        return stats

    # ------------------------------------------------------------------------------------------------ loop
    def step(self) -> None:
        """One scan: load what is ready; score if there is unscored data and the last scoring is old enough."""
        self.inbox.mkdir(parents=True, exist_ok=True)
        files = self.ready_files()
        if files:
            self.load(files)
        if self.unscored_rows and time.time() - self.last_score >= self.score_every:
            try:
                self.score()
            except Exception as e:
                self.state["last_error"] = f"scoring failed: {e}"[:300]
                self.log(f"  scoring failed: {e}")
        self.write_status()

    def run(self, once: bool = False) -> None:
        self.log(f"Watching {self.inbox} every {self.interval:g} s, scoring at most every {self.score_every:g} s")
        while not self._stop.is_set():
            self.step()
            if once:
                if self.unscored_rows:
                    self.score()
                    self.write_status()
                return
            self._stop.wait(self.interval)
        self.state["running"] = False
        self.write_status()

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.run, name="beans-ingest-worker", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()
