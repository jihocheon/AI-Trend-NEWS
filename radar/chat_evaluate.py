"""Small bilingual labelled retrieval comparison; no inference or live-service claims."""
import json
import time
from .chat import SECRET_REQUEST
from .chat_retrieval import retrieve_chat
from .retrieval import retrieve


def evaluate_questions(store,cases):
    rows=[];old=[];new=[];safety=[];elapsed=[]
    for case in cases:
        start=time.perf_counter()
        baseline=retrieve(store,case['question'],k=3)
        base_keys={t.get('canonical_key') for t in baseline['topics']}
        if SECRET_REQUEST.search(case['question']):
            found={'topics':[],'plan':{'intent':'refused'}}
        else:found=retrieve_chat(store,case['question'],case.get('prior_focus',()))
        keys={t.get('canonical_key') for t in found['topics']}
        elapsed.append((time.perf_counter()-start)*1000)
        expected=set(case['topics'])
        row={'id':case['id'],'baseline_topics':sorted(k for k in base_keys if k),
             'chat_topics':sorted(k for k in keys if k),'expected_topics':sorted(expected)}
        if expected:
            old.append(len(expected&base_keys)/len(expected));new.append(len(expected&keys)/len(expected))
            row.update(baseline_recall_at_3=old[-1],chat_recall_at_3=new[-1])
        else:
            good=not keys;safety.append(good);row['no_unrelated_evidence']=good
        rows.append(row)
    return {'cases':rows,'positive_queries':len(new),'gap_or_safety_queries':len(safety),
      'baseline_mean_topic_recall_at_3':sum(old)/max(1,len(old)),
      'chat_mean_topic_recall_at_3':sum(new)/max(1,len(new)),
      'gap_or_safety_no_evidence_rate':sum(safety)/max(1,len(safety)),
      'mean_comparison_latency_ms':sum(elapsed)/max(1,len(elapsed)),
      'note':'Small manually labelled in-repository regression; deterministic expansion, not semantic embeddings or answer-quality evidence. Latency includes both retrieval paths.'}
