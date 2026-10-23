import json
import logging
from .models import Source
from .store import utcnow


log = logging.getLogger("radar")


def run(store, sources, reasoner, *, archive_days=90, now=None):
    if archive_days <= 0:
        raise ValueError("archive_days must be positive")
    now = now or utcnow()
    with store.db:
        run_id = store.db.execute("INSERT INTO runs(started_at,status) VALUES (?,'running')", (now,)).lastrowid
    counts = {"Create": 0, "Update": 0, "Skip": 0}
    try:
        store.ingest(sources)
        pending = store.db.execute("SELECT * FROM sources WHERE processed=0 ORDER BY id").fetchall()
        for row in pending:
            source = Source(**{k: row[k] for k in Source.__dataclass_fields__})
            analysis = reasoner.analyze(source, store.retrieve(source))
            store.apply(row["id"], analysis, now)
            counts[analysis.decision] += 1
            log.info("run=%s source=%s decision=%s", run_id, row["id"], analysis.decision)
        store.rank_and_archive(now, archive_days)
        with store.db:
            store.db.execute("UPDATE runs SET finished_at=?,status='success',details=? WHERE id=?",
                             (utcnow(), json.dumps(counts), run_id))
        return counts
    except Exception:
        with store.db:
            store.db.execute("UPDATE runs SET finished_at=?,status='failed',details=? WHERE id=?",
                             (utcnow(), json.dumps({"completed": counts}), run_id))
        log.error("run=%s failed; completed source transactions retained", run_id)
        raise
