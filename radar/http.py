"""Small verified-TLS HTTP client. Never log headers, URLs, or remote error bodies."""
import json
import time
import urllib.error
import urllib.request


class IntegrationError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward credentials to redirected destinations.


class HTTP:
    def request(self, method, url, *, headers=None, data=None):
        if not url.startswith("https://"):
            raise IntegrationError("External requests require HTTPS")
        body = json.dumps(data).encode() if data is not None else None
        request_headers = {"User-Agent": "AI-Technology-Radar/0.1", **(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, body, request_headers, method=method)
                with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
                    raw = response.read(4_000_001)
                    if len(raw) > 4_000_000:
                        raise IntegrationError("External response exceeded 4 MB limit")
                    return raw
            except urllib.error.HTTPError as exc:
                # Retry reads only: retrying writes can create duplicate pages.
                if method == "GET" and exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise IntegrationError(f"External HTTP request failed (status {exc.code})") from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
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
