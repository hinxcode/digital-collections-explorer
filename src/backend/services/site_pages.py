"""The pages a deployed site shows to crawlers: home page metadata, robots.txt and llms.txt"""

import re
from html import escape
from pathlib import Path
from typing import Any, Dict

PROJECT_URL = "https://github.com/hinxcode/digital-collections-explorer"
PAPER_URL = "https://arxiv.org/abs/2507.00961"

ROBOTS_TXT = """\
# This collection is public. Search engines and AI assistants are welcome to read it.
# Only the search endpoints are kept off limits: they are the one costly thing the site does.
User-agent: *
Allow: /
Disallow: /api/search/

User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /
"""

TITLE = re.compile(r"<title>.*?</title>", re.DOTALL)
DESCRIPTION = re.compile(r'<meta name="description" content=".*?"\s*/?>', re.DOTALL)


def home_page(index_html: str, collection: Dict[str, Any]) -> str:
    """Fill the home page's title, description and sharing tags from the collection"""
    title = escape(collection.get("title") or "Digital Collections Explorer")
    description = escape(collection.get("description") or "")
    tags = "\n    ".join(
        [
            f"<title>{title}</title>",
            f'<meta name="description" content="{description}" />',
            f'<meta property="og:title" content="{title}" />',
            f'<meta property="og:description" content="{description}" />',
            '<meta property="og:type" content="website" />',
            '<meta name="twitter:card" content="summary" />',
        ]
    )
    page = DESCRIPTION.sub("", index_html, count=1)
    if TITLE.search(page):
        return TITLE.sub(lambda _: tags, page, count=1)
    return page.replace("</head>", f"{tags}\n  </head>", 1)


def llms_txt(collection: Dict[str, Any]) -> str:
    """Describe the site to AI assistants in the llms.txt format"""
    title = collection.get("title") or "Digital Collections Explorer"
    description = collection.get("description") or ""
    lines = [f"# {title}", "", f"> {description}", ""]
    counts = []
    if collection.get("images"):
        counts.append(f"{collection['images']:,} images")
    if collection.get("objects"):
        counts.append(f"{collection['objects']:,} objects")
    if counts:
        lines += [f"This site holds {' in '.join(counts)}.", ""]
    if collection.get("source_name"):
        lines += [f"The images come from {collection['source_name']}.", ""]
    licence = collection.get("license") or {}
    if licence.get("name"):
        note = f" ({licence['note']})" if licence.get("note") else ""
        lines += [f"Licence: {licence['name']}{note}.", ""]
    lines += [
        "Visitors search the collection by describing what they are looking for in plain",
        "language, or by uploading a picture. No catalogue or metadata is needed: search",
        "compares the meaning of the words with the content of the images.",
        "",
        "## Searching",
        "",
        "- [Text search](/api/search/text?query=a+steam+locomotive): "
        "GET with `query`, optional `limit` and `page`; returns ranked images",
        "- [Image search](/api/search/image): POST an image file; returns similar images",
        "- [About this collection](/api/collection): title, size, suggested searches",
        "- [API reference](/docs): every endpoint, as OpenAPI",
        "",
        "## Software",
        "",
        f"- [Digital Collections Explorer]({PROJECT_URL}): "
        "the open-source software that runs this site",
        f"- [Paper]({PAPER_URL}): how the search works and how it was evaluated",
    ]
    for link in collection.get("links") or []:
        if link.get("label") and link.get("url"):
            lines.append(f"- [{link['label']}]({link['url']})")
    return "\n".join(lines) + "\n"


def read_index(frontend_dir: Path) -> str:
    """The frontend's index.html as built"""
    return (frontend_dir / "index.html").read_text(encoding="utf-8")
