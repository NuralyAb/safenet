from app.services.ssrf import check_url, is_safe_url, UnsafeURLError

ALLOW = ["api.telegram.org", "www.youtube.com"]


def test_allows_allowlisted_https_host():
    assert is_safe_url("https://api.telegram.org/file/x.mp4", ALLOW) is True


def test_blocks_cloud_metadata_endpoint():
    assert is_safe_url("http://169.254.169.254/latest/meta-data/", ALLOW) is False


def test_blocks_private_and_loopback_literals():
    assert is_safe_url("http://10.0.0.5/internal", ALLOW) is False
    assert is_safe_url("http://192.168.1.1/", ALLOW) is False
    assert is_safe_url("http://127.0.0.1:6379/", ALLOW) is False


def test_blocks_host_not_in_allowlist():
    assert is_safe_url("https://evil.example.com/x", ALLOW) is False


def test_blocks_non_http_scheme():
    assert is_safe_url("file:///etc/passwd", ALLOW) is False
    assert is_safe_url("gopher://api.telegram.org/", ALLOW) is False


def test_check_url_raises_with_reason():
    try:
        check_url("http://169.254.169.254/", ALLOW)
        assert False, "should have raised"
    except UnsafeURLError as e:
        assert "blocked address" in str(e)
