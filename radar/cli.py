import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
import time
import xml.etree.ElementTree as ET
from . import collectors
from .http import HTTP, IntegrationError
from .intelligence import GeminiReasoner, SampleReasoner
from .notion import Notion
from .pipeline import run
from .store import Store


def parser():
    p = argparse.ArgumentParser(description="Local-first AI Technology Radar")
    p.add_argument("--db", default="var/radar.sqlite3")
    p.add_argument("--log", default="var/radar.log")
    commands = p.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("run", help="Collect, classify, rank, and archive")
    collect.add_argument("--mode", choices=["sample", "live"], default="sample")
    collect.add_argument("--rss", action="append", default=[])
    collect.add_argument("--arxiv-query", default="cat:cs.AI")
    collect.add_argument("--github-query", default="topic:artificial-intelligence")
    collect.add_argument("--limit", type=int, default=5)
    collect.add_argument("--archive-days", type=int, default=90)
    collect.add_argument("--sync-notion", action="store_true", help="Explicitly publish to Notion")
    collect.add_argument("--interval", type=int, default=0, help="Repeat locally every N seconds; 0 runs once")
    commands.add_parser("topics", help="List ranked topics, including archived ones")
    commands.add_parser("sync", help="Publish pending changes to Notion")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.command == "run" and (not 1 <= args.limit <= 100 or args.archive_days <= 0 or
                                   (args.interval != 0 and args.interval < 60)):
        p.error("limit must be 1..100; archive-days positive; interval 0 or >=60")
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("radar")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(args.log, maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    store = Store(args.db)
    http = HTTP()
    try:
        if args.command == "topics":
            print(json.dumps(store.topics(), indent=2))
            return 0
        notion = None
        if args.command == "sync" or args.sync_notion:
            notion = Notion(http, os.getenv("NOTION_TOKEN"), os.getenv("NOTION_PARENT_PAGE_ID"))
        if args.command == "sync":
            print(json.dumps({"notion_synced": notion.sync(store)}))
            return 0
        reasoner = SampleReasoner() if args.mode == "sample" else GeminiReasoner(
            http, os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
        while True:
            if args.mode == "sample":
                sources = collectors.sample()
            else:
                # Fail visibly if any collector fails; never silently replace live data with fixtures.
                sources = []
                for url in args.rss or ["https://huggingface.co/blog/feed.xml"]:
                    sources.extend(collectors.rss(http, url, args.limit))
                sources.extend(collectors.arxiv(http, args.arxiv_query, args.limit))
                sources.extend(collectors.github(http, args.github_query, args.limit, os.getenv("GITHUB_TOKEN")))
            counts = run(store, sources, reasoner, archive_days=args.archive_days)
            if notion:
                counts["notion_synced"] = notion.sync(store)
            print(json.dumps({"mode": args.mode, **counts}), flush=True)
            if not args.interval:
                return 0
            time.sleep(args.interval)
    except (IntegrationError, ValueError, KeyError, TypeError, ET.ParseError, sqlite3.Error, OSError) as exc:
        # Avoid leaking tokens from arbitrary SDK/remote exception bodies.
        logger.error("command=%s failed; check configuration, connectivity, and run history", args.command)
        if isinstance(exc, IntegrationError):
            print("Radar command failed: " + str(exc))
        else:
            print("Radar command failed. Check credentials, service access, input format, and local run history.")
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        store.close()
        logger.removeHandler(handler)
        handler.close()
