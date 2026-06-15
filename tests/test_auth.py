from repository.users import UserRepository
from services.auth import Hash, create_access_token, create_email_token


def _register(client, email="newuser@example.com", username="newuser", password="pass1234"):
    return client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def _confirm(client, email):
    token = create_email_token({"sub": email})
    return client.get(f"/api/auth/confirmed_email/{token}")


def test_register_returns_201_and_safe_body(anon_client):
    r = _register(anon_client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "newuser@example.com"
    assert body["confirmed"] is False
    assert "hashed_password" not in body
    assert "password" not in body


def test_register_duplicate_email_returns_409(anon_client):
    _register(anon_client)
    r = _register(anon_client, username="other")
    assert r.status_code == 409


def test_password_is_stored_hashed(anon_client, db_session):
    _register(anon_client, email="hash@example.com", username="hashuser")
    user = UserRepository(db_session).get_by_email("hash@example.com")
    assert user.hashed_password != "pass1234"
    assert Hash().verify_password("pass1234", user.hashed_password)


def test_login_unconfirmed_returns_401(anon_client):
    _register(anon_client)
    r = anon_client.post(
        "/api/auth/login",
        data={"username": "newuser@example.com", "password": "pass1234"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Email not confirmed"


def test_login_after_confirm_returns_token_pair(anon_client):
    _register(anon_client)
    _confirm(anon_client, "newuser@example.com")
    r = anon_client.post(
        "/api/auth/login",
        data={"username": "newuser@example.com", "password": "pass1234"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]


def test_login_wrong_password_returns_401(anon_client):
    _register(anon_client)
    _confirm(anon_client, "newuser@example.com")
    r = anon_client.post(
        "/api/auth/login",
        data={"username": "newuser@example.com", "password": "WRONG"},
    )
    assert r.status_code == 401


def test_confirm_flips_flag_and_is_idempotent(anon_client):
    _register(anon_client)
    assert _confirm(anon_client, "newuser@example.com").json() == {"message": "Email confirmed"}
    assert _confirm(anon_client, "newuser@example.com").json() == {
        "message": "Email already confirmed"
    }


def test_confirm_bad_token_returns_422(anon_client):
    r = anon_client.get("/api/auth/confirmed_email/not-a-valid-token")
    assert r.status_code == 422


def _login_tokens(client, email="newuser@example.com"):
    _register(client, email=email, username=email.split("@")[0])
    _confirm(client, email)
    return client.post("/api/auth/login", data={"username": email, "password": "pass1234"}).json()


def test_refresh_returns_new_pair(anon_client):
    tokens = _login_tokens(anon_client)
    r = anon_client.post("/api/auth/refresh_token", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    assert {"access_token", "refresh_token"} <= set(r.json())


def test_old_refresh_token_rejected_after_rotation(anon_client):
    tokens = _login_tokens(anon_client)
    old = tokens["refresh_token"]
    anon_client.post("/api/auth/refresh_token", json={"refresh_token": old})
    r = anon_client.post("/api/auth/refresh_token", json={"refresh_token": old})
    assert r.status_code == 401


def test_refresh_token_rejected_as_bearer(anon_client):
    tokens = _login_tokens(anon_client)
    headers = {"Authorization": f"Bearer {tokens['refresh_token']}"}
    r = anon_client.get("/api/users/me", headers=headers)
    assert r.status_code == 401


def test_access_token_with_unknown_user_rejected(anon_client):
    token = create_access_token({"sub": "ghost@example.com"})
    r = anon_client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
