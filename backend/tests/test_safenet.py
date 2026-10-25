"""SafeNet KZ detector: normalisation, numeric extractors, gates, LLM guard, groups, metrics."""
from app.services.safenet import analyze_text, detect
from app.services.safenet import numeric
from app.services.safenet.detector import parse_llm_hits
from app.services.safenet.evaluation import evaluate, load
from app.services.safenet.group import analyze_chat, parse_chat, template_clusters, Message
from app.services.safenet.normalize import build_views, detect_language


# --- normalisation (anti-obfuscation) -----------------------------------------
def test_views_undo_obfuscation():
    assert "казино" in build_views("к@зин0 без верификации").deobf
    assert "казино" in build_views("К А З И Н О с выводом").collapsed
    assert "казино" in build_views("KAЗИНО").deobf                     # latin homoglyphs
    assert "vavada" in build_views("𝓿𝓪𝓿𝓪𝓭𝓪").base                      # styled unicode
    assert "гарантированный доход" in build_views("garantirovannyi dohod").translit
    assert "тегин" in build_views("Қатысу тегін").base                 # Kazakh folded


def test_obfuscated_quote_is_reported_with_view():
    a = analyze_text("кaзинo без верификации, ссылка в шапке")
    gambling = next(s for s in a.signals if s["signal"] == "casino.gambling")
    assert any(q["view"] == "deobf" for q in gambling["quotes"])


def test_language_detection():
    assert detect_language("Ұтыс ойыны! Қатысу тегін") == "kk"
    assert detect_language("Розыгрыш! Қатысу үшін 1000 тг аударыңыз, итоги в прямом эфире") == "mixed"
    assert detect_language("vlozhi 10000 i poluchi 30000") == "translit"


# --- numeric extractors ------------------------------------------------------
def test_return_ratio_and_rate():
    assert numeric.return_ratio("вложи 5000 тг получи 10 000 тг")
    assert numeric.return_rate("доход 3% в день")
    assert not numeric.return_rate("депозит 15% годовых")
    assert not numeric.return_rate("депозит под 16%, проценты капитализируются ежемесячно")
    # «120% за 2 месяца» = 60% в месяц
    assert numeric.return_rate("доходность 120% за 2 месяца")
    # periodic payout smaller than the stake: 30% a week
    assert numeric.return_ratio("вложила 5 000, вывожу по 1 500 каждую неделю")


def test_card_numbers_luhn_and_masking():
    cards = numeric.card_numbers("карта 4400 4301 2345 6789")
    assert cards and numeric.mask_card(cards[0][0]) == "4400 43•• •••• 6789"
    assert not numeric.card_numbers("номер 1234 5678 1234 5678")      # Luhn-invalid


# --- false-positive gates ------------------------------------------------------
def test_paid_lottery_vs_free_giveaway():
    paid = analyze_text("Розыгрыш iPhone! Номер 1000 тг, перевод на Kaspi. Рандомайзер в эфире")
    free = analyze_text("Розыгрыш iPhone! Подпишись, лайк, отметь друга. Участие бесплатное, рандомайзер в эфире")
    assert paid.track == "lottery" and paid.threat_level.value == "HIGH"
    assert free.threat_level.value == "LOW"


def test_tournament_fee_is_not_a_lottery():
    a = analyze_text("Шахматный турнир, взнос 1000 тг, призовой фонд 50 000 тг для победителей")
    assert a.threat_level.value == "LOW"


def test_bank_deposit_and_rate_news_are_clean():
    for t in ("Депозит в Halyk: 15% годовых, гарантировано КФГД",
              "Процентная ставка по ипотеке снизилась до 12%",
              "Инвестиции в золото: гарантий доходности нет"):
        assert analyze_text(t).score < 40, t


def test_warning_post_is_discounted_but_real_call_is_not():
    warning = analyze_text("Осторожно, мошенники! Пирамиды обещают 30% в месяц. Не переводите деньги")
    scam = analyze_text("Доход 30% в месяц! Переводи на Kaspi +7 701 555 12 34, осторожно — мест мало")
    assert warning.score < 40
    assert scam.score >= 40


def test_sports_news_about_bets_is_capped():
    assert analyze_text("Букмекеры принимают ставки на финал Лиги чемпионов").score < 40


def test_breakdown_sums_to_score():
    a = analyze_text("Вложи 5000 тг, через неделю получишь 10 000! Осталось 3 места. Перевод на Kaspi Gold")
    assert round(sum(b["contribution"] for b in a.breakdown)) == a.score
    assert a.disclaimer and "не объявляет" in a.disclaimer


# --- LLM assist: quotes must exist in the text --------------------------------
def test_llm_hallucinated_quote_is_dropped():
    text = "Вложи 5к, через неделю будет 15к"
    raw = '[{"signal": "pyramid.unrealistic_return", "quote": "через неделю будет 15к"},' \
          ' {"signal": "casino.gambling", "quote": "лучшее казино"},' \
          ' {"signal": "unknown.signal", "quote": "Вложи 5к"}]'
    assert parse_llm_hits(raw, text) == [("pyramid.unrealistic_return", "через неделю будет 15к")]


class _LLM:
    def __init__(self, raw):
        self.raw = raw

    def complete(self, system, user):
        return self.raw


def test_llm_hit_is_used_with_its_quote():
    text = "Каждый день капает понемногу, ничего делать не надо"
    det = detect([("text", text)], llm=_LLM('[{"signal": "pyramid.unrealistic_return", "quote": "Каждый день капает"}]'))
    hit = det.hits["pyramid.unrealistic_return"]
    assert hit.strength == 0.8 and hit.quotes[0].source == "llm"


# --- groups ------------------------------------------------------------------
def test_whatsapp_and_plain_parsing():
    wa = parse_chat("12.10.2026, 18:00 - Админ: Номер = 1000 тг\n12.10.2026, 18:01 - Айжан: мне 7")
    assert wa.platform == "whatsapp" and wa.messages[0].author == "Админ"
    plain = parse_chat("[Куратор]: вложи 5000\n[Аня]: ок")
    assert [m.author for m in plain.messages] == ["Куратор", "Аня"]


def test_template_messages_from_different_authors():
    msgs = [Message(a, "Выплата пришла, спасибо Алия! Всем рекомендую 🙏") for a in ("A", "B", "C")]
    msgs.append(Message("D", "кто идет на йогу завтра утром?"))
    clusters = template_clusters(msgs)
    assert clusters and clusters[0]["size"] == 3


def test_demo_pyramid_group_roles():
    from app.services.safenet.demo import demo_chat_bytes
    raw, name = demo_chat_bytes("pyramid_telegram")
    r = analyze_chat(parse_chat(raw, name))
    assert r["risk"]["track"] == "pyramid" and r["risk"]["threat_level"] == "HIGH"
    assert r["organizer"].startswith("Алия")
    assert "Куратор Ержан" in r["curators"]
    factors = {b["factor"] for b in r["risk"]["breakdown"]}
    assert {"group.template_messages", "group.organizer_curators"} <= factors


# --- metrics regression ------------------------------------------------------
def test_metrics_on_independent_blind_set_do_not_regress():
    r = evaluate(load("blind"))
    assert r["binary"]["fpr"] <= 0.05            # few false positives — the hackathon priority
    assert r["binary"]["precision"] >= 0.9
    assert r["binary"]["recall"] >= 0.6
