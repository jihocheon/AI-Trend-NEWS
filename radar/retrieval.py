"""SQLite FTS5 chunks + persistent identity retrieval, with inspectable provenance."""
import json
from .knowledge import migrate,resolve
from .store import tokens


def index(store,chunk_size=900,overlap=120):
    if not (0<=overlap<chunk_size):raise ValueError('Invalid chunk overlap')
    migrate(store);db=store.db
    db.executescript('''
    CREATE TABLE IF NOT EXISTS chunks (
      id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES sources(id),position INTEGER,text TEXT,
      UNIQUE(source_id,position));
    CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text,content='chunks',content_rowid='id');
    CREATE VIRTUAL TABLE IF NOT EXISTS topic_fts USING fts5(name,aliases,summary,wiki,topic_id UNINDEXED);
    ''')
    with db:
        for s in db.execute('SELECT * FROM sources WHERE id NOT IN (SELECT source_id FROM chunks)').fetchall():
            text=s['title']+'\n'+s['text']
            for position,start in enumerate(range(0,len(text),chunk_size-overlap)):
                content=text[start:start+chunk_size]
                row=db.execute('INSERT INTO chunks(source_id,position,text) VALUES (?,?,?)',(s['id'],position,content)).lastrowid
                db.execute('INSERT INTO chunk_fts(rowid,text) VALUES (?,?)',(row,content))
        db.execute('DELETE FROM topic_fts')
        for t in store.topics():
            db.execute('INSERT INTO topic_fts(name,aliases,summary,wiki,topic_id) VALUES (?,?,?,?,?)',
                       (t['name'],t['aliases_json'],t['summary'],json.dumps({k:v for k,v in json.loads(t['wiki_json']).items() if k not in ('code','diagram','citations','provenance')},ensure_ascii=False),t['id']))


def retrieve(store,query,k=5):
    index(store)
    # Quote individual tokens: external content never becomes executable MATCH syntax.
    terms=sorted(tokens(query))[:24]
    match=' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
    topics={t['id']:t for t in store.topics()}
    exact=resolve(store,query)
    ids=[exact] if exact else []
    spans=[]
    if match:
        for row in store.db.execute('SELECT topic_id,bm25(topic_fts,5,4,1,0.5,0) AS score FROM topic_fts WHERE topic_fts MATCH ? ORDER BY score,topic_id LIMIT ?',(match,k)):
            if row['topic_id'] not in ids:ids.append(row['topic_id'])
        strict=' AND '.join('"'+t.replace('"','""')+'"' for t in terms)
        doc_match=strict if store.db.execute('SELECT count(*) FROM chunk_fts WHERE chunk_fts MATCH ?',(strict,)).fetchone()[0] else match
        for row in store.db.execute('''SELECT c.id AS chunk_id,c.source_id,c.position,c.text,s.url,s.title,
          bm25(chunk_fts) AS score FROM chunk_fts JOIN chunks c ON c.id=chunk_fts.rowid
          JOIN sources s ON s.id=c.source_id WHERE chunk_fts MATCH ? ORDER BY score,c.id LIMIT ?''',(doc_match,k)):
            spans.append(dict(row))
    selected=[topics[i] for i in ids[:k]]
    history=[]
    for t in selected:
        for r in store.db.execute('SELECT id,action,reason,created_at FROM history WHERE topic_id=? ORDER BY id DESC LIMIT 2',(t['id'],)):
            history.append(dict(r))
    return {'topics':selected,'evidence':spans,'history':history,
            'trace':{'query_terms':terms,'identity_match':exact,'method':'identity + SQLite FTS5 BM25','k':k}}
