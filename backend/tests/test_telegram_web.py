import httpx
import respx

from app.services import telegram_web
from app.workers.collectors.registry import get_collector

# Minimal but faithful slice of the t.me/s/<channel> widget markup (two posts;
# the second is media-only with no text div).
SAMPLE_HTML = """
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message" data-post="scamchan/101">
    <div class="tgme_widget_message_text js-message_text" dir="auto">
      Вложи 100$ и получай 1000$! Пиши @profitbot, кошелёк 0x52908400098527886E0F7030069857D2E4169EE7 &amp; сайт profit-x.io
    </div>
    <span class="tgme_widget_message_views">12.3K</span>
  </div>
</div>
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message" data-post="scamchan/102">
    <div class="tgme_widget_message_photo_wrap"></div>
    <span class="tgme_widget_message_views">900</span>
  </div>
</div>
"""


def test_normalize_channel_variants():
    for raw in ["@ScamChan", "t.me/ScamChan", "https://t.me/s/ScamChan/101", "ScamChan"]:
        assert telegram_web.normalize_channel(raw) == "ScamChan"


def test_parse_posts_extracts_text_views_and_skips_media_only():
    posts = telegram_web.parse_posts(SAMPLE_HTML, "scamchan")
    assert len(posts) == 2
    p1 = posts[0]
    assert p1["id"] == "scamchan/101"
    assert p1["url"] == "https://t.me/scamchan/101"
    assert "Вложи 100$" in p1["text"] and "@profitbot" in p1["text"]
    assert "&" in p1["text"]                       # HTML entity unescaped
    assert p1["views"] == 12300                    # 12.3K -> 12300
    assert posts[1]["text"] == "" and posts[1]["views"] == 900


@respx.mock
def test_fetch_channel_hits_web_preview_and_limits():
    route = respx.get("https://t.me/s/scamchan").mock(
        return_value=httpx.Response(200, text=SAMPLE_HTML)
    )
    posts = telegram_web.fetch_channel("@scamchan", limit=1)
    assert route.called
    assert len(posts) == 1                          # limited to the most recent


@respx.mock
def test_collector_emits_items_with_extracted_identifiers():
    respx.get("https://t.me/s/scamchan").mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
    items = get_collector("telegram").fetch("@scamchan", limit=20)
    assert len(items) == 1                          # media-only post skipped (no text)
    it = items[0]
    assert it.source == "telegram" and it.author == "@scamchan"
    assert it.content_type.startswith("text/plain") and it.ext == "txt"
    assert it.media == it.text.encode("utf-8")      # post text is the WORM evidence
    assert "profitbot" in it.telegram               # identifiers extracted from the post
    assert any(w.startswith("0x") for w in it.wallets)
    assert "profit-x.io" in it.domains
    assert it.reach == {"views": 12300}


def test_telegram_collector_is_healthy_without_credentials():
    assert get_collector("telegram").health() is True   # public web preview, no API keys
