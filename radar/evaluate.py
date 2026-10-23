"""Reproducible, manually labelled small retrieval regression evaluation."""
import argparse
import json
import time
from .store import Store
from .retrieval import retrieve

QUERIES=[('RAG','rag'),('트랜스포머','llm-architecture'),('MCP','agent-harness'),
         ('KV cache','llm-architecture'),('reranking','rag'),('도구 호출','agent-harness')]
DOCS=[('similarity search clustering vectors','https://raw.githubusercontent.com/facebookresearch/faiss/main/README.md'),
      ('Model Context Protocol','https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/README.md'),
      ('causal language model','https://raw.githubusercontent.com/huggingface/transformers/main/docs/source/en/llm_tutorial.md')]


def evaluate(store):
    if sum(bool(t.get('canonical_key')) for t in store.topics())<3:raise ValueError('Run bootstrap first')
    rows=[];rr=[];durations=[]
    for query,expected in QUERIES:
        start=time.perf_counter();result=retrieve(store,query,k=3);durations.append((time.perf_counter()-start)*1000)
        keys=[t['canonical_key'] for t in result['topics']]
        rank=keys.index(expected)+1 if expected in keys else None
        rr.append(1/rank if rank else 0)
        rows.append({'query':query,'expected':expected,'actual':keys,'hit_at_1':bool(keys and keys[0]==expected),'reciprocal_rank':rr[-1]})
    docrows=[]
    for query,url in DOCS:
        result=retrieve(store,query,k=3)
        actual=[s['url'] for s in result['evidence']]
        docrows.append({'query':query,'expected_url':url,'actual_urls':actual,
                        'precision_at_1':int(bool(actual and actual[0]==url))})
    unrelated=retrieve(store,'volcano weather baseball',k=3)
    return {'topic_queries':rows,'topic_hit_at_1':sum(r['hit_at_1'] for r in rows)/len(rows),
      'topic_mrr_at_3':sum(rr)/len(rr),'document_queries':docrows,
      'document_precision_at_1':sum(r['precision_at_1'] for r in docrows)/len(docrows),
      'unrelated_topic_results':len(unrelated['topics']),'mean_topic_latency_ms':sum(durations)/len(durations),
      'dataset_note':'6 labelled topic queries + 3 document queries + 1 irrelevant query; small in-repository regression, not an independent production benchmark'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',default='var/live-integration.sqlite3');args=p.parse_args()
    s=Store(args.db)
    try:print(json.dumps(evaluate(s),ensure_ascii=False,indent=2))
    finally:s.close()

if __name__=='__main__':main()
