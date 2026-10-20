#!/usr/bin/env python3
"""Append new public Patreon quips to the local Markdown archive.

Usage:
    python3 quips/scrape_patreon_quips.py
    python3 quips/scrape_patreon_quips.py --output path/to/archive.md

Creator details and the default archive filename template are loaded from the
adjacent patreon_config.json file. Start by copying
quips/patreon_config.example.json to quips/patreon_config.json, then replace
the example values. Featured images are downloaded beside the archive in an
archive-specific images directory.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


API_PATH = "/api/quick_posts_feed/v1"
PAGE_SIZE = 10
CONFIG_PATH = Path(__file__).with_name("patreon_config.json")
ARCHIVE_FOOTER = (
    ". Entries are listed newest first; Patreon displayed the newest entry "
    "as “Yesterday” when collected.\n\n"
)

SAVED_LINK_RE = re.compile(r"(?m)^\[Patreon quip\]\((https?://[^)\s]+)\)")


def load_config() -> dict[str, str]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Could not read creator config {CONFIG_PATH}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Creator config {CONFIG_PATH} is not valid JSON.") from exc

    if not isinstance(config, dict):
        raise RuntimeError(f"Scraper config {CONFIG_PATH} must contain a JSON object.")
    required = (
        "campaign_id",
        "creator_name",
        "creator_slug",
        "platform_url",
        "profile_url",
        "user_agent",
        "archive_filename_template",
    )
    missing = [
        key
        for key in required
        if not isinstance(config.get(key), str) or not config[key].strip()
    ]
    if missing:
        raise RuntimeError(
            f"Scraper config {CONFIG_PATH} must define non-empty string values for: "
            + ", ".join(missing)
        )
    archive_template = config["archive_filename_template"]
    try:
        archive_name = archive_template.format(year=datetime.now().year)
    except (IndexError, KeyError, ValueError) as exc:
        raise RuntimeError(
            "archive_filename_template must be a valid format string using {year}."
        ) from exc
    if (
        "{year}" not in archive_template
        or Path(archive_name).name != archive_name
        or "\\" in archive_name
    ):
        raise RuntimeError(
            "archive_filename_template must be a filename containing the {year} "
            "placeholder."
        )
    return config


def initial_feed_params(config: dict[str, str]) -> dict[str, str]:
    return {
        "filter[campaign_id]": config["campaign_id"],
        "fields[launcher-feed-section]": "footer",
        "fields[launcher-feed-item]": "",
        "fields[feed-card-quick-post]": "",
        "fields[post]": "content_json_string,published_at,url,post_type,title,image",
        "include": "items,items.card_quick_post,items.card_quick_post.post",
        "json-api-version": "1.0",
        "json-api-use-default-includes": "false",
        "json-api-use-default-fields": "false",
    }


def page_feed_params(config: dict[str, str]) -> dict[str, str]:
    return {
        "filter[campaign_id]": config["campaign_id"],
        "fields[launcher-feed-item]": "",
        "fields[feed-card-quick-post]": "",
        "fields[post]": "content_json_string,published_at,url,post_type,title,image",
        "include": "card_quick_post,card_quick_post.post",
        "page[size]": str(PAGE_SIZE),
        "json-api-version": "1.0",
        "json-api-use-default-includes": "false",
        "json-api-use-default-fields": "false",
    }


def fetch_json(
    path: str, params: dict[str, str], config: dict[str, str]
) -> dict:
    url = (
        f"{config['platform_url'].rstrip('/')}{API_PATH}{path}"
        f"?{urlencode(params)}"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.api+json",
            "Referer": config["profile_url"],
            "User-Agent": config["user_agent"],
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


def saved_post_ids(markdown: str, config: dict[str, str]) -> set[str]:
    platform_host = urlparse(config["platform_url"]).netloc
    post_path_re = re.compile(r"/posts/(?:[^/\s)]*-)?(\d+)(?:[/?#]|$)")
    ids = set()
    for link in SAVED_LINK_RE.finditer(markdown):
        url = urlparse(link.group(1))
        if url.netloc != platform_host:
            continue
        post_path = post_path_re.search(url.path)
        if post_path:
            ids.add(post_path.group(1))
    return ids


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


def save_featured_image(
    post: dict, output_path: Path, config: dict[str, str]
) -> str | None:
    image = post.get("attributes", {}).get("image")
    if not isinstance(image, dict):
        return None
    image_url = image.get("large_url") or image.get("url") or image.get("thumb_url")
    if not isinstance(image_url, str) or not image_url:
        return None

    request = Request(
        image_url,
        headers={
            "Referer": config["profile_url"],
            "User-Agent": config["user_agent"],
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            image_data = response.read()
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Could not download featured image for Patreon post {post.get('id')}: "
            f"{exc}"
        ) from exc

    if not content_type.startswith("image/"):
        raise RuntimeError(
            f"Patreon returned non-image content for featured image on post "
            f"{post.get('id')}: {content_type}"
        )
    extension = mimetypes.guess_extension(content_type) or ".img"
    if extension == ".jpe":
        extension = ".jpg"
    post_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(post.get("id", "")))
    if not post_id:
        raise RuntimeError("Cannot save featured image for a post without an ID.")

    image_directory = output_path.parent / f"{output_path.stem}_images"
    image_directory.mkdir(parents=True, exist_ok=True)
    image_path = image_directory / f"{post_id}{extension}"
    image_path.write_bytes(image_data)
    return Path(os.path.relpath(image_path, start=output_path.parent)).as_posix()


def format_post(
    post: dict, config: dict[str, str], output_path: Path
) -> str:
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
        f"{config['platform_url'].rstrip('/')}/{config['creator_slug']}/posts/{post_id}"
    )
    body = render_post_body(post)
    featured_image_path = save_featured_image(post, output_path, config)
    image_markdown = (
        f"\n\n![Featured image]({featured_image_path})" if featured_image_path else ""
    )
    return f"## {date}\n\n[Patreon quip]({url}){image_markdown}\n\n{body}"


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


def scrape(output_path: Path, config: dict[str, str]) -> int:
    if output_path.exists() and not output_path.is_file():
        raise RuntimeError(f"Archive path is not a file: {output_path}")
    if output_path.is_file():
        markdown = output_path.read_text(encoding="utf-8")
    else:
        markdown = ""
    archive_pattern = config["archive_filename_template"].replace("{year}", "*")
    archive_paths = set(CONFIG_PATH.parent.glob(archive_pattern))
    archive_paths.add(output_path)
    known_ids = set()
    for archive_path in archive_paths:
        if archive_path.is_file():
            known_ids.update(
                saved_post_ids(archive_path.read_text(encoding="utf-8"), config)
            )

    payload = fetch_json("", initial_feed_params(config), config)
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
        params = page_feed_params(config)
        params["page[cursor]"] = cursor
        page = fetch_json("/section_feed", params, config)
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
        if not markdown:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                archive_header(config)
                + datetime.now().strftime("%B %d, %Y").replace(" 0", " ")
                + ARCHIVE_FOOTER,
                encoding="utf-8",
            )
            print(f"Created empty quip archive at {output_path}; no quips were found.")
        else:
            print("No new quips found; the newest feed entry is already in the archive.")
        return 0

    entries = "\n\n".join(
        format_post(post, config, output_path) for post in new_posts
    )
    collected_date = datetime.now().strftime("%B %d, %Y").replace(" 0", " ")
    if not markdown:
        updated = (
            archive_header(config) + collected_date + ARCHIVE_FOOTER + entries + "\n"
        )
    else:
        updated = re.sub(
            r"^(Public quips from .+?, collected )[^.]+(\. Entries are listed newest first;.*)$",
            lambda match: match.group(1) + collected_date + match.group(2),
            markdown,
            count=1,
            flags=re.MULTILINE,
        )
        updated = insert_entries(updated, entries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(updated, encoding="utf-8")
    print(f"Saved {len(new_posts)} new quip(s) to {output_path}.")
    if stop_id:
        print(f"Stopped at previously saved quip {stop_id}.")
    else:
        print("Reached the end of the available Quips feed.")
    return len(new_posts)


def archive_header(config: dict[str, str]) -> str:
    return (
        "# Patreon Quips\n\n"
        f"Public quips from [{config['creator_name']}'s Patreon Quips page]"
        f"({config['profile_url']}), collected "
    )


def default_output_path(config: dict[str, str], year: int | None = None) -> Path:
    archive_year = datetime.now().year if year is None else year
    archive_name = config["archive_filename_template"].format(year=archive_year)
    return CONFIG_PATH.with_name(archive_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Markdown archive to update (overrides the configured default).",
    )
    args = parser.parse_args()
    try:
        config = load_config()
        output_path = args.output or default_output_path(config)
        scrape(output_path, config)
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
