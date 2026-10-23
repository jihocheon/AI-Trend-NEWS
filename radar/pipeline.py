import json
import logging
from .models import Source, Analysis
from .store import utcnow


log = logging.getLogger("radar")


def run(store, sources, reasoner, *, archive_days=90, now=None, curate=False, interests=None, weights=None):
    if archive_days <= 0:
        raise ValueError("archive_days must be positive")
    if curate:
        from .knowledge import migrate
        migrate(store)
    now = now or utcnow()
    with store.db:
        run_id = store.db.execute("INSERT INTO runs(started_at,status) VALUES (?,'running')", (now,)).lastrowid
    counts = {"Create": 0, "Update": 0, "Skip": 0}
    try:
        store.ingest(sources)
        pending = store.db.execute("SELECT * FROM sources WHERE processed=0 ORDER BY id").fetchall()
        for row in pending:
            source = Source(**{k: row[k] for k in Source.__dataclass_fields__})
            if curate:
                from .workflow import investigate,event,evaluate_summary
                plan=investigate(store,run_id,row['id'],source,interests,weights)
                if plan['action']=='Investigate':
                    continue
                if plan['action']=='Skip':
                    analysis=Analysis('','','','Skip',reason=plan['reason'])
                else:
                    research=plan['research']
                    from .intelligence import GeminiReasoner
                    policy=getattr(reasoner,'policy',None)
                    if policy is not None and getattr(policy,'requests',0)>=getattr(policy,'max_requests',float('inf')):
                        event(store,run_id,row['id'],'PAUSED_BUDGET',{'checkpoint':'source remains pending; no generation attempt'})
                        break
                    event(store,run_id,row['id'],'INFERENCING')
                    analysis=reasoner.analyze(source,research['topics'],research=research) if isinstance(reasoner,GeminiReasoner) else reasoner.analyze(source,research['topics'])
                    redflags=evaluate_summary(source,analysis.summary,research)
                    if redflags:
                        event(store,run_id,row['id'],'WAITING_REVIEW',{'unsupported_numeric_claims':redflags})
                        continue
                    event(store,run_id,row['id'],'EVALUATED',{'decision':analysis.decision})
            else:
                analysis = reasoner.analyze(source, store.retrieve(source))
            applied = store.apply(row["id"], analysis, now) or analysis.decision
            if curate:
                from .knowledge import record_news_change
                record_news_change(store,row['id'],now)
                event(store,run_id,row['id'],'COMPLETED',{'decision':applied})
            counts[applied] += 1
            log.info("run=%s source=%s decision=%s", run_id, row["id"], applied)
        store.rank_and_archive(now, archive_days)
        if curate:
            from .knowledge import rank
            rank(store,interests,now,weights)
        remaining=store.db.execute('SELECT count(*) FROM sources WHERE processed=0').fetchone()[0]
        with store.db:
            store.db.execute("UPDATE runs SET finished_at=?,status=?,details=? WHERE id=?",
                             (utcnow(), 'partial' if remaining else 'success', json.dumps({**counts,**({'pending':remaining} if remaining else {})}), run_id))
        return counts
    except Exception:
        if curate:
            from .workflow import event
            event(store,run_id,None,'BLOCKED',{'checkpoint':'completed decisions retained; pending sources retryable'})
        with store.db:
            store.db.execute("UPDATE runs SET finished_at=?,status='failed',details=? WHERE id=?",
                             (utcnow(), json.dumps({"completed": counts}), run_id))
        log.error("run=%s failed; completed source transactions retained", run_id)
        raise
