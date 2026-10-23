"""Fail-closed, zero-cost generation gate. No fallback or tier upgrades."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from .http import IntegrationError

PRICING_URL = 'https://ai.google.dev/gemini-api/docs/pricing'


class Rows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row=[]
        if tag in ('td','th'): self.cell=[]
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None: self.row.append(' '.join(''.join(self.cell).split()))
            self.cell=None
        if tag == 'tr' and self.row is not None:
            self.rows.append(self.row); self.row=None


def verify_pricing(html, model):
    match=re.search(r'<h(?P<level>[23])\b[^>]*\bid=["\']'+re.escape(model)+r'["\'][^>]*>', html, re.I)
    if not match:
        raise IntegrationError('Cannot verify this exact model on the official pricing page; generation disabled')
    boundary=r'<h2\b' if match.group('level')=='2' else r'<h[23]\b'
    section=re.split(boundary,html[match.end():],maxsplit=1,flags=re.I)[0]
    table=re.search(r'<table\b.*?</table>',section,re.I|re.S)
    if table is None:raise IntegrationError('No standard pricing table; generation disabled')
    headings=re.findall(r'<h[34]\b[^>]*>(.*?)</h[34]>',section[:table.start()],re.I|re.S)
    if headings and re.sub('<[^>]+>','',headings[-1]).strip().lower()!='standard':
        raise IntegrationError('Cannot establish standard free-tier pricing; generation disabled')
    parser=Rows(); parser.feed(table.group())
    # Require an explicit free-tier column and free input AND output in that column.
    header=next((r for r in parser.rows if any('free tier' in c.lower() for c in r)),None)
    if not header:
        raise IntegrationError('No explicit free-tier pricing column; generation disabled')
    free_index=next(i for i,c in enumerate(header) if 'free tier' in c.lower())
    for label in ('input','output'):
        row=next((r for r in parser.rows if r and label in r[0].lower() and 'price' in r[0].lower()),None)
        if not row or free_index >= len(row) or row[free_index].lower() != 'free of charge':
            raise IntegrationError('Model input/output is not explicitly free; generation disabled')
    return {'model':model,'url':PRICING_URL,'sha256':hashlib.sha256(html.encode()).hexdigest(),
            'verified_at':datetime.now(timezone.utc).isoformat()}


class FreeTierBudget:
    def __init__(self, http, model, billing_disabled, db, *, requests=2, input_tokens=6000,
                 output_tokens=3000, total_tokens=12000):
        if billing_disabled != 'true':
            raise IntegrationError('Confirm billing is disabled with GEMINI_BILLING_DISABLED=true; generation disabled')
        if not (1 <= requests <= 3 and 1 <= input_tokens <= 12000 and 1 <= output_tokens <= 4000
                and 1 <= total_tokens <= 20000):
            raise ValueError('Free-tier budgets exceed conservative safety bounds')
        self.proof=verify_pricing(http.request('GET',PRICING_URL).decode(),model)
        self.model=model; self.db=db; self.max_requests=requests; self.max_input=input_tokens
        self.max_output=output_tokens; self.max_total=total_tokens
        self.requests=0; self.reserved=0; self.stopped=False
        db.execute('''CREATE TABLE IF NOT EXISTS generation_usage (
          id INTEGER PRIMARY KEY, model TEXT, status TEXT, reserved_tokens INTEGER,
          input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
          pricing_proof TEXT, created_at TEXT)''')
        db.commit()

    def reserve(self, contents, output_tokens):
        # UTF-8 byte length plus overhead deliberately overestimates token counts.
        upper_input=len(json.dumps(contents,ensure_ascii=False).encode())+256
        cost=upper_input+output_tokens
        if self.stopped or self.requests >= self.max_requests or upper_input > self.max_input or \
           output_tokens > self.max_output or self.reserved+cost > self.max_total:
            raise IntegrationError('Conservative free-tier request/token budget exhausted; stopped without fallback')
        self.requests+=1; self.reserved+=cost
        with self.db:
            return self.db.execute('''INSERT INTO generation_usage
              (model,status,reserved_tokens,pricing_proof,created_at) VALUES (?,'reserved',?,?,?)''',
              (self.model,cost,json.dumps(self.proof),datetime.now(timezone.utc).isoformat())).lastrowid

    def finish(self, request_id, response=None, error=None):
        usage=(response or {}).get('usageMetadata',{})
        if error: self.stopped=True  # No retries, model switching, or quota bypass.
        with self.db:
            self.db.execute('''UPDATE generation_usage SET status=?,input_tokens=?,output_tokens=?,total_tokens=?
              WHERE id=?''', ('failed' if error else 'completed',usage.get('promptTokenCount'),
              usage.get('candidatesTokenCount'),usage.get('totalTokenCount'),request_id))
