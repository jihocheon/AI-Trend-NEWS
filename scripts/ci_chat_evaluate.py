"""Offline chat retrieval evaluation and gates using the existing CI source corpus."""
import json
import os
import tempfile
from pathlib import Path
from ci_evaluate import FixtureSources
from radar.bootstrap import bootstrap
from radar.chat_evaluate import evaluate_questions
from radar.store import Store


def main():
    if os.getenv('RADAR_CI_NETWORK_BLOCKED')!='1':raise SystemExit('CI network guard required')
    cases=json.loads(Path(__file__).resolve().parents[1].joinpath('tests/fixtures/chat_questions.json').read_text())
    with tempfile.TemporaryDirectory(prefix='radar-chat-eval-') as folder:
        s=Store(str(Path(folder)/'chat.sqlite3'))
        try:
            bootstrap(s,FixtureSources());result=evaluate_questions(s,cases)
            assert result['positive_queries']==8 and result['gap_or_safety_queries']==4
            assert result['chat_mean_topic_recall_at_3']==1.0,result
            assert result['chat_mean_topic_recall_at_3']>=result['baseline_mean_topic_recall_at_3'],result
            assert result['gap_or_safety_no_evidence_rate']==1.0,result
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:s.close()


if __name__=='__main__':main()
