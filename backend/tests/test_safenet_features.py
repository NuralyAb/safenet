"""SafeNet KZ v4 features: number words, emoji arithmetic, learned layer, «что если»,
campaigns, bulk check, adaptation insights."""
from types import SimpleNamespace

from app.services.safenet import analyze_text, model
from app.services.safenet.bulk import demo_rows, parse_rows, run_bulk
from app.services.safenet.normalize import build_views, fold
from app.services.safenet.numwords import words_to_digits


# --- number words -------------------------------------------------------------
def test_number_words_ru_kz_and_slang():
    assert words_to_digits(fold("вложил двадцать тысяч получил сорок тысяч")) == "вложил 20000 получил 40000"
    assert words_to_digits(fold("бес мың теңге салып он мың алдым")) == "5000 тенге салып 10000 алдым"
    assert words_to_digits(fold("закинул косарь")) == "закинул 1000"
    assert words_to_digits(fold("в два раза больше")) == "в 2 раза больше"


def test_ambiguous_words_stay_words():
    text = fold("он пришел домой и съел торт")
    assert words_to_digits(text) == text                      # «он», «торт» are not numbers here


def test_spelled_out_pyramid_is_detected():
    a = analyze_text("[эфир] кто вложил двадцать тысяч в пятницу получил сорок тысяч успевайте", use_model=False)
    assert a.track == "pyramid" and a.score >= 40


# --- emoji arithmetic -----------------------------------------------------------
def test_emoji_multiplication_view():
    assert "раза больше" in build_views("💵➡️💵💵 за 10 дней").emoji
    assert "раза больше" not in build_views("💵💵➡️💵").emoji     # less money after the arrow
    assert "казино" in build_views("🎰➡️💸").emoji


def test_brand_does_not_fire_inside_casino_word():
    a = analyze_text("казино", use_model=False)
    assert not any(s["signal"] == "casino.brand" for s in a.signals)   # «азино» ⊂ «казино» regression


# --- learned layer --------------------------------------------------------------
def test_model_predicts_track_with_explanation():
    track, p, why = model.predict("Вложи 10 000 тг — через неделю получишь 30 000, пригласи друга")
    assert track == "pyramid" and p > 0.5 and why


def test_model_alone_cannot_make_high():
    # a text the rules barely touch: the model may lift it, but never above «средний»
    a = analyze_text("Каждый день капает понемногу, ничего делать не надо, пиши мне")
    assert a.threat_level.value in ("LOW", "MEDIUM")


def test_model_is_not_trained_on_blind_sets():
    assert set(model.TRAIN_SETS).isdisjoint({"blind", "blind2"})


# --- «что если» -----------------------------------------------------------------
def test_counterfactual_without_each_sign():
    a = analyze_text("Розыгрыш iPhone! Номер 1000 тг, перевод на Kaspi. Рандомайзер в эфире", use_model=False)
    paid = next(b for b in a.breakdown if b["factor"] == "lottery.paid_entry")
    assert paid["without"] < a.score                           # removing the core sign drops the score


# --- campaigns ------------------------------------------------------------------
class _Q:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def filter(self, *_):
        return self

    def __iter__(self):
        return iter(self.rows)


def test_campaigns_link_accounts_by_shared_kaspi_number():
    from app.db.models import Content, ContentRisk
    from app.services.safenet.campaigns import build_campaigns

    texts = {"a": "Розыгрыш! Номер 1000 тг, Kaspi +7 747 123 45 67",
             "b": "Ұтыс! Kaspi-ге аударыңыз +7 747 123 45 67",
             "c": "Обычный пост про кофе"}
    risks = [SimpleNamespace(id=i, content_id=k, author=f"acc_{k}", score=80 if k != "c" else 0,
                             threat_level="HIGH", track="lottery", views=100, source="instagram")
             for i, k in enumerate(texts)]
    contents = [SimpleNamespace(id=k, caption=t, transcript=None, ocr_text=None, collected_at=None)
                for k, t in texts.items()]
    session = SimpleNamespace(query=lambda m: _Q(risks if m is ContentRisk else contents))
    out = build_campaigns(session)
    assert len(out) == 1
    assert {a["account"] for a in out[0]["accounts"]} == {"acc_a", "acc_b"}
    assert out[0]["shared"][0]["kind"] == "телефон"


# --- bulk -----------------------------------------------------------------------
def test_bulk_parses_csv_jsonl_txt():
    assert len(parse_rows("text,author\nВложи 5000 получи 10000,a\nпривет,b\n".encode(), "x.csv")) == 2
    assert len(parse_rows(b'{"text": "a"}\n{"text": "b"}\n', "x.jsonl")) == 2
    assert len(parse_rows("один\nдва\n\n".encode(), "x.txt")) == 2


def test_bulk_demo_feed_is_mostly_clean_and_fast():
    r = run_bulk(demo_rows(400), persist=False)
    assert r["rows"] == 400 and 0 < r["flagged"] < 100
    assert r["items_per_second"] and r["items_per_second"] > 50
