"""Interest-guided but open-ended, explainable source triage."""
import json
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from .knowledge import DEFAULT_INTERESTS
from .store import utcnow


def select(store,source_id,source,interests=None,weights=None):
    interests=DEFAULT_INTERESTS if interests is None else interests
    text=(source.title+' '+source.text).lower()
    hits=[x for x in interests if x.lower() in text]
    adjacent=any(x in text for x in ('embedding','retrieval','token','attention','quantization','reasoning','tool','benchmark'))
    try:
        try:published=datetime.fromisoformat(source.published.replace('Z','+00:00'))
        except ValueError:published=parsedate_to_datetime(source.published)
        if published.tzinfo is None:published=published.replace(tzinfo=timezone.utc)
        age=max(0,(datetime.now(timezone.utc)-published).days)
        freshness=1/(1+age/30)
    except (ValueError,TypeError,OverflowError):freshness=.3
    seen=store.db.execute('SELECT count(*) FROM sources WHERE kind=? AND external_id=? AND id<>?',
                          (source.kind,source.external_id,source_id)).fetchone()[0]
    factors={'technical_relevance' :.95 if hits else (.7 if adjacent else .25),
      'foundational_importance':.7 if any(x in text for x in ('architecture','protocol','framework','evaluation')) else .2,
      'practical_utility':.8 if source.kind in ('official','github') else .5,
      'novelty':.25 if seen else .7,'credibility':.9 if source.kind in ('official','arxiv','github') else .6,
      'freshness':freshness}
    from .config import DEFAULT_WEIGHTS,validate_weights
    weights=validate_weights(weights or DEFAULT_WEIGHTS)
    score=sum(factors[k]*w for k,w in weights.items())
    selected=score>=.50
    reason=f"{'선택' if selected else '보류'}: 점수={score:.3f}, 관심 신호={','.join(hits) or '인접 분야 탐색'}, 최신성 가중치={weights['freshness']:.0%}"
    with store.db:
        store.db.execute('''CREATE TABLE IF NOT EXISTS source_selection (
          id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES sources(id),selected INTEGER,
          score REAL,factors_json TEXT,reason TEXT,created_at TEXT)''')
        store.db.execute('INSERT INTO source_selection(source_id,selected,score,factors_json,reason,created_at) VALUES (?,?,?,?,?,?)',
          (source_id,int(selected),score,json.dumps(factors),reason,utcnow()))
    return selected,reason
