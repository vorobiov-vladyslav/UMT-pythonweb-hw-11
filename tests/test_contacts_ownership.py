from repository.users import UserRepository
from services.auth import create_access_token


def _other_user_headers(db_session, email="other@example.com", username="other"):
    user = UserRepository(db_session).create(username=username, email=email, hashed_password="x")
    user.confirmed = True
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


def _body(**overrides):
    base = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@x.com",
        "phone": "+1",
        "birthday": "1990-01-01",
        "additional_data": None,
    }
    base.update(overrides)
    return base


def test_other_user_cannot_read_update_or_delete(client, db_session):
    # `client` is authenticated as the default test_user (owner A).
    contact_id = client.post("/api/contacts", json=_body()).json()["id"]
    b_headers = _other_user_headers(db_session)

    assert client.get(f"/api/contacts/{contact_id}", headers=b_headers).status_code == 404
    assert (
        client.put(
            f"/api/contacts/{contact_id}", json=_body(first_name="X"), headers=b_headers
        ).status_code
        == 404
    )
    assert client.delete(f"/api/contacts/{contact_id}", headers=b_headers).status_code == 404


def test_list_returns_only_callers_contacts(client, db_session):
    client.post("/api/contacts", json=_body(email="a@x.com"))
    b_headers = _other_user_headers(db_session, email="b2@example.com", username="b2")

    # B sees none of A's contacts.
    assert client.get("/api/contacts", headers=b_headers).json() == []

    # B's own contact is visible only to B.
    client.post("/api/contacts", json=_body(email="b@x.com"), headers=b_headers)
    b_rows = client.get("/api/contacts", headers=b_headers).json()
    assert [r["email"] for r in b_rows] == ["b@x.com"]

    a_rows = client.get("/api/contacts").json()
    assert [r["email"] for r in a_rows] == ["a@x.com"]
