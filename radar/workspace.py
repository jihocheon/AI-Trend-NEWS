"""Additive Notion Wiki, daily change database, source index, radar, and navigation."""
import hashlib
import json
import time
from .http import IntegrationError
from .knowledge import SECTIONS,migrate

AREAS={'home':'Home Dashboard · AI 기술 지식', 'wiki':'Technology Wiki · 기술 레퍼런스',
       'daily':'Daily Briefing · 일일 변화', 'sources':'Research & Sources · 근거 자료',
       'radar':'Technology Radar · 관련성 평가'}


def rich(text):
    return [{'type':'text','text':{'content':text[i:i+1800]}} for i in range(0,len(text),1800)] or [{'type':'text','text':{'content':' '}}]

def block(kind,text,**extras):
    return {'object':'block','type':kind,kind:{'rich_text':rich(text),**extras}}


def linked(text,url):
    return {'type':'text','text':{'content':text[:1800],'link':{'url':url}}}


def mention(page_id):
    return {'type':'mention','mention':{'type':'page','page':{'id':page_id}}}


class Workspace:
    def __init__(self,store,notion):
        migrate(store);self.store=store;self.notion=notion;self.last=0

    def call(self,method,path,data=None):
        delay=.36-(time.monotonic()-self.last)
        if delay>0:time.sleep(delay)
        self.last=time.monotonic()
        return self.notion.call(method,path,data)

    def known(self,key):
        row=self.store.db.execute('SELECT remote_id FROM notion_objects WHERE key=?',(key,)).fetchone()
        return row[0] if row else None

    def remember(self,key,remote_id,body_hash=None):
        with self.store.db:
            self.store.db.execute('INSERT INTO notion_objects(key,remote_id,body_hash) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET remote_id=excluded.remote_id,body_hash=excluded.body_hash',
                                 (key,remote_id,body_hash))

    def page(self,key,title,parent):
        found=self.known(key)
        if found:return found
        response=self.call('POST','pages',{'parent':{'page_id':parent},
          'properties':{'title':{'title':rich(title)}}})
        self.remember(key,response['id']);return response['id']

    def blocks(self,parent,prefix,items):
        """Only update owned blocks. Keep all unknown/manual and older evidence blocks."""
        missing=[]
        for name,body in items:
            key=prefix+':'+name
            digest=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            old=self.store.db.execute('SELECT remote_id,body_hash FROM notion_objects WHERE key=?',(key,)).fetchone()
            if old and old['body_hash']!=digest:
                kind=body['type']
                self.call('PATCH','blocks/'+old['remote_id'],{kind:body[kind]})
                self.remember(key,old['remote_id'],digest)
            elif not old:missing.append((key,body,digest))
        for start in range(0,len(missing),50):
            chunk=missing[start:start+50]
            data=self.call('PATCH','blocks/'+parent+'/children',{'children':[x[1] for x in chunk]})
            result=data.get('results',[])
            if len(result)!=len(chunk):raise IntegrationError('Incomplete Notion block append; inspect remote state before retry')
            for (key,_,digest),remote in zip(chunk,result):self.remember(key,remote['id'],digest)

    def sync(self):
        store=self.store
        areas={k:self.page('area:'+k,v,self.notion.parent) for k,v in AREAS.items()}
        ready=[t for t in store.topics() if json.loads(t['wiki_json']) and not t['archived']]
        for t in ready:
            wiki=json.loads(t['wiki_json']); page_id=t['notion_page_id']
            if not page_id:
                page_id=self.page('topic:'+str(t['id']),t['name'],areas['wiki'])
                with store.db:store.db.execute('UPDATE topics SET notion_page_id=? WHERE id=?',(page_id,t['id']))
                t['notion_page_id']=page_id
            items=[('banner',block('callout','지속적으로 갱신하는 기술 참고 자료 · 일일 뉴스와 분리\n'+wiki.get('provenance','근거 자료를 확인하세요'))),
                   ('metadata',block('paragraph',f"분류: {t['category']} | 중요도: {t['score']:.2f} | 성숙도: {t['maturity']}\n검색 별칭: "+', '.join(json.loads(t['aliases_json']))))]
            for key,title in SECTIONS.items():
                if wiki.get(key):items.extend([(key+'-heading',block('heading_2',title)),(key,block('paragraph',wiki[key]))])
            if wiki.get('diagram'):
                items.extend([('diagram-heading',block('heading_2','아키텍처 · 설명용 흐름도 (직접 작성)')),
                              ('diagram',block('code',wiki['diagram'],language='mermaid'))])
            if wiki.get('code'):
                items.extend([('code-heading',block('heading_2','최소 구현 예제 · 교육용')),
                              ('code',block('code',wiki['code'],language='python'))])
            recent=store.db.execute('''SELECT s.title,s.url,s.published,h.reason FROM history h JOIN sources s ON s.id=h.source_id
              WHERE h.topic_id=? ORDER BY h.id DESC LIMIT 3''',(t['id'],)).fetchall()
            if recent:
                b=block('paragraph','최근 검토 근거 · 기술 해석은 검토가 필요한 모델 초안입니다.\n'+t['summary'])
                for src in recent:
                    b['paragraph']['rich_text']+=rich('\n발행/갱신일: '+(src['published'] or '미상')+' · ')
                    b['paragraph']['rich_text'].append(linked(src['title'],src['url']))
                items.extend([('recent-heading',block('heading_2','최근 검토 근거와 변화')),('recent-evidence',b)])
            citations=wiki.get('citations',[])
            for index,url in enumerate(citations):
                body=block('paragraph',' ');body['paragraph']['rich_text']=[linked('공식 근거 '+str(index+1),url)]
                items.append(('citation:'+url,body))
            relations=store.db.execute('SELECT t.notion_page_id,t.name FROM topic_links l JOIN topics t ON t.id=l.related_id WHERE l.topic_id=?',(t['id'],)).fetchall()
            links=[mention(r['notion_page_id']) for r in relations if r['notion_page_id']]
            if links:
                body=block('paragraph','관련 기술: ');body['paragraph']['rich_text']+=links;items.append(('related',body))
            body=block('paragraph',' ');body['paragraph']['rich_text']=[mention(areas['home']),mention(areas['wiki']),mention(areas['daily'])]
            items.append(('navigation',body))
            self.blocks(page_id,'wiki:'+str(t['id']),items)
            with store.db:store.db.execute('UPDATE topics SET wiki_pending=0 WHERE id=?',(t['id'],))
        # A second lightweight relation pass resolves pages created later in this same sync.
        for t in ready:
            relations=store.db.execute('SELECT t.notion_page_id FROM topic_links l JOIN topics t ON t.id=l.related_id WHERE l.topic_id=?',(t['id'],)).fetchall()
            links=[mention(r[0]) for r in relations if r[0]]
            if links:
                b=block('paragraph','관련 기술: ');b['paragraph']['rich_text']+=links
                self.blocks(t['notion_page_id'],'wiki:'+str(t['id']),[('related',b)])
        dbid=self.known('briefing-database')
        if not dbid:
            response=self.call('POST','databases',{'parent':{'type':'page_id','page_id':areas['daily']},
              'title':rich('한국어 일일 AI 브리핑'),
              'properties':{'Name':{'title':{}},'Date':{'date':{}},'Changes':{'number':{'format':'number'}}}})
            dbid=response['id'];self.remember('briefing-database',dbid)
        for day in store.db.execute('SELECT * FROM briefings ORDER BY day').fetchall():
            changes=store.db.execute('''SELECT c.*,t.notion_page_id,t.name FROM briefing_changes c
              JOIN topics t ON t.id=c.topic_id WHERE day=? ORDER BY t.score DESC,history_id''',(day['day'],)).fetchall()
            if not changes:continue
            page_id=day['notion_page_id']
            if not page_id:
                response=self.call('POST','pages',{'parent':{'database_id':dbid},'properties':{
                  'Name':{'title':rich(day['day']+' · AI 기술 변화')},'Date':{'date':{'start':day['day']}},'Changes':{'number':len(changes)}}})
                page_id=response['id']
                with store.db:store.db.execute('UPDATE briefings SET notion_page_id=? WHERE day=?',(page_id,day['day']))
            elif day['sync_pending']:
                self.call('PATCH','pages/'+page_id,{'properties':{'Changes':{'number':len(changes)}}})
            items=[('intro',block('paragraph','뉴스 요약과 기술 위키는 분리합니다. 아래는 한국 시간 기준 지식 갱신 내역이며, 사건 발생일과 다를 수 있습니다. 영구적인 설명은 연결된 기술 페이지에서 확인하세요.'))]
            for c in changes:
                b=block('paragraph',c['text_ko'])
                if c['notion_page_id']:b['paragraph']['rich_text'].append(mention(c['notion_page_id']))
                else:b['paragraph']['rich_text'].extend(rich(' · 위키 작성 전 검토 후보'))
                src=store.db.execute('SELECT s.url FROM history h JOIN sources s ON s.id=h.source_id WHERE h.id=?',(c['history_id'],)).fetchone()
                if src:b['paragraph']['rich_text'].append(linked('원문',src[0]))
                items.append(('change:'+str(c['history_id']),b))
            self.blocks(page_id,'briefing:'+day['day'],items)
            with store.db:store.db.execute('UPDATE briefings SET sync_pending=0 WHERE day=?',(day['day'],))
        refdb=self.known('reference-database')
        if not refdb:
            response=self.call('POST','databases',{'parent':{'type':'page_id','page_id':areas['wiki']},
              'title':rich('AI Technology Cheat Sheet · 선별 레퍼런스'),
              'properties':{'Name':{'title':{}},'Category':{'select':{}},'Relevance':{'number':{'format':'number'}},
                'Last updated':{'date':{}},'Status':{'select':{}},'Reference':{'url':{}},
                'Sources':{'number':{'format':'number'}},'Related technologies':{'rich_text':{}}}})
            refdb=response['id'];self.remember('reference-database',refdb)
        for t in ready:
            canonical=self.call('GET','pages/'+t['notion_page_id'])['url']
            related_ids=[r[0] for r in store.db.execute('SELECT t.notion_page_id FROM topic_links l JOIN topics t ON t.id=l.related_id WHERE l.topic_id=?',(t['id'],)) if r[0]]
            properties={'Name':{'title':rich(t['name'])},'Category':{'select':{'name':t['category']}},
              'Relevance':{'number':t['score']},'Last updated':{'date':{'start':t['updated_at']}},
              'Status':{'select':{'name':'Curated'}},'Reference':{'url':canonical},
              'Sources':{'number':len(json.loads(t['wiki_json']).get('citations',[]))},
              'Related technologies':{'rich_text':[mention(i) for i in related_ids]}}
            key='reference-row:'+str(t['id'])
            digest=hashlib.sha256(json.dumps(properties,sort_keys=True).encode()).hexdigest()
            old=store.db.execute('SELECT * FROM notion_objects WHERE key=?',(key,)).fetchone()
            if not old:
                row=self.call('POST','pages',{'parent':{'database_id':refdb},'properties':properties})
                self.remember(key,row['id'],digest);row_id=row['id']
            else:
                row_id=old['remote_id']
                if old['body_hash']!=digest:
                    self.call('PATCH','pages/'+row_id,{'properties':properties})
                    self.remember(key,row_id,digest)
            content=block('paragraph','이 항목은 검색·분류용 메타데이터입니다. 중복 본문을 만들지 않고 영구 기술 페이지로 연결합니다: ')
            content['paragraph']['rich_text'].append(mention(t['notion_page_id']))
            self.blocks(row_id,'reference-row:'+str(t['id']),[('canonical',content)])
        for t in store.topics():
            if not t['archived']:continue
            key='reference-row:'+str(t['id'])
            old=store.db.execute('SELECT * FROM notion_objects WHERE key=?',(key,)).fetchone()
            if old and old['body_hash']!='archived':
                self.call('PATCH','pages/'+old['remote_id'],{'properties':{'Status':{'select':{'name':'Archived'}}}})
                self.remember(key,old['remote_id'],'archived')
        wiki_items=[('intro',block('paragraph','유용하고 다시 찾아볼 가치가 있는 기술만 선별합니다. 고정된 분량이나 페이지 수 목표가 없습니다. Notion 검색과 아래 분류를 사용하거나 로컬 search 명령으로 기술·모델·용도를 검색하세요.'))]
        for t in ready:
            b=block('paragraph',t['category']+' · ');b['paragraph']['rich_text'].append(mention(t['notion_page_id']))
            wiki_items.append(('topic:'+str(t['id']),b))
        self.blocks(areas['wiki'],'index:wiki',wiki_items)
        home=[('intro',block('paragraph','AI 엔지니어링을 위한 선별형 지식 허브입니다. 최신성만으로 주제를 선택하지 않습니다. 기술 관련성·기초 중요도·실용성·새로움·근거 신뢰도·최신성의 판단 근거를 함께 보존합니다.'))]
        for k in ('wiki','daily','sources','radar'):
            b=block('paragraph',' ');b['paragraph']['rich_text']=[mention(areas[k])];home.append(('area:'+k,b))
        top=block('paragraph','우선 검토할 기술: ')
        top['paragraph']['rich_text'] += [mention(t['notion_page_id']) for t in ready if t['score']>=55][:8]
        home.append(('curated-top',top))
        self.blocks(areas['home'],'index:home',home)
        self.blocks(areas['daily'],'index:daily',[
          ('calendar',block('paragraph','Date 속성을 기준으로 일별 탐색합니다. Notion API는 캘린더 뷰 생성을 지원하지 않아, 아래 데이터베이스에서 + 뷰 추가 → 캘린더 → Date를 한 번 설정하세요. 별도 유료 기능은 필요하지 않습니다.'))])
        source_items=[]
        for src in store.db.execute('SELECT * FROM sources ORDER BY id'):
            b=block('paragraph',f"[{src['kind']}] {src['title']}\n발행/갱신일: {src['published'] or '미상'}\n")
            if src['url'].startswith(('https://','http://')):b['paragraph']['rich_text'].append(linked('원문',src['url']))
            linked_topics=store.db.execute('SELECT t.notion_page_id FROM topics t JOIN relationships r ON r.topic_id=t.id WHERE r.source_id=?',(src['id'],)).fetchall()
            b['paragraph']['rich_text'] += [mention(r[0]) for r in linked_topics if r[0]]
            source_items.append(('source:'+str(src['id']),b))
        self.blocks(areas['sources'],'index:sources',source_items)
        radar=[]
        for t in store.topics():
            factors=json.loads(t['rank_reason'])
            labels={'technical_relevance':'기술 관련성','foundational_importance':'기초 중요도',
                    'practical_utility':'실용성','novelty':'새로움','credibility':'근거 신뢰도','freshness':'최신성'}
            detail=' · '.join(f"{label} {100*factors.get(key,0):.0f}%" for key,label in labels.items())
            line=f"{t['name']} | 점수 {t['score']:.2f} | 성숙도 {t['maturity']} | 상태 {'보관' if t['archived'] else '활성'}\n"+detail
            radar.append(('topic:'+str(t['id']),block('paragraph',line)))
        self.blocks(areas['radar'],'index:radar',radar)
        # Add a navigation entry to the configured parent, leaving all existing content untouched.
        b=block('paragraph','기술 지식 홈: ');b['paragraph']['rich_text'].append(mention(areas['home']))
        self.blocks(self.notion.parent,'root',[('home',b)])
        return {'areas':areas,'wiki_topics':len(ready),'briefing_database':dbid,'reference_database':refdb}
