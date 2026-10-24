"""Conversation-aware expansion around the shared FTS5 retriever; no network calls."""
import json
import re
from dataclasses import asdict, dataclass
from .retrieval import retrieve

SYNONYMS = {
    'rag': ('rag', '검색 증강', '검색증강', '근거를 찾아', '문서를 찾아', '문서 검색', '문서검색', '자료를 찾아', 'retrieval augmented', '사내 문서', 'retrieval', '색인', '검색 정확도', 'rerank', '벡터 검색'),
    'agent-harness': ('mcp', '하네스', 'harness', '오케스트레이션', 'orchestration', '도구 호출', '도구호출', '에이전트', 'agent'),
    'llm-architecture': ('llm', '트랜스포머', 'transformer', 'attention', '어텐션', 'kv cache', '다음 토큰', '다음 단어', '언어 모델', '언어모델'),
}
FOLLOWUP = re.compile(r'그럼|그러면|그것|그거|둘|앞서|위에서|더 자세|이 경우|그 방식|\b(it|that|those|them|follow.up|what about)\b', re.I)
OUTSIDE = re.compile(r'날씨|야구|축구|주가|운세|조리법|\b(weather|baseball|horoscope|recipe)\b', re.I)
GENERIC = {'모델', '비교', '설명', '기술', '알려줘', '설명해줘', '어떻게', 'model', 'compare', 'explain'}


@dataclass(frozen=True)
class Evidence:
    id: str
    text: str
    title: str
    topic_id: int | None
    source_id: int | None = None
    source_url: str | None = None
    notion_url: str | None = None
    published: str = ''
    kind: str = 'reference'

    def prompt(self):
        # The model returns identifiers, never invents or chooses browser URLs.
        return {'id': self.id, 'title': self.title, 'text': self.text, 'kind': self.kind,
                'published': self.published or 'unknown','topic_id':self.topic_id}


def clip_bytes(text, limit):
    return text.encode()[:limit].decode('utf-8', errors='ignore')


def understand(question, topics, prior_focus=()):
    lower=question.lower()
    if OUTSIDE.search(lower):
        return {'query':question,'focus':[],'intent':'outside','followup':False}
    focus=[]
    for key, words in SYNONYMS.items():
        if any(word in lower for word in words):focus.append(key)
    # Reuse current knowledge aliases for future technologies, rather than an exclusive catalog.
    for topic in topics:
        key=topic.get('canonical_key') or str(topic['id'])
        aliases=[topic['name'],*json.loads(topic.get('aliases_json','[]'))]
        if any(len(a)>=3 and a.lower() in lower for a in aliases) and key not in focus:focus.append(key)
    followup=bool(prior_focus and (FOLLOWUP.search(question) or (not focus and len(question)<100 and re.search(r'장점|단점|한계|비용|예제|trade.off|implementation|limitation|latency',lower))))
    if followup:
        focus=list(dict.fromkeys([*focus,*prior_focus]))[:3]
    intent='comparison' if re.search(r'비교|차이|대비|trade.off|versus|\bvs\b|compare',lower) else 'explanation'
    if re.search(r'실무|구현|연결|권한|지연|적용|설계|latency|implement|practical',lower):intent='application'
    if not focus and set(re.findall(r'[a-z가-힣]+',lower)) <= GENERIC:
        intent='ambiguous'
    if re.search(r'상충|충돌|서로 다르|conflict|contradict',lower):intent='conflict'
    return {'query':' '.join([question,*focus])[:900],'focus':focus,'intent':intent,'followup':followup}


def retrieve_chat(store,question,prior_focus=(),context_bytes=2600):
    topics=store.topics()
    has_links=store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chat_page_links'").fetchone()
    links={r['topic_id']:r['url'] for r in store.db.execute('SELECT topic_id,url FROM chat_page_links')} if has_links else {}
    plan=understand(question,topics,prior_focus)
    if plan['intent'] in ('outside','ambiguous'):
        return {'plan':plan,'evidence':[],'topics':[],'trace':{'query_count':0,'method':'shared FTS5 + deterministic conversational expansion'}}
    results=[retrieve(store,plan['query'],k=3)]
    if not plan['focus']:
        return {'plan':{**plan,'intent':'insufficient'},'evidence':[],'topics':[],
                'trace':{'query_count':1,'method':'shared FTS5 + conservative topic anchor check'}}
    by_key={(t.get('canonical_key') or str(t['id'])):t for t in topics}
    for focus in plan['focus']:
        if focus in by_key:results.append(retrieve(store,by_key[focus]['name'],k=2))
    selected=[]
    for key in plan['focus']:
        if key in by_key:selected.append(by_key[key])
    for result in results:
        for t in result['topics']:
            if t['id'] not in {s['id'] for s in selected}:selected.append(t)
    # Focused turns keep unrelated broad OR matches out of the context.
    if plan['focus']:selected=selected[:max(1,min(3,len(plan['focus'])))]
    else:selected=selected[:2]
    evidence=[]
    remaining=context_bytes
    sections={'comparison':('comparisons','concept'), 'application':('limitations','implementation','architecture'),
              'explanation':('concept','architecture')}.get(plan['intent'],('concept','architecture'))
    per_topic=min(850,max(400,context_bytes//max(1,len(selected)+1)))
    for t in selected:
        wiki=json.loads(t.get('wiki_json','{}'))
        parts=[clip_bytes(wiki[key],per_topic//2) for key in sections if wiki.get(key)][:2]
        if not parts and t['summary']:parts=[clip_bytes(t['summary'],per_topic)]
        text='\n'.join(parts)
        if re.search(r'지연|latency|권한|permission',question,re.I):
            probes=[]
            if re.search(r'지연|latency',question,re.I):probes+=['latency','지연','timeout']
            if re.search(r'권한|permission',question,re.I):probes+=['권한','접근','permission']
            sentences=[s.strip() for value in wiki.values() if isinstance(value,str) for s in re.split(r'(?<=[.!?])\s+',value)]
            targeted=[]
            for probe in probes:
                match=next((s for s in sentences if probe.lower() in s.lower() and len(s)>=20),None)
                if match and match not in targeted:targeted.append(match)
            if targeted:text='\n'.join(targeted)+ '\n'+text
        if not text:continue
        row=(links[t['id']],) if t['id'] in links else None
        text=clip_bytes(text,min(per_topic,remaining));remaining-=len(text.encode())
        evidence.append(Evidence('K'+str(len(evidence)+1),text,t['name'],t['id'],notion_url=row[0] if row else None))
    # One actual stored source excerpt per topic maintains source diversity in comparisons.
    spans=[s for r in results for s in r['evidence']]
    for t in selected:
        source_ids={r[0] for r in store.db.execute('SELECT source_id FROM relationships WHERE topic_id=?',(t['id'],))}
        candidates=[s for s in spans if s['source_id'] in source_ids]
        if not candidates:
            rows=store.db.execute('''SELECT c.id AS chunk_id,c.source_id,c.position,c.text,s.url,s.title
              FROM chunks c JOIN sources s ON s.id=c.source_id WHERE c.source_id IN
              (SELECT source_id FROM relationships WHERE topic_id=?) ORDER BY c.position,c.id LIMIT 1''',(t['id'],)).fetchall()
            candidates=[dict(r) for r in rows]
        if not candidates or remaining<80:continue
        s=candidates[0]
        if any(e.source_id==s['source_id'] for e in evidence):continue
        text=clip_bytes(s['text'],min(330,remaining));remaining-=len(text.encode())
        source=store.db.execute('SELECT kind,published FROM sources WHERE id=?',(s['source_id'],)).fetchone()
        url=(links[t['id']],) if t['id'] in links else None
        evidence.append(Evidence('K'+str(len(evidence)+1),text,s['title'],t['id'],s['source_id'],s['url'],url[0] if url else None,source['published'],source['kind']))
    plan['focus']=[t.get('canonical_key') or str(t['id']) for t in selected]
    selected_ids={t['id'] for t in selected}
    relations=[dict(r) for r in store.db.execute('SELECT topic_id,related_id,relation FROM topic_links') if r['topic_id'] in selected_ids and r['related_id'] in selected_ids]
    return {'plan':plan,'evidence':evidence,'topics':selected,'relations':relations,
            'trace':{'query_count':len(results),'followup':plan['followup'],
                     'topic_ids':[t['id'] for t in selected],
                     'source_ids':[e.source_id for e in evidence if e.source_id],
                     'context_bytes':sum(len(e.text.encode()) for e in evidence),
                     'method':'shared FTS5 + deterministic conversational expansion'}}
