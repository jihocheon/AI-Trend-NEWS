"""Explicit scripted answers and source fixtures; never live inference evidence."""
import json
from pathlib import Path
from radar.bootstrap import bootstrap
from radar.store import Store


class FixtureSources:
    def request(self,method,url):
        data=json.loads(Path('tests/fixtures/ci_sources.json').read_text())['responses']
        assert method=='GET' and url in data
        return data[url].encode()


def knowledge(path):
    s=Store(str(path));bootstrap(s,FixtureSources());return s


class ScriptedGenerator:
    def __init__(self):self.calls=[]
    def generate(self,body):
        self.calls.append(body)
        data=json.loads(body['contents'][0]['parts'][0]['text']);items=data['evidence']
        selected=items[:min(2,len(items))]
        segments=[{'kind':'grounded','text':'검색과 도구 연결은 서로 다른 책임으로 나누어 이해하는 것이 좋습니다. 각 기술의 역할을 근거에 맞추어 구분할 수 있습니다.',
          'evidence_ids':[s['id']],'quotes':[{'evidence_id':s['id'],'quote':s['text'][:40]}]} for s in selected]
        raw={'segments':segments}
        return {'candidates':[{'content':{'parts':[{'text':json.dumps(raw,ensure_ascii=False)}]}}],
                'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':20,'totalTokenCount':30}}
