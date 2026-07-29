from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def redis_url_with_db(redis_url: str, db: int) -> str:
    """Return a Redis URL that selects ``db`` while preserving connection options."""
    if db < 0:
        raise ValueError("Redis database number must be non-negative")

    parsed = urlsplit(redis_url)
    if parsed.scheme not in {"redis", "rediss"}:
        raise ValueError(f"Unsupported Redis URL scheme: {parsed.scheme!r}")

    query = [(key, value) for key, value in parse_qsl(parsed.query) if key != "db"]
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{db}",
            urlencode(query),
            parsed.fragment,
        )
    )
