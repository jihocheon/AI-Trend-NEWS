"""Evidence-bounded adaptive Wiki enrichment; same guarded Gemini budget."""
import json
from .knowledge import publish_revision
from .http import IntegrationError


def enrich(store,reasoner,topic_id):
    topic=next((t for t in store.topics() if t['id']==topic_id),None)
    if topic is None:raise ValueError('Unknown topic identity')
    evidence=[dict(r) for r in store.db.execute('''SELECT s.id,s.url,s.title,s.text FROM sources s
      JOIN relationships r ON s.id=r.source_id WHERE r.topic_id=? ORDER BY s.id DESC LIMIT 3''',(topic_id,))]
    if not evidence:raise ValueError('Persisted source evidence required')
    prompt={'task':'한국어 선별형 기술 참고 노트를 작성하세요. 백과사전 분량을 채우지 말고 무엇인지/왜 중요한지/동작/용도/한계를 명확히 설명하세요. '
      '각 핵심 설명은 최소 40자. 원문에 없는 수치·실험 결과를 만들지 말고 일반 설계 설명과 불확실성을 구분하세요. '
      '이전 개념 설명을 유지하며 새 근거로 필요한 부분만 보강하세요. 코드와 도표는 유용할 때만 포함하고 코드는 실행 검증 전임을 표시하세요.',
      'topic':topic['name'],'prior':{k:v[:250] for k,v in json.loads(topic['wiki_json']).items() if isinstance(v,str)},
      'sources':[{**e,'text':e['text'][:600]} for e in evidence]}
    props={k:{'type':'STRING'} for k in ('concept','architecture','use_cases','limitations','comparisons','code','diagram')}
    response=reasoner.generate({'contents':[{'parts':[{'text':json.dumps(prompt,ensure_ascii=False)}]}],
      'generationConfig':{'temperature':0,'maxOutputTokens':3000,'responseMimeType':'application/json',
      'responseSchema':{'type':'OBJECT','properties':props,'required':['concept','architecture','use_cases','limitations']}}})
    try:
        wiki=json.loads(response['candidates'][0]['content']['parts'][0]['text'])
        if not isinstance(wiki,dict) or any(not isinstance(v,str) for v in wiki.values()):raise ValueError()
        wiki.update(depth='concise',citations=[s['url'] for s in evidence],provenance='Gemini · 공식/수집 근거 기반 초안 · 코드 미실행')
        publish_revision(store,topic_id,wiki,[s['id'] for s in evidence],provenance='Gemini evidence-bounded enrichment')
    except (KeyError,IndexError,TypeError,ValueError):
        raise IntegrationError('Invalid Wiki draft; existing reference preserved') from None
    return topic_id
