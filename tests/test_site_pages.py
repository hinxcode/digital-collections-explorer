import asyncio

import pytest

from src.backend.services import site_pages

INDEX = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="description" content="Digital Collections Explorer - Photographs" />
    <title>Digital Collections Explorer - Photographs</title>
  </head>
  <body><div id="root"></div></body>
</html>
"""

SMITHSONIAN = {
    "title": "National Museum of American History",
    "description": "Wander through objects & photographs from the Smithsonian.",
    "source_name": "the Smithsonian",
    "images": 12345,
    "objects": 6789,
    "license": {"name": "CC0 (public domain)", "note": "via Smithsonian Open Access"},
    "links": [
        {"label": "Smithsonian Open Access", "url": "https://www.si.edu/openaccess"}
    ],
}


def test_home_page_carries_the_collection_title_and_description():
    page = site_pages.home_page(INDEX, SMITHSONIAN)

    assert "<title>National Museum of American History</title>" in page
    assert (
        'content="Wander through objects &amp; photographs from the Smithsonian."'
        in page
    )
    assert 'property="og:title" content="National Museum of American History"' in page
    assert "Digital Collections Explorer - Photographs" not in page
    assert page.count("<title>") == 1
    assert page.count('name="description"') == 1


def test_home_page_falls_back_to_the_project_name():
    page = site_pages.home_page(INDEX, {})
    assert "<title>Digital Collections Explorer</title>" in page


def test_home_page_adds_tags_when_the_template_has_none():
    page = site_pages.home_page("<html><head></head><body></body></html>", SMITHSONIAN)
    assert "<title>National Museum of American History</title>" in page
    assert page.index("<title>") < page.index("</head>")


def test_robots_welcome_crawlers_but_not_on_the_search_endpoints():
    assert "User-agent: *\nAllow: /\nDisallow: /api/search/" in site_pages.ROBOTS_TXT
    assert "User-agent: ClaudeBot\nAllow: /" in site_pages.ROBOTS_TXT
    assert "GPTBot" in site_pages.ROBOTS_TXT


def test_llms_txt_describes_the_collection_and_its_api():
    text = site_pages.llms_txt(SMITHSONIAN)

    assert text.startswith("# National Museum of American History\n\n> Wander")
    assert "12,345 images in 6,789 objects" in text
    assert "The images come from the Smithsonian." in text
    assert "Licence: CC0 (public domain) (via Smithsonian Open Access)." in text
    assert "- [Text search](/api/search/text" in text
    assert "- [Smithsonian Open Access](https://www.si.edu/openaccess)" in text
    assert site_pages.PROJECT_URL in text


def test_llms_txt_leaves_out_what_the_collection_does_not_say():
    text = site_pages.llms_txt({"title": "Maps"})
    assert "This site holds" not in text
    assert "Licence" not in text
    assert "The images come from" not in text


@pytest.fixture()
def backend(monkeypatch):
    monkeypatch.setattr(
        "src.backend.services.embedding_service_factory.create_embedding_service",
        lambda: object(),
    )
    from src.backend import main

    return main


def test_site_serves_the_pages_crawlers_read(backend, monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text(INDEX)
    monkeypatch.setattr(backend, "frontend_dir", tmp_path)
    monkeypatch.setattr(backend.collection_service, "info", lambda: SMITHSONIAN)

    home = asyncio.run(backend.home())
    robots = asyncio.run(backend.robots())
    llms = asyncio.run(backend.llms())

    assert "<title>National Museum of American History</title>" in home.body.decode()
    assert home.media_type == "text/html"
    assert robots.body.decode().startswith("# This collection is public.")
    assert llms.body.decode().startswith("# National Museum of American History")


def test_pages_survive_an_index_that_cannot_be_read(backend, monkeypatch):
    def broken():
        raise RuntimeError("no index")

    monkeypatch.setattr(backend.collection_service, "info", broken)
    text = asyncio.run(backend.llms()).body.decode()
    assert text.startswith("# Digital Collection Explorer")
