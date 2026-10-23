import json
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from .models import Source


SAMPLE = Path(__file__).with_name("sample.json")


def sample():
    return [Source(**item) for item in json.loads(SAMPLE.read_text())]


def rss(http, url, limit=10):
    root = ET.fromstring(http.request("GET", url))
    items = root.findall(".//item")
    atom = {"a": "http://www.w3.org/2005/Atom"}
    if items:
        return [Source(i.findtext("guid") or i.findtext("link") or i.findtext("title", ""),
                       "rss", i.findtext("title", ""), i.findtext("link", ""),
                       i.findtext("description", ""), i.findtext("pubDate", ""))
                for i in items[:limit]]
    result = []
    for i in root.findall("a:entry", atom)[:limit]:
        links = i.findall("a:link", atom)
        link = next((x.get("href", "") for x in links if x.get("rel", "alternate") == "alternate"), "")
        result.append(Source(i.findtext("a:id", link, atom), "rss", i.findtext("a:title", "", atom),
                             link, i.findtext("a:summary", "", atom), i.findtext("a:updated", "", atom)))
    return result


def arxiv(http, query="cat:cs.AI", limit=10):
    params = urllib.parse.urlencode({"search_query": query, "start": 0, "max_results": limit,
                                    "sortBy": "submittedDate", "sortOrder": "descending"})
    root = ET.fromstring(http.request("GET", "https://export.arxiv.org/api/query?" + params))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    return [Source(i.findtext("a:id", "", ns), "arxiv", " ".join(i.findtext("a:title", "", ns).split()),
                   i.findtext("a:id", "", ns), " ".join(i.findtext("a:summary", "", ns).split()),
                   i.findtext("a:published", "", ns)) for i in root.findall("a:entry", ns)[:limit]]


def github(http, query="topic:artificial-intelligence", limit=10, token=None):
    params = urllib.parse.urlencode({"q": query, "sort": "updated", "per_page": limit})
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = http.json("GET", "https://api.github.com/search/repositories?" + params, headers=headers)
    return [Source(str(i["id"]), "github", i["full_name"], i["html_url"],
                   i.get("description") or "", i["updated_at"]) for i in data["items"][:limit]]
