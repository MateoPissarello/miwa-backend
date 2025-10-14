import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Payloads for testing
sql_injection_payloads = [
    "' OR 1=1 --",
    "' OR '1'='1",
    "admin'--",
    "admin'/*",
    "admin' or 1=1#",
    "1' UNION SELECT 1,2,3,4,5,6,7,8,9,10--",
    "'; EXEC xp_cmdshell('echo vulnerable') --",
]

xss_payloads = [
    "<script>alert('XSS')</script>",
    "<img src=x onerror=alert('XSS')>",
    '\'"\'><script>alert(\"XSS\")</script>',
    "<body onload=alert('XSS')>",
]


@pytest.mark.parametrize("payload", sql_injection_payloads)
def test_sql_injection_login(payload):
    """
    Tests for SQL injection vulnerabilities on the /auth/login endpoint.
    """
    response = client.post("/auth/login", json={"email": payload, "password": "password"})
    assert response.status_code != 500, f"SQL Injection attempt returned a 500 error with payload: {payload}"
    assert response.status_code in [401, 404, 422], (
        f"Unexpected status code {response.status_code} for payload: {payload}"
    )


@pytest.mark.parametrize("payload", xss_payloads)
def test_xss_login(payload):
    """
    Tests for XSS vulnerabilities on the /auth/login endpoint.
    """
    response = client.post("/auth/login", json={"email": payload, "password": "password"})
    assert response.status_code != 500
    assert payload not in response.text, f"XSS payload reflected in response from /auth/login: {payload}"


@pytest.mark.parametrize("payload", sql_injection_payloads)
def test_sql_injection_signup_email(payload):
    """
    Tests for SQL injection vulnerabilities on the /auth/signup endpoint in the email field.
    """
    user_data = {
        "email": payload,
        "password": "testpassword",
        "first_name": "Test",
        "last_name": "User",
        "role": "user",
    }
    response = client.post("/auth/signup", json=user_data)
    assert response.status_code != 500, f"SQL Injection attempt returned a 500 error with payload: {payload}"
    assert response.status_code in [400, 422, 404], (
        f"Unexpected status code {response.status_code} for payload: {payload}"
    )


@pytest.mark.parametrize("payload", xss_payloads)
def test_xss_signup(payload):
    """
    Tests for XSS vulnerabilities on the /auth/signup endpoint.
    """
    user_data = {
        "email": "test@example.com",
        "password": "testpassword",
        "first_name": payload,
        "last_name": "User",
        "role": "user",
    }
    response = client.post("/auth/signup", json=user_data)
    assert response.status_code != 500
    # Pydantic usually catches this and returns a 422, but we check for reflection just in case.
    assert payload not in response.text, f"XSS payload reflected in response from /auth/signup: {payload}"


@pytest.mark.parametrize("payload", sql_injection_payloads)
def test_sql_injection_signup_other_fields(payload):
    """
    Tests for SQL injection vulnerabilities on the /auth/signup endpoint in other text fields.
    """
    user_data = {
        "email": "test@example.com",
        "password": "testpassword",
        "first_name": payload,
        "last_name": payload,
        "role": "user",
    }
    response = client.post("/auth/signup", json=user_data)
    assert response.status_code != 500, f"SQL Injection attempt returned a 500 error with payload: {payload}"
    assert response.status_code in [400, 422, 404], (
        f"Unexpected status code {response.status_code} for payload: {payload}"
    )


# Cognito Router Tests


@pytest.mark.parametrize("payload", sql_injection_payloads + xss_payloads)
def test_cognito_signup_injection(payload):
    user_data = {
        "nickname": payload,
        "email": "test@example.com",
        "address": "123 Main St",
        "birthdate": "2000-01-01",
        "gender": "other",
        "picture": "http://example.com/pic.jpg",
        "phone_number": "+1234567890",
        "family_name": payload,
        "name": payload,
        "password": "Password123!",
    }
    response = client.post("/cognito/auth/signup", json=user_data)
    assert response.status_code != 500
    assert payload not in response.text


@pytest.mark.parametrize("payload", sql_injection_payloads + xss_payloads)
def test_cognito_login_injection(payload):
    login_data = {"email": payload, "password": payload}
    response = client.post("/cognito/auth/login", json=login_data)
    assert response.status_code != 500
    assert payload not in response.text


@pytest.mark.parametrize("payload", sql_injection_payloads + xss_payloads)
def test_cognito_confirm_injection(payload):
    confirm_data = {"email": "test@example.com", "code": payload}
    response = client.post("/cognito/auth/confirm", json=confirm_data)
    assert response.status_code != 500
    assert payload not in response.text


# S3 Service Tests


@pytest.mark.parametrize("payload", ["../", "..%2F", "..%5C"])
def test_s3_path_traversal_upload(payload):
    response = client.post(f"/s3/upload?folder={payload}", files={"file": ("test.txt", b"test content")})
    assert response.status_code != 500
    # This is a basic check. A more robust check would verify that the file was not uploaded to an unintended location.
    # For now, we just check that the server doesn't crash.


@pytest.mark.parametrize("payload", ["../", "..%2F", "..%5C"])
def test_s3_path_traversal_list(payload):
    response = client.get(f"/s3/list?folder={payload}")
    assert response.status_code != 500


@pytest.mark.parametrize("payload", sql_injection_payloads + xss_payloads)
def test_s3_presign_setup_injection(payload):
    req_data = {"email": payload, "filename": payload, "content_type": "image/jpeg"}
    response = client.post("/s3/presign-setup", json=req_data)
    assert response.status_code != 500


@pytest.mark.parametrize("payload", ["../", "..%2F", "..%5C"])
def test_s3_path_traversal_download(payload):
    response = client.get(f"/s3/download/{payload}")
    assert response.status_code != 500


# Calendar Service Tests


@pytest.mark.parametrize("payload", sql_injection_payloads + xss_payloads)
def test_calendar_events_list_injection(payload):
    response = client.get(f"/calendar/events?tz={payload}")
    assert response.status_code != 500
    assert payload not in response.text


@pytest.mark.parametrize("payload", sql_injection_payloads + xss_payloads)
def test_calendar_events_create_injection(payload):
    event_data = {
        "summary": payload,
        "description": payload,
        "location": payload,
        "start": "2025-09-05T10:00:00",
        "end": "2025-09-05T11:00:00",
        "timezone": "UTC",
        "attendees": [payload],
    }
    response = client.post("/calendar/events", json=event_data)
    assert response.status_code != 500
    assert payload not in response.text


@pytest.mark.parametrize("payload", sql_injection_payloads + xss_payloads)
def test_calendar_events_update_injection(payload):
    response = client.patch(f"/calendar/events/{payload}", json={"summary": payload})
    assert response.status_code != 500
    assert payload not in response.text


@pytest.mark.parametrize("payload", sql_injection_payloads + xss_payloads)
def test_calendar_events_delete_injection(payload):
    response = client.delete(f"/calendar/events/{payload}")
    assert response.status_code != 500
    assert payload not in response.text
