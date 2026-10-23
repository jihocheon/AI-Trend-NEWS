"""Bounded text/date normalization; preserve the original separately."""
from dataclasses import replace
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse


class Text(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        elif tag in ('p','br','div','li','h1','h2'):self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:self.skip-=1
        elif tag in ('p','div','li'):self.parts.append(' ')
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)


def normalize(source):
    parsed=urlparse(source.url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid source URL')
    # Only parse text that resembles HTML; keep technical operators in plain text.
    text=source.text
    if any(t in text.lower() for t in ('<p','<div','<a ','<script','<br')):
        parser=Text();parser.feed(text);text=''.join(parser.parts)
    published=''
    if source.published:
        try:
            try:stamp=datetime.fromisoformat(source.published.replace('Z','+00:00'))
            except ValueError:stamp=parsedate_to_datetime(source.published)
            # Unknown timezone stays unknown rather than inventing UTC.
            if stamp.tzinfo:published=stamp.astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError,OverflowError):pass
    return replace(source,title=' '.join(source.title.split()),text=' '.join(text.split())[:20000],published=published)
