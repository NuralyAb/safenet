from app.services.cookies import header_to_netscape


def test_converts_header_to_netscape_lines():
    out = header_to_netscape("sessionid=abc123; ds_user_id=42", ".instagram.com")
    lines = out.strip().splitlines()
    assert lines[0].startswith("# Netscape")
    rows = [ln for ln in lines if not ln.startswith("#")]
    assert len(rows) == 2
    # domain include_subdomains path secure expiry name value
    cols = rows[0].split("\t")
    assert cols[0] == ".instagram.com" and cols[1] == "TRUE" and cols[2] == "/" and cols[3] == "TRUE"
    assert cols[5] == "sessionid" and cols[6] == "abc123"


def test_skips_blank_and_malformed_pairs():
    out = header_to_netscape("a=1; ; junk; b=2;", ".tiktok.com")
    rows = [ln for ln in out.strip().splitlines() if not ln.startswith("#")]
    assert {r.split("\t")[5]: r.split("\t")[6] for r in rows} == {"a": "1", "b": "2"}


def test_handles_values_with_equals():
    out = header_to_netscape("token=ab=cd==", ".instagram.com")
    row = [ln for ln in out.strip().splitlines() if not ln.startswith("#")][0]
    cols = row.split("\t")
    assert cols[5] == "token" and cols[6] == "ab=cd=="
