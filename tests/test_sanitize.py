import pytest

from app.sanitize import ContentTooLarge, content_hash, sanitize_html


def test_script_tag_and_its_contents_removed():
    out = sanitize_html("<p>hi</p><script>alert(1)</script>")
    assert "script" not in out and "alert" not in out and "hi" in out


def test_event_handler_and_style_removed():
    out = sanitize_html('<p onclick="x()" style="color:red">hi</p>')
    assert out == "<p>hi</p>"


def test_javascript_link_removed_but_text_kept():
    out = sanitize_html('<a href="javascript:alert(1)">click</a>')
    assert "javascript" not in out and "click" in out


def test_safe_links_kept():
    for url in ("https://example.com", "http://example.com", "mailto:a@b.com"):
        assert f'href="{url}"' in sanitize_html(f'<a href="{url}">x</a>')


def test_images_and_iframes_removed():
    out = sanitize_html('<img src="x"><iframe src="https://evil"></iframe><p>ok</p>')
    assert out == "<p>ok</p>"


def test_allowed_formatting_survives():
    html = ("<h1>a</h1><h2>b</h2><h3>c</h3><p><strong>b</strong><em>i</em><u>u</u></p>"
            "<ul><li>x</li></ul><ol><li>y</li></ol>")
    assert sanitize_html(html) == html


def test_sanitizing_twice_changes_nothing():
    # Needed for "identical content causes no change": a re-save must hash the same.
    once = sanitize_html('<p>hi <a href="https://example.com">link</a> <b>x</b></p>')
    assert sanitize_html(once) == once


def test_too_large_is_rejected():
    with pytest.raises(ContentTooLarge):
        sanitize_html("a" * 500_001)


def test_hash_is_stable_and_content_sensitive():
    assert content_hash("<p>a</p>") == content_hash("<p>a</p>")
    assert content_hash("<p>a</p>") != content_hash("<p>b</p>")
