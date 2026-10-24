"""Small verified-TLS HTTP client. Never log headers, URLs, or remote error bodies."""
import json
import logging
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


class IntegrationError(RuntimeError):
    def __init__(self,message,*,status_code=None):
        self.status_code=status_code
        super().__init__(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward credentials to redirected destinations.


class HTTP:
    def __init__(self,timeout=30,max_get_attempts=3):
        if not 0<timeout<=30 or not 1<=max_get_attempts<=3:raise ValueError('Invalid HTTP limits')
        self.timeout=timeout;self.max_get_attempts=max_get_attempts

    def request(self, method, url, *, headers=None, data=None):
        if not url.startswith("https://"):
            raise IntegrationError("External requests require HTTPS")
        body = json.dumps(data).encode() if data is not None else None
        request_headers = {"User-Agent": "AI-Technology-Radar/0.1", **(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        for attempt in range(getattr(self,'max_get_attempts',3) if method=='GET' else 1):
            if not hasattr(self,'metrics'):
                self.metrics={'requests':0,'errors':0,'notion_write_attempts':0,'gemini_generation_attempts':0,'latency_ms':0.0}
            self.metrics['requests']+=1
            service=urlparse(url).hostname
            if service=='api.notion.com' and method!='GET' and not url.endswith('/query'):
                self.metrics['notion_write_attempts']+=1
            if service=='generativelanguage.googleapis.com' and method=='POST':
                self.metrics['gemini_generation_attempts']+=1
            started=time.perf_counter()
            try:
                req = urllib.request.Request(url, body, request_headers, method=method)
                with urllib.request.build_opener(NoRedirect()).open(req, timeout=getattr(self,'timeout',30)) as response:
                    raw = response.read(4_000_001)
                    if len(raw) > 4_000_000:
                        raise IntegrationError("External response exceeded 4 MB limit")
                    elapsed=(time.perf_counter()-started)*1000
                    self.metrics['latency_ms']+=elapsed
                    logging.getLogger('radar').info(json.dumps({'event':'http','service':service,'method':method,'status':response.status,'latency_ms':round(elapsed,2),'attempt':attempt+1}))
                    return raw
            except urllib.error.HTTPError as exc:
                self.metrics['errors']+=1
                logging.getLogger('radar').warning(json.dumps({'event':'http_error','service':service,'method':method,'status':exc.code,'attempt':attempt+1}))
                # Retry reads only: retrying writes can create duplicate pages.
                if method == "GET" and exc.code in (429, 500, 502, 503, 504) and attempt < getattr(self,'max_get_attempts',3)-1:
                    time.sleep(2 ** attempt)
                    continue
                raise IntegrationError(f"External HTTP request failed (status {exc.code})",status_code=exc.code) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self.metrics['errors']+=1
                if "Tunnel connection failed: 403" in str(getattr(exc, "reason", "")):
                    raise IntegrationError("Network proxy denied destination (403); check the environment allowlist") from None
                raise IntegrationError("External request failed: network or TLS error") from None
        raise IntegrationError("External request retry limit reached")

    def json(self, method, url, **kwargs):
        raw = self.request(method, url, **kwargs)
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise IntegrationError("External service returned invalid JSON") from None
