"""Persistent Wiki identities, explainable discovery, and date-based change views."""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from .store import utcnow, tokens

FOUNDATIONS = [
 ('llm-architecture','LLM 아키텍처','Models'),
 ('rag','RAG · 검색 증강 생성','Retrieval'),
 ('agent-harness','에이전트 하네스 · 오케스트레이션 · MCP','Agents'),
]
DEFAULT_INTERESTS=['LLM','architecture','agent','harness','MCP','RAG','evaluation','inference','orchestration']
SECTIONS={'concept':'핵심 개념','architecture':'구조와 데이터 흐름','algorithms':'알고리즘과 설계 선택',
          'implementation':'구현 절차','use_cases':'적합한 사용 사례','comparisons':'비교와 선택 기준',
          'limitations':'한계 · 실패 모드','evaluation':'평가와 확인 방법'}


def migrate(store):
    db=store.db
    version=db.execute('PRAGMA user_version').fetchone()[0]
    path=db.execute('PRAGMA database_list').fetchone()[2]
    if version<2 and path:
        from pathlib import Path
        import sqlite3
        backup=Path(path+'.pre-wiki-v1.bak')
        if not backup.exists():
            with sqlite3.connect(str(backup)) as destination:db.backup(destination)
    with db:
        existing={r[1] for r in db.execute('PRAGMA table_info(topics)')}
        for name,decl in [('canonical_key','TEXT'),('aliases_json',"TEXT NOT NULL DEFAULT '[]'"),
                          ('wiki_json',"TEXT NOT NULL DEFAULT '{}'"),('foundational','INTEGER NOT NULL DEFAULT 0'),
                          ('relevance','REAL NOT NULL DEFAULT 0.3'),('utility','REAL NOT NULL DEFAULT 0.4'),
                          ('maturity',"TEXT NOT NULL DEFAULT '미평가'"),('rank_reason',"TEXT NOT NULL DEFAULT '{}'"),
                          ('wiki_pending','INTEGER NOT NULL DEFAULT 0')]:
            if name not in existing: db.execute(f'ALTER TABLE topics ADD COLUMN {name} {decl}')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS canonical_identity ON topics(canonical_key) WHERE canonical_key IS NOT NULL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS topic_links (
          topic_id INTEGER REFERENCES topics(id), related_id INTEGER REFERENCES topics(id),
          relation TEXT NOT NULL, PRIMARY KEY(topic_id,related_id,relation));
        CREATE TABLE IF NOT EXISTS wiki_revisions (
          id INTEGER PRIMARY KEY, topic_id INTEGER REFERENCES topics(id), body_json TEXT,
          source_ids TEXT, created_at TEXT, provenance TEXT);
        CREATE TABLE IF NOT EXISTS briefings (
          day TEXT PRIMARY KEY, notion_page_id TEXT, sync_pending INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS briefing_changes (
          day TEXT REFERENCES briefings(day), history_id INTEGER UNIQUE REFERENCES history(id),
          topic_id INTEGER REFERENCES topics(id), text_ko TEXT,
          PRIMARY KEY(day,history_id));
        CREATE TABLE IF NOT EXISTS notion_objects (
          key TEXT PRIMARY KEY, remote_id TEXT NOT NULL, body_hash TEXT);
        CREATE TABLE IF NOT EXISTS selection_log (
          id INTEGER PRIMARY KEY, topic_id INTEGER REFERENCES topics(id), selected INTEGER,
          factors_json TEXT, reason TEXT, created_at TEXT);
        ''')
        db.execute('PRAGMA user_version=2')


def identity(text):
    return ''.join(re.findall(r'[a-z0-9가-힣]+',text.lower()))


def resolve(store, name):
    key=identity(name)
    for t in store.topics():
        aliases=json.loads(t.get('aliases_json','[]'))
        if key in {identity(x) for x in [t['name'],t.get('canonical_key') or '',*aliases]}:
            return t['id']
    return None


def seed_foundations(store):
    migrate(store)
    with store.db:
        for key,name,category in FOUNDATIONS:
            found=resolve(store,key) or resolve(store,name)
            if not found:
                found=store.db.execute('''INSERT INTO topics(name,category,summary,updated_at,sync_pending)
                  VALUES (?,?,?, ?,0)''',(name,category,'기초 주제 · 공식 자료를 바탕으로 위키 작성 대기',utcnow())).lastrowid
            store.db.execute('''UPDATE topics SET canonical_key=?,foundational=1,relevance=1,
              utility=0.95,aliases_json=? WHERE id=?''',(key,json.dumps(sorted(set(json.loads(store.db.execute('SELECT aliases_json FROM topics WHERE id=?',(found,)).fetchone()[0]))|{key,name}),ensure_ascii=False),found))
    return {key:resolve(store,key) for key,_,_ in FOUNDATIONS}


def publish_revision(store,topic_id,wiki,source_ids,*,aliases=(),related=(),provenance='official-source curation',now=None):
    migrate(store); now=now or utcnow()
    required=SECTIONS if wiki.get('depth')=='deep' else ('concept','architecture','use_cases','limitations')
    if not all(isinstance(wiki.get(k),str) and len(wiki[k].strip())>=40 for k in required):
        raise ValueError('Reference needs useful what/how/use/limitations explanations; deep entries need all sections')
    if wiki.get('depth')=='deep' and (not wiki.get('diagram','').startswith('flowchart ') or not wiki.get('code')):
        raise ValueError('Complex technical entries need a meaningful diagram and an implementation example')
    if not wiki.get('citations'):
        raise ValueError('Original-source citations required')
    evidence=[dict(r) for r in store.db.execute('SELECT id,url FROM sources WHERE id IN ('+','.join('?'*len(source_ids))+')',source_ids)] if source_ids else []
    if len(evidence)!=len(set(source_ids)) or not set(wiki['citations'])<={s['url'] for s in evidence}:
        raise ValueError('Wiki citation must resolve to persisted source evidence')
    before=store.db.execute('SELECT * FROM topics WHERE id=?',(topic_id,)).fetchone()
    if before is None: raise ValueError('Unknown persistent topic')
    old=json.loads(before['wiki_json'])
    merged={**old,**wiki}  # Unspecified fields remain; no news-cycle overwrite of conceptual knowledge.
    if merged==old:
        with store.db:
            for source_id in source_ids:
                store.db.execute('INSERT OR IGNORE INTO relationships(source_id,topic_id) VALUES (?,?)',(source_id,topic_id))
        return False
    with store.db:
        old_aliases=json.loads(before['aliases_json'])
        store.db.execute('''UPDATE topics SET wiki_json=?,aliases_json=?,wiki_pending=1,
          updated_at=?,archived=0,utility=max(utility,0.8) WHERE id=?''',(json.dumps(merged,ensure_ascii=False),
          json.dumps(sorted(set(old_aliases)|set(aliases)),ensure_ascii=False),now,topic_id))
        for source_id in source_ids:
            store.db.execute("INSERT OR IGNORE INTO relationships(source_id,topic_id) VALUES (?,?)",(source_id,topic_id))
        for target in related:
            if target!=topic_id:
                store.db.execute("INSERT OR IGNORE INTO topic_links VALUES (?,?,'related')",(topic_id,target))
        store.db.execute('INSERT INTO wiki_revisions(topic_id,body_json,source_ids,created_at,provenance) VALUES (?,?,?,?,?)',
                         (topic_id,json.dumps(merged,ensure_ascii=False),json.dumps(source_ids),now,provenance))
        h=store.db.execute('''INSERT INTO history(topic_id,action,reason,before_json,after_json,created_at)
          VALUES (?,'WikiUpdate',?,?,?,?)''',(topic_id,provenance,json.dumps(dict(before),ensure_ascii=False),json.dumps(merged,ensure_ascii=False),now)).lastrowid
        day=datetime.fromisoformat(now).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
        store.db.execute('INSERT OR IGNORE INTO briefings(day) VALUES (?)',(day,))
        store.db.execute('UPDATE briefings SET sync_pending=1 WHERE day=?',(day,))
        text=f"{before['name']}: 기술 위키 설명·구현·평가 항목을 근거 자료로 보강했습니다. 뉴스의 발생일이 아닌 지식 갱신 기록입니다."
        store.db.execute('INSERT INTO briefing_changes VALUES (?,?,?,?)',(day,h,topic_id,text))
    return True


def rank(store, interests=None, now=None, weights=None):
    migrate(store); now=now or utcnow(); interests=interests if interests is not None else DEFAULT_INTERESTS
    stamp=datetime.fromisoformat(now)
    for t in store.topics():
        wiki=json.loads(t['wiki_json']); age=max(0,(stamp-datetime.fromisoformat(t['updated_at'])).days)
        search=' '.join([t['name'],t['category'],t['summary'],t['aliases_json'],json.dumps(wiki,ensure_ascii=False)]).lower()
        interest_hits=[term for term in interests if term.lower() in search]
        count,credible=store.db.execute('''SELECT count(*),sum(CASE WHEN s.kind IN ('official','arxiv','github')
          THEN 1 ELSE 0 END) FROM relationships r JOIN sources s ON r.source_id=s.id WHERE r.topic_id=?''',(t['id'],)).fetchone()
        adjacent=any(term in search for term in ('embedding','quantization','reasoning','tool','retrieval','context','추론','검색','도구'))
        relevance=max(t['relevance'],0.9 if interest_hits else (.7 if adjacent else .35))  # Adjacent topics retain a path to selection.
        factors={'technical_relevance':relevance,'foundational_importance':float(t['foundational']),
                 'practical_utility':t['utility'],'novelty':min(count/5,1),
                 'credibility':min((credible or 0)/max(count,1),1),'freshness':1/(1+age/30)}
        from .config import DEFAULT_WEIGHTS,validate_weights
        weights=validate_weights(weights or DEFAULT_WEIGHTS)
        score=round(100*sum(factors[k]*weights[k] for k in factors),2)
        ready=bool(wiki) and not t['archived']; selected=ready and score>=55
        reason=('주요 위키에 선택' if selected else '보존하되 주요 화면에서는 제외')+f"; 관심 신호={','.join(interest_hits) or '인접·탐색 후보'}; 기초={bool(t['foundational'])}; 위키완성={bool(wiki)}"
        with store.db:
            store.db.execute('UPDATE topics SET score=?,rank_reason=? WHERE id=?',(score,json.dumps(factors),t['id']))
            store.db.execute('INSERT INTO selection_log(topic_id,selected,factors_json,reason,created_at) VALUES (?,?,?,?,?)',
                             (t['id'],int(selected),json.dumps(factors),reason,now))
    return store.topics()


def search(store, query='',category=None):
    migrate(store); terms=tokens(query)
    return [t for t in store.topics() if (category is None or category==t['category']) and
            (not terms or all(term in tokens(' '.join([t['name'],t['category'],t['aliases_json'],t['wiki_json']])) for term in terms))]


def record_news_change(store,source_id,now):
    row=store.db.execute('''SELECT h.id,h.topic_id,h.action,h.reason,t.name,t.summary,t.wiki_json FROM history h
      JOIN topics t ON t.id=h.topic_id WHERE source_id=? ORDER BY h.id DESC LIMIT 1''',(source_id,)).fetchone()
    if not row:return
    day=datetime.fromisoformat(now).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
    published=store.db.execute('SELECT published FROM sources WHERE id=?',(source_id,)).fetchone()[0]
    with store.db:
        store.db.execute('INSERT OR IGNORE INTO briefings(day) VALUES (?)',(day,))
        wiki=json.loads(row['wiki_json'])
        text=(f"{row['name']} · {'새 근거 추가' if row['action']=='Update' else '신규 검토 후보'}\n"
          f"무엇을 검토했나: {row['summary']}\n왜 중요한가: {row['reason']}\n"
          f"어떻게 작동하나 (기존 기술 해설): {wiki.get('architecture','추가 기술 근거 확인이 필요한 검토 후보입니다.')[:350]}\n"
          f"실무에서의 의미: {wiki.get('use_cases','유용성과 구현 근거를 더 확인한 뒤 위키로 승격합니다.')[:250]}\n"
          f"원문 발행/갱신일: {published or '미상 · 당일 발표라고 단정하지 않음'}")
        store.db.execute('INSERT INTO briefing_changes VALUES (?,?,?,?) ON CONFLICT(day,history_id) DO UPDATE SET text_ko=excluded.text_ko',(day,row['id'],row['topic_id'],text))
        store.db.execute('UPDATE briefings SET sync_pending=1 WHERE day=?',(day,))
