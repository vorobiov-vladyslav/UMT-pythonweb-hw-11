def test_me_requires_token(anon_client):
    assert anon_client.get("/api/users/me").status_code == 401


def test_me_returns_current_user(client, test_user):
    r = client.get("/api/users/me")
    assert r.status_code == 200
    assert r.json()["email"] == test_user.email


def test_me_rate_limited_at_10_per_minute(client):
    codes = [client.get("/api/users/me").status_code for _ in range(12)]
    assert codes.count(200) == 10
    assert 429 in codes


def test_avatar_update_returns_cloudinary_url(client, monkeypatch):
    fake_url = "https://res.cloudinary.com/demo/image/upload/RestApp/tester.png"
    monkeypatch.setattr(
        "api.users.UploadFileService.upload_file",
        lambda self, file, username: fake_url,
    )
    r = client.patch(
        "/api/users/avatar",
        files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["avatar"] == fake_url


def test_avatar_requires_token(anon_client):
    r = anon_client.patch(
        "/api/users/avatar",
        files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
    )
    assert r.status_code == 401
