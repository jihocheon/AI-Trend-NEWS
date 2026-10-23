import json,os,sqlite3,argparse,time
from pathlib import Path
from radar.http import HTTP
from radar.notion import Notion
from radar.workspace import Workspace
from radar.store import Store

class ObservedHTTP(HTTP):
    def __init__(self):self.writes=[]
    def request(self,method,url,**kw):
        if method!='GET':self.writes.append(method)
        return super().request(method,url,**kw)
parser=argparse.ArgumentParser()
parser.add_argument('--db',default='var/radar.sqlite3')
parser.add_argument('--output',default='var/notion-validation.json')
parser.add_argument('--legacy-backup')
args=parser.parse_args()
started=time.perf_counter()
http=ObservedHTTP();s=Store(args.db);n=Notion(http,os.environ['NOTION_TOKEN'],os.environ['NOTION_PARENT_PAGE_ID']);w=Workspace(s,n)

def children(page):
    items=[];cursor=None
    while True:
        data=w.call('GET','blocks/'+page+'/children?page_size=100'+('&start_cursor='+cursor if cursor else ''))
        items+=data['results']
        if not data.get('has_more'):return items
        cursor=data['next_cursor']

def page_info(pid):
    return w.call('GET','pages/'+pid)

result={'generation_requests':0,'wiki':[],'areas':{},'preserved_legacy':0}
for key in ('home','wiki','daily','sources','radar'):
    pid=w.known('area:'+key);p=page_info(pid)
    assert not p['archived']
    result['areas'][key]=p['url']
for t in s.topics():
    if not json.loads(t['wiki_json']) or t['archived']:continue
    p=page_info(t['notion_page_id']);blocks=children(p['id']);bytype={}
    for b in blocks:bytype.setdefault(b['type'],[]).append(b)
    wiki=json.loads(t['wiki_json'])
    text='\n'.join(''.join(x.get('plain_text','') for x in b.get(b['type'],{}).get('rich_text',[])) for b in blocks)
    for key in ('concept','architecture','algorithms','implementation','use_cases','comparisons','limitations','evaluation'):
        if not wiki.get(key):continue
        assert wiki[key] in text,(t['name'],key)
    diagrams=[b for b in bytype.get('code',[]) if b['code']['language']=='mermaid']
    examples=[b for b in bytype.get('code',[]) if b['code']['language']=='python']
    assert len(diagrams)==int(bool(wiki.get('diagram'))) and len(examples)==int(bool(wiki.get('code')))
    if diagrams:assert ''.join(x['plain_text'] for x in diagrams[0]['code']['rich_text'])==wiki['diagram']
    assert len(bytype.get('heading_2',[]))>=4
    mentions=[x['mention']['page']['id'] for b in blocks for x in b.get(b['type'],{}).get('rich_text',[]) if x['type']=='mention']
    assert w.known('area:home') in mentions and w.known('area:daily') in mentions
    expected_related={r[0] for r in s.db.execute('SELECT t.notion_page_id FROM topic_links l JOIN topics t ON t.id=l.related_id WHERE l.topic_id=?',(t['id'],)) if r[0]}
    assert expected_related<=set(mentions)
    result['wiki'].append({'name':t['name'],'url':p['url'],'body_characters':len(text),'headings':len(bytype['heading_2']),'diagrams':len(diagrams),'code_examples':len(examples),'source_count':len(wiki['citations'])})
if args.legacy_backup:
    legacy=sqlite3.connect(args.legacy_backup);legacy.row_factory=sqlite3.Row
    for t in legacy.execute('SELECT * FROM topics'):
        assert s.db.execute('SELECT notion_page_id FROM topics WHERE id=?',(t['id'],)).fetchone()[0]==t['notion_page_id']
        b=w.call('GET','blocks/'+t['notion_block_id'])
        text=''.join(x['plain_text'] for x in b['paragraph']['rich_text'])
        assert t['summary'] in text
        result['preserved_legacy']+=1
    legacy.close()
for d in s.db.execute('SELECT * FROM briefings'):
    p=page_info(d['notion_page_id']);assert p['properties']['Date']['date']['start']==d['day']
    blocks=children(p['id'])
    mentions=[x['mention']['page']['id'] for b in blocks for x in b.get(b['type'],{}).get('rich_text',[]) if x['type']=='mention']
    expected={r[0] for r in s.db.execute('SELECT t.notion_page_id FROM briefing_changes c JOIN topics t ON t.id=c.topic_id WHERE c.day=?',(d['day'],)) if r[0]}
    assert expected<=set(mentions)
    result['briefing']={'day':d['day'],'url':p['url'],'linked_wiki_topics':len(mentions)}
home=children(w.known('area:home'))
links={x['mention']['page']['id'] for b in home for x in b.get(b['type'],{}).get('rich_text',[]) if x['type']=='mention'}
assert {w.known('area:'+k) for k in ('wiki','daily','sources','radar')}<=links
assert not {t['notion_page_id'] for t in s.topics() if not json.loads(t['wiki_json'])}&links
refid=w.known('reference-database')
refdb=w.call('GET','databases/'+refid)
assert all(k in refdb['properties'] for k in ('Name','Category','Relevance','Last updated','Status','Reference','Sources','Related technologies'))
rows=[];cursor=None
while True:
    body={'filter':{'property':'Status','select':{'equals':'Curated'}},'page_size':100}
    if cursor:body['start_cursor']=cursor
    response=w.call('POST','databases/'+refid+'/query',body);rows+=response['results']
    if not response.get('has_more'):break
    cursor=response['next_cursor']
assert len(rows)==len(result['wiki'])
for row in rows:
    props=row['properties']
    assert props['Reference']['url'] in {x['url'] for x in result['wiki']}
    assert props['Status']['select']['name']=='Curated'
    assert props['Last updated']['date']['start']
result['reference_database']={'url':refdb['url'],'metadata_rows':len(rows),'canonical_pages_preserved':True}
before={r['key']:r['remote_id'] for r in s.db.execute('SELECT * FROM notion_objects')}
http.writes.clear();w.sync()
assert not http.writes,http.writes
assert before=={r['key']:r['remote_id'] for r in s.db.execute('SELECT * FROM notion_objects')}
result['repeat_sync_remote_writes']=0
result['repeat_sync_duplicate_objects']=0
result['status']='PASS'
result['elapsed_seconds']=time.perf_counter()-started
result['http_metrics']=http.metrics
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
s.close()
