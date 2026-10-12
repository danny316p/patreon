#!/usr/bin/env python3
"""Append new public Patreon quips to the local Markdown archive.

Usage:
    python3 quips/scrape_patreon_quips.py
    python3 quips/scrape_patreon_quips.py --output quips/Patreon_Quips_2026.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CAMPAIGN_ID = "12110557"
API_ROOT = "https://www.patreon.com/api/quick_posts_feed/v1"
PROFILE_URL = "https://www.patreon.com/cw/DanPikora/quips"
PAGE_SIZE = 10
USER_AGENT = "Mozilla/5.0 (compatible; PatreonQuipArchive/1.0)"

INITIAL_PARAMS = {
    "filter[campaign_id]": CAMPAIGN_ID,
    "fields[launcher-feed-section]": "footer",
    "fields[launcher-feed-item]": "",
    "fields[feed-card-quick-post]": "",
    "fields[post]": "content_json_string,published_at,url,post_type,title",
    "include": "items,items.card_quick_post,items.card_quick_post.post",
    "json-api-version": "1.0",
    "json-api-use-default-includes": "false",
    "json-api-use-default-fields": "false",
}

PAGE_PARAMS = {
    "filter[campaign_id]": CAMPAIGN_ID,
    "fields[launcher-feed-item]": "",
    "fields[feed-card-quick-post]": "",
    "fields[post]": "content_json_string,published_at,url,post_type,title",
    "include": "card_quick_post,card_quick_post.post",
    "page[size]": str(PAGE_SIZE),
    "json-api-version": "1.0",
    "json-api-use-default-includes": "false",
    "json-api-use-default-fields": "false",
}

SAVED_ID_RE = re.compile(
    r"(?m)^\[Patreon quip\]\(https://www\.patreon\.com/[^/]+/posts/"
    r"(?:[^/\s)]*-)?(\d+)(?=[/?#)])"
)


def fetch_json(path: str, params: dict[str, str]) -> dict:
    url = f"{API_ROOT}{path}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.api+json",
            "Referer": PROFILE_URL,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Patreon request failed for {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Patreon returned invalid JSON for {url}") from exc


def get_feed_posts(payload: dict) -> list[dict]:
    included = {
        (item.get("type"), item.get("id")): item
        for item in payload.get("included", [])
    }
    posts = []

    for item in payload.get("data", []):
        if item.get("type") == "launcher-feed-section":
            feed_items = (
                item.get("relationships", {})
                .get("items", {})
                .get("data", [])
            )
        else:
            feed_items = [item]

        for feed_item_ref in feed_items:
            feed_item = included.get(
                (feed_item_ref.get("type"), feed_item_ref.get("id")),
                feed_item_ref,
            )
            card_ref = (
                feed_item.get("relationships", {})
                .get("card_quick_post", {})
                .get("data")
            )
            if not card_ref:
                continue
            card = included.get((card_ref.get("type"), card_ref.get("id")))
            if not card:
                continue
            post_ref = card.get("relationships", {}).get("post", {}).get("data")
            if not post_ref:
                continue
            post = included.get((post_ref.get("type"), post_ref.get("id")))
            if post:
                posts.append(post)
    return posts


def next_cursor(payload: dict) -> str | None:
    return (
        payload.get("meta", {})
        .get("pagination", {})
        .get("cursors", {})
        .get("next")
    )


def saved_post_ids(markdown: str) -> set[str]:
    return {match.group(1) for match in SAVED_ID_RE.finditer(markdown)}


def render_inline(node: dict) -> str:
    if node.get("type") == "text":
        text = node.get("text", "")
        for mark in node.get("marks", []):
            mark_type = mark.get("type")
            if mark_type == "link":
                href = mark.get("attrs", {}).get("href", "")
                if href and href != text:
                    text = f"[{text}]({href})"
            elif mark_type == "bold":
                text = f"**{text}**"
            elif mark_type == "italic":
                text = f"*{text}*"
            elif mark_type == "strike":
                text = f"~~{text}~~"
            elif mark_type == "code":
                text = f"`{text}`"
        return text
    if node.get("type") == "hardBreak":
        return "  \n"
    return "".join(render_inline(child) for child in node.get("content", []))


def render_block(node: dict) -> str:
    node_type = node.get("type")
    children = node.get("content", [])
    if node_type == "paragraph":
        return "".join(render_inline(child) for child in children)
    if node_type == "heading":
        level = max(1, min(int(node.get("attrs", {}).get("level", 2)), 6))
        return "#" * level + " " + "".join(
            render_inline(child) for child in children
        )
    if node_type == "blockquote":
        return "\n".join(f"> {render_block(child)}" for child in children)
    if node_type == "codeBlock":
        code = "".join(render_inline(child) for child in children)
        return f"```\n{code}\n```"
    if node_type in ("bulletList", "orderedList"):
        lines = []
        for index, child in enumerate(children, start=1):
            prefix = "- " if node_type == "bulletList" else f"{index}. "
            lines.append(prefix + render_block(child).replace("\n", "\n  "))
        return "\n".join(lines)
    if node_type == "listItem":
        return "\n".join(render_block(child) for child in children)
    return "".join(render_block(child) for child in children)


def render_post_body(post: dict) -> str:
    raw = post.get("attributes", {}).get("content_json_string") or ""
    if not raw:
        return "_No text content._"
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid rich-text content for Patreon post {post.get('id')}"
        ) from exc
    blocks = [
        rendered
        for rendered in (
            render_block(node) for node in document.get("content", [])
        )
        if rendered.strip()
    ]
    return "\n\n".join(blocks)


def format_post(post: dict) -> str:
    attributes = post.get("attributes", {})
    published_at = attributes.get("published_at")
    if published_at:
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            date = published.strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid published_at value for Patreon post {post.get('id')}: "
                f"{published_at}"
            ) from exc
    else:
        date = "Date unavailable"

    post_id = str(post.get("id", ""))
    url = attributes.get("url") or (
        f"https://www.patreon.com/DanPikora/posts/{post_id}"
    )
    body = render_post_body(post)
    return f"## {date}\n\n[Patreon quip]({url})\n\n{body}"


def collect_new_posts(
    posts: list[dict], known_ids: set[str]
) -> tuple[list[dict], str | None]:
    new_posts = []
    seen_ids = set()
    for post in posts:
        post_id = str(post.get("id", ""))
        if post_id in known_ids:
            return new_posts, post_id
        if post_id and post_id not in seen_ids:
            new_posts.append(post)
            seen_ids.add(post_id)
    return new_posts, None


def insert_entries(markdown: str, entries: str) -> str:
    first_entry = re.search(r"(?m)^## ", markdown)
    if first_entry:
        return (
            markdown[: first_entry.start()]
            + entries
            + "\n\n"
            + markdown[first_entry.start() :]
        )
    return markdown.rstrip() + "\n\n" + entries + "\n"


def scrape(output_path: Path) -> int:
    if not output_path.is_file():
        raise RuntimeError(f"Archive file not found: {output_path}")
    markdown = output_path.read_text(encoding="utf-8")
    known_ids = saved_post_ids(markdown)
    if not known_ids:
        raise RuntimeError(
            f"No saved Patreon quip links found in {output_path}; "
            "refusing to append blindly."
        )

    payload = fetch_json("", INITIAL_PARAMS)
    sections = payload.get("data", [])
    if not sections:
        raise RuntimeError("Patreon returned no Quips feed section.")

    new_posts, stop_id = collect_new_posts(get_feed_posts(payload), known_ids)
    known_ids.update(str(post["id"]) for post in new_posts)
    cursor = (
        sections[0].get("attributes", {})
        .get("footer", {})
        .get("pagination", {})
        .get("cursor")
    )
    while cursor and not stop_id:
        params = dict(PAGE_PARAMS)
        params["page[cursor]"] = cursor
        page = fetch_json("/section_feed", params)
        page_posts = get_feed_posts(page)
        if not page_posts:
            break

        page_new_posts, stop_id = collect_new_posts(page_posts, known_ids)
        new_posts.extend(page_new_posts)
        known_ids.update(str(post["id"]) for post in page_new_posts)

        new_cursor = next_cursor(page)
        if new_cursor == cursor:
            raise RuntimeError("Patreon returned the same pagination cursor twice.")
        cursor = new_cursor

    if not new_posts:
        print("No new quips found; the newest feed entry is already in the archive.")
        return 0

    entries = "\n\n".join(format_post(post) for post in new_posts)
    collected_date = datetime.now().strftime("%B %d, %Y").replace(" 0", " ")
    updated = re.sub(
        r"^(Public quips from .+?, collected )[^.]+(\. Entries are listed newest first;.*)$",
        lambda match: match.group(1) + collected_date + match.group(2),
        markdown,
        count=1,
        flags=re.MULTILINE,
    )
    output_path.write_text(insert_entries(updated, entries), encoding="utf-8")
    print(f"Saved {len(new_posts)} new quip(s) to {output_path}.")
    if stop_id:
        print(f"Stopped at previously saved quip {stop_id}.")
    else:
        print("Reached the end of the available Quips feed.")
    return len(new_posts)


def main() -> int:
    default_output = Path(__file__).with_name("Patreon_Quips_2026.md")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help=f"Markdown archive to update (default: {default_output})",
    )
    args = parser.parse_args()
    try:
        scrape(args.output)
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
