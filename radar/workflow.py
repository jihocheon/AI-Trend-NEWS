"""Deterministic, bounded research decisions. No claim of autonomous tool planning."""
import json
import re
import time
from .store import utcnow
from .retrieval import retrieve
from .discovery import select


def event(store,run_id,source_id,state,details=None):
    with store.db:
        store.db.execute('''CREATE TABLE IF NOT EXISTS workflow_events (
          id INTEGER PRIMARY KEY,run_id INTEGER REFERENCES runs(id),source_id INTEGER REFERENCES sources(id),
          state TEXT,details_json TEXT,created_at TEXT)''')
        store.db.execute('INSERT INTO workflow_events(run_id,source_id,state,details_json,created_at) VALUES (?,?,?,?,?)',
          (run_id,source_id,state,json.dumps(details or {},ensure_ascii=False),utcnow()))


def investigate(store,run_id,source_id,source,interests=None,weights=None):
    start=time.perf_counter()
    event(store,run_id,source_id,'PLANNING')
    selected,reason=select(store,source_id,source,interests,weights)
    if not selected:
        event(store,run_id,source_id,'REJECTED',{'reason':reason})
        return {'action':'Skip','reason':reason}
    research=retrieve(store,source.title+' '+source.text[:160],k=3)
    event(store,run_id,source_id,'RETRIEVED',{'topic_ids':[t['id'] for t in research['topics']],
      'chunk_ids':[s['chunk_id'] for s in research['evidence']],'latency_ms':round((time.perf_counter()-start)*1000,3)})
    if len(source.text.strip())<80:
        event(store,run_id,source_id,'NEED_EVIDENCE',{'reason':'Source content too short; one additional local retrieval allowed'})
        extra=retrieve(store,source.title,k=5)
        additional=[s for s in extra['evidence'] if s['source_id']!=source_id and len(s['text'])>=100]
        event(store,run_id,source_id,'RESEARCH_RETRY',{'attempt':1,'supporting_chunks':[s['chunk_id'] for s in additional]})
        if not additional:
            event(store,run_id,source_id,'WAITING_EVIDENCE',{'checkpoint':'source remains unprocessed'})
            return {'action':'Investigate','reason':'No adequate supporting evidence after bounded local retrieval'}
        research['evidence']=additional[:3]
    event(store,run_id,source_id,'READY_TO_INFER')
    return {'action':'Infer','research':research,'reason':reason}


def evaluate_summary(source,summary,research=None):
    """Numeric red flags only; not a semantic factuality or entailment verifier."""
    supported=source.title+' '+source.text+' '+' '.join(s['text'] for s in (research or {}).get('evidence',[]))
    figures=re.findall(r'\b\d+(?:\.\d+)?\s*(?:%|ms|GB|TB|tokens/s|배)',summary,re.I)
    return [figure for figure in figures if figure not in supported]
