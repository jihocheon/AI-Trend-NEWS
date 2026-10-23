"""Explicit opt-in publication to a Notion parent page (no database required)."""
import re
from .http import IntegrationError


class Notion:
    def __init__(self, http, token, parent):
        if not token or not parent:
            raise ValueError("NOTION_TOKEN and NOTION_PARENT_PAGE_ID are required")
        if not re.fullmatch(r"[a-fA-F0-9-]{32,36}", parent):
            raise ValueError("NOTION_PARENT_PAGE_ID must be a page UUID")
        self.http, self.parent = http, parent
        self.headers = {"Authorization": "Bearer " + token, "Notion-Version": "2022-06-28"}

    def call(self, method, path, data):
        return self.http.json(method, "https://api.notion.com/v1/" + path, headers=self.headers, data=data)

    @staticmethod
    def content(topic, evidence):
        text = topic["category"] + "\n\n" + topic["summary"] + "\n\nEvidence:\n"
        text += "\n".join(f"{s['title']}: {s['url']}" for s in evidence)
        # Notion permits at most 2000 characters per text fragment.
        text = text[:12000]
        return [{"type": "text", "text": {"content": text[i:i + 2000]}} for i in range(0, len(text), 2000)]

    def sync(self, store):
        synced = 0
        for t in store.topics():
            if not t["sync_pending"]:
                continue
            evidence = store.db.execute('''SELECT s.title,s.url FROM sources s JOIN relationships r
              ON r.source_id=s.id WHERE r.topic_id=? ORDER BY s.id''', (t["id"],)).fetchall()
            paragraph = {"rich_text": self.content(t, evidence)}
            page_id, block_id = t["notion_page_id"], t["notion_block_id"]
            if not page_id:
                if t["archived"]:
                    continue  # No need to publish an already archived local-only topic.
                page = self.call("POST", "pages", {"parent": {"page_id": self.parent},
                    "properties": {"title": {"type": "title", "title": [
                        {"type": "text", "text": {"content": t["name"][:2000]}}]}}})
                page_id = page.get("id")
                if not page_id:
                    raise IntegrationError("Notion create response missing page ID")
                # Persist remote identity before subsequent writes to allow recovery.
                with store.db:
                    store.db.execute("UPDATE topics SET notion_page_id=? WHERE id=?", (page_id, t["id"]))
            self.call("PATCH", "pages/" + page_id, {"archived": bool(t["archived"])})
            if not t["archived"]:
                if block_id:
                    self.call("PATCH", "blocks/" + block_id, {"paragraph": paragraph})
                else:
                    result = self.call("PATCH", "blocks/" + page_id + "/children", {
                        "children": [{"object": "block", "type": "paragraph", "paragraph": paragraph}]})
                    try:
                        block_id = result["results"][0]["id"]
                    except (KeyError, IndexError, TypeError):
                        raise IntegrationError("Notion append response missing block ID") from None
            with store.db:
                store.db.execute("UPDATE topics SET notion_block_id=?,sync_pending=0 WHERE id=?", (block_id, t["id"]))
            synced += 1
        return synced
