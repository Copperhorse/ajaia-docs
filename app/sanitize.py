"""HTML sanitizer: the security boundary. All stored and returned HTML goes through here."""
import hashlib

import nh3

MAX_CONTENT_CHARS = 500_000

ALLOWED_TAGS = {"p", "br", "h1", "h2", "h3", "strong", "em", "u", "ul", "ol", "li", "a"}
ALLOWED_ATTRIBUTES = {"a": {"href"}}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


class ContentTooLarge(ValueError):
    pass


def sanitize_html(html: str) -> str:
    if len(html) > MAX_CONTENT_CHARS:
        raise ContentTooLarge(f"Document is too large (limit {MAX_CONTENT_CHARS:,} characters)")
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel=None,  # no target=_blank is allowed, so no rel needed; keeps output minimal
    )


def content_hash(sanitized_html: str) -> str:
    return hashlib.sha256(sanitized_html.encode()).hexdigest()
