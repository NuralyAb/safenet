from app.services.extract import extract_identifiers


def test_extracts_telegram_handles():
    ids = extract_identifiers("Пиши в @FastMoney или https://t.me/newmoney_pro")
    assert ids["telegram"] == ["fastmoney", "newmoney_pro"]


def test_extracts_crypto_wallets():
    text = "USDT TRC20: TJRabPrwbZy45sbavfcjinPJC18kjpRTv8 ETH 0x" + "a" * 40
    ids = extract_identifiers(text)
    assert any(w.startswith("T") for w in ids["wallets"])
    assert any(w.startswith("0x") for w in ids["wallets"])


def test_extracts_domains_lowercased_unique():
    ids = extract_identifiers("invest at Profit-X.com and profit-x.com plus scam.io")
    assert ids["domains"] == ["profit-x.com", "scam.io"]


def test_uppercase_tme_link_caught_and_not_a_domain():
    # "T.ME/BETBOT" (uppercase, no @) — common in casino posts; was previously missed.
    ids = extract_identifiers("T.ME/BETBOT COMING SOON 🤍")
    assert "betbot" in ids["telegram"]
    assert "t.me" not in ids["domains"]          # the messaging host isn't a standalone domain


def test_extracts_btc_legacy_and_bech32():
    text = ("BTC 1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2 "
            "or bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq")
    ws = extract_identifiers(text)["wallets"]
    assert any(w.startswith("1") for w in ws)
    assert any(w.startswith("bc1") for w in ws)


def test_does_not_catch_garbage_as_wallet():
    # plain prose / short tokens must not be mistaken for crypto addresses
    ids = extract_identifiers("Это обычное предложение про ставки и казино, заходи сейчас!")
    assert ids["wallets"] == []


def test_empty_text_is_safe():
    assert extract_identifiers("") == {"telegram": [], "wallets": [], "domains": [], "phones": []}


def test_phone_extraction_normalizes_kz():
    ids = extract_identifiers("Звоните +7 701 234 56 78 или 8 (777) 111-22-33")
    assert ids["phones"] == ["+77012345678", "+77771112233"]


def test_phone_does_not_match_wallets_or_short_numbers():
    ids = extract_identifiers("0x52908400098527886E0F7030069857D2E4169EE7 цена 100$ в 2024")
    assert ids["phones"] == []
