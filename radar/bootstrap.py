"""Small curated starter references, independent of daily news (no LLM calls)."""
import json
from pathlib import Path
from .models import Source
from .knowledge import migrate,seed_foundations,publish_revision,rank


def bootstrap(store,http,interests=None,weights=None):
    migrate(store)
    candidates=json.loads(Path(__file__).with_name('data').joinpath('curated.json').read_text())
    # Fetch authoritative originals before publishing the corresponding reference.
    snapshots={}
    for c in candidates:
        for url in c['citations']:
            if url not in snapshots:
                if url.startswith('https://arxiv.org/abs/'):
                    import xml.etree.ElementTree as ET
                    identifier=url.rsplit('/',1)[-1]
                    raw=http.request('GET','https://export.arxiv.org/api/query?id_list='+identifier)
                    entry=ET.fromstring(raw).find('{http://www.w3.org/2005/Atom}entry')
                    if entry is None:raise ValueError('Original paper metadata unavailable')
                    ns={'a':'http://www.w3.org/2005/Atom'}
                    snapshots[url]=Source(url,'arxiv',entry.findtext('a:title','',ns),url,
                        entry.findtext('a:summary','',ns),entry.findtext('a:published','',ns))
                else:
                    text=http.request('GET',url).decode()
                    snapshots[url]=Source(url,'official',url.rsplit('/',1)[-1],url,text,'')
    store.ingest(snapshots.values())
    ids=seed_foundations(store)
    updated=0
    for c in candidates:
        key=c['key'];source_ids=[]
        for url in c['citations']:
            source_ids.append(store.db.execute('SELECT id FROM sources WHERE kind=? AND external_id=? ORDER BY id DESC LIMIT 1',(snapshots[url].kind,url)).fetchone()[0])
        with store.db:
            for source_id in source_ids:store.db.execute('UPDATE sources SET processed=1 WHERE id=?',(source_id,))
        wiki={k:v for k,v in c.items() if k not in ('key','aliases')}
        updated+=publish_revision(store,ids[key],wiki,source_ids,aliases=c['aliases'],
                                  related=[v for k,v in ids.items() if k!=key],provenance=c['provenance'])
        with store.db:store.db.execute('UPDATE topics SET maturity=? WHERE id=?',(c['maturity'],ids[key]))
    rank(store,interests,weights=weights)
    return {'curated_candidates':len(candidates),'updated_references':updated,'generation_requests':0}
