def extract_api_message(detail: object | None) -> str | None:
    if not detail or not isinstance(detail, dict):
        return None

    nested = detail.get("detail")
    message = detail.get("message")
    if isinstance(message, str):
        return message
    if isinstance(nested, str):
        return nested
    if isinstance(nested, dict):
        nested_message = nested.get("message")
        nested_code = nested.get("code")
        if isinstance(nested_message, str):
            return nested_message
        if isinstance(nested_code, str):
            return nested_code
    return None


def origin_allowed(origin: str | None, expected_origin: str) -> bool:
    return bool(origin and origin == expected_origin)


def csrf_valid(method: str, csrf_cookie: str | None, csrf_header: str | None) -> bool:
    if method in {"GET", "HEAD"}:
        return True
    return bool(csrf_cookie and csrf_header and csrf_cookie == csrf_header)


def test_extract_api_message_reads_nested_fastapi_detail():
    assert (
        extract_api_message({"detail": {"code": "BACKEND_UNAVAILABLE", "message": "Backend unavailable."}})
        == "Backend unavailable."
    )


def test_extract_api_message_reads_string_detail():
    assert extract_api_message({"detail": "Authentication required"}) == "Authentication required"


def test_account_selection_422_message_stays_distinguishable():
    assert (
        extract_api_message({"detail": {"message": "Account selection is required for this view."}})
        == "Account selection is required for this view."
    )


def test_origin_mismatch_rejected():
    assert origin_allowed("http://evil.example", "http://localhost:3000") is False
    assert origin_allowed("http://localhost:3000", "http://localhost:3000") is True


def test_csrf_token_required_for_mutations():
    assert csrf_valid("POST", "abc", "abc") is True
    assert csrf_valid("POST", "abc", "def") is False
    assert csrf_valid("GET", None, None) is True
