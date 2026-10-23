import json
import hashlib
import re
import sqlite3
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def tokens(text):
    return set(re.findall(r"[a-z0-9]{3,}", text.lower())) - {"the", "and", "with", "for", "from", "that"}


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sources (
          id INTEGER PRIMARY KEY, kind TEXT NOT NULL, external_id TEXT NOT NULL,
          title TEXT, url TEXT, text TEXT, published TEXT, content_hash TEXT NOT NULL, processed INTEGER DEFAULT 0,
          UNIQUE(kind, external_id, content_hash));
        CREATE TABLE IF NOT EXISTS topics (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT, summary TEXT,
          updated_at TEXT NOT NULL, archived INTEGER DEFAULT 0, score REAL DEFAULT 0,
          notion_page_id TEXT, notion_block_id TEXT, sync_pending INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS relationships (
          source_id INTEGER REFERENCES sources(id), topic_id INTEGER REFERENCES topics(id),
          relation TEXT NOT NULL DEFAULT 'evidence', PRIMARY KEY(source_id,topic_id));
        CREATE TABLE IF NOT EXISTS history (
          id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id),
          topic_id INTEGER REFERENCES topics(id), action TEXT NOT NULL, reason TEXT,
          before_json TEXT, after_json TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT, details TEXT);
        ''')

    def close(self):
        self.db.close()

    def ingest(self, sources):
        with self.db:
            for s in sources:
                if not s.external_id or not s.title:
                    continue
                self.db.execute('''INSERT OR IGNORE INTO sources
                  (kind,external_id,title,url,text,published,content_hash) VALUES (?,?,?,?,?,?,?)''',
                  (s.kind, s.external_id, s.title, s.url, s.text[:20000], s.published,
                   hashlib.sha256(json.dumps([s.title, s.url, s.text, s.published]).encode()).hexdigest()))

    def topics(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM topics ORDER BY score DESC,id")]

    def retrieve(self, source, limit=5):
        query = tokens(source.title + " " + source.text)
        ranked = []
        for topic in self.topics():
            terms = tokens(topic["name"] + " " + topic["summary"])
            similarity = len(query & terms) / max(1, len(query | terms))
            if similarity:
                ranked.append({**topic, "similarity": similarity})
        return sorted(ranked, key=lambda x: (-x["similarity"], x["id"]))[:limit]

    def apply(self, source_id, analysis, now):
        a = analysis
        if a.decision not in {"Create", "Update", "Skip"}:
            raise ValueError("Unsupported decision")
        with self.db:
            source = self.db.execute("SELECT processed FROM sources WHERE id=?", (source_id,)).fetchone()
            if not source or source[0]:
                return
            before = None
            topic_id = None
            if a.decision == "Update":
                before = self.db.execute("SELECT * FROM topics WHERE id=?", (a.target_id,)).fetchone()
                if before is None:
                    raise ValueError("Update target does not exist")
                topic_id = a.target_id
                self.db.execute('''UPDATE topics SET summary=?,category=?,updated_at=?,archived=0,
                  sync_pending=1 WHERE id=?''', (a.summary, a.category, now, topic_id))
            elif a.decision == "Create":
                topic_id = self.db.execute('''INSERT INTO topics(name,category,summary,updated_at)
                  VALUES (?,?,?,?)''', (a.topic, a.category, a.summary, now)).lastrowid
            if topic_id:
                self.db.execute("INSERT INTO relationships(source_id,topic_id) VALUES (?,?)", (source_id, topic_id))
            after = self.db.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
            self.db.execute('''INSERT INTO history(source_id,topic_id,action,reason,before_json,after_json,created_at)
              VALUES (?,?,?,?,?,?,?)''', (source_id, topic_id, a.decision, a.reason,
                json.dumps(dict(before)) if before else None,
                json.dumps(dict(after)) if after else None, now))
            self.db.execute("UPDATE sources SET processed=1 WHERE id=?", (source_id,))

    def rank_and_archive(self, now, archive_days=90):
        stamp = datetime.fromisoformat(now)
        with self.db:
            for t in self.topics():
                age = max(0, (stamp - datetime.fromisoformat(t["updated_at"])).total_seconds() / 86400)
                count, diversity = self.db.execute('''SELECT count(*),count(DISTINCT s.kind)
                  FROM relationships r JOIN sources s ON s.id=r.source_id WHERE r.topic_id=?''', (t["id"],)).fetchone()
                score = round((count + 2 * diversity) / (1 + age / 30), 4)
                self.db.execute("UPDATE topics SET score=? WHERE id=?", (score, t["id"]))
                if age >= archive_days and not t["archived"]:
                    self.db.execute("UPDATE topics SET archived=1,sync_pending=1 WHERE id=?", (t["id"],))
                    self.db.execute('''INSERT INTO history(topic_id,action,reason,created_at)
                      VALUES (?,'Archive','Inactive beyond retention window',?)''', (t["id"], now))
