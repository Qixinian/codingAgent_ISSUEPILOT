from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_register_accepts_valid_email() -> None:
    response = client.post(
        "/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "safe-password",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "username": "alice",
        "email": "alice@example.com",
        "status": "registered",
    }


def test_register_rejects_email_without_at_sign() -> None:
    response = client.post(
        "/register",
        json={
            "username": "alice",
            "email": "not-an-email",
            "password": "safe-password",
        },
    )

    assert response.status_code == 422


def test_register_rejects_email_without_domain() -> None:
    response = client.post(
        "/register",
        json={
            "username": "alice",
            "email": "alice@",
            "password": "safe-password",
        },
    )

    assert response.status_code == 422

