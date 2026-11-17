"""Hits the real MariaDB once to prove the pages and rules work together."""

import re

from werkzeug.security import check_password_hash

from app import app
from db import execute, fetch_all, fetch_one, init_db


def token(html):
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf missing"
    return match.group(1)


def main():
    init_db()
    with app.app_context():
        execute("DELETE FROM users WHERE username IN (%s, %s)", ("alineuwase", "revpro"))
    client = app.test_client()
    for path in ("/about", "/services", "/contact", "/admin/messages"):
        assert client.get(path).status_code == 404, path
    pages = ["/", "/disclaimer", "/login", "/register"]
    for path in pages:
        response = client.get(path)
        assert response.status_code == 200, path

    bad = client.post(
        "/register",
        data={
            "csrf_token": token(client.get("/register").data.decode()),
            "full_name": "Jean2",
            "username": "1bad user",
            "email": "not-email",
            "phone": "0711234567",
            "password": "admin",
            "confirm_password": "admin",
        },
        follow_redirects=True,
    )
    text = bad.data.decode()
    assert "Name cannot contain numbers" in text
    assert "cannot contain spaces" in text or "cannot start with a number" in text
    assert "valid email" in text
    assert "valid phone" in text
    assert "at least 6" in text

    page = client.get("/register")
    created = client.post(
        "/register",
        data={
            "csrf_token": token(page.data.decode()),
            "full_name": "Aline Uwase",
            "username": "alineuwase",
            "email": "aline.uwase@example.com",
            "phone": "078 123 4567",
            "password": "secret1",
            "confirm_password": "secret1",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200, created.status_code
    assert b"Hello, Aline" in created.data

    checker = client.get("/checker")
    result = client.post(
        "/checker",
        data={
            "csrf_token": token(checker.data.decode()),
            "symptoms": ["cough", "sore_throat"],
            "duration": "under_24h",
            "severity": "mild",
            "age_group": "adult",
            "pregnancy": "no",
            "notes": "",
            "acknowledge": "yes",
        },
        follow_redirects=True,
    )
    assert result.status_code == 200
    assert b"Home care" in result.data or b"home care" in result.data.lower()

    chest = client.get("/checker")
    emergency = client.post(
        "/checker",
        data={
            "csrf_token": token(chest.data.decode()),
            "symptoms": "chest",
            "duration": "under_24h",
            "severity": "severe",
            "age_group": "adult",
            "pregnancy": "no",
            "acknowledge": "yes",
        },
        follow_redirects=True,
    )
    assert b"emergency" in emergency.data.lower()

    plan_page = client.get("/lifestyle")
    plan = client.post(
        "/lifestyle",
        data={
            "csrf_token": token(plan_page.data.decode()),
            "goal": "sleep",
            "activity": "light",
            "diet": "mixed",
            "sleep_hours": "5_6",
        },
        follow_redirects=True,
    )
    assert plan.status_code == 200
    assert b"sleep" in plan.data.lower()

    with app.app_context():
        patient = fetch_one("SELECT id FROM users WHERE username = %s", ("alineuwase",))
        own_checks = [
            row["id"]
            for row in fetch_all(
                "SELECT id FROM symptom_checks WHERE user_id = %s ORDER BY id",
                (patient["id"],),
            )
        ]
    assert len(own_checks) >= 2
    private_id, shared_id = own_checks[0], own_checks[1]
    detail = client.get(f"/checks/{shared_id}")
    requested = client.post(
        f"/checks/{shared_id}/review-request",
        data={"csrf_token": token(detail.data.decode())},
        follow_redirects=True,
    )
    assert b"asked for a professional review" in requested.data
    for blocked in ("/reviews", "/admin", "/admin/users", "/admin/reports"):
        assert client.get(blocked).status_code == 403, blocked

    client.post("/logout", data={"csrf_token": token(client.get("/dashboard").data.decode())})

    login = client.get("/login")
    admin = client.post(
        "/login",
        data={"csrf_token": token(login.data.decode()), "username": "admin", "password": "admin"},
        follow_redirects=True,
    )
    assert admin.status_code == 200
    assert b"Desk" in admin.data
    for path in (
        "/admin/users",
        "/admin/roles",
        "/admin/guidance",
        "/admin/audit",
        "/admin/reports",
        "/admin/settings",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
    for path in ("/checker", "/lifestyle", "/profile", "/history", "/dashboard", "/reviews", f"/checks/{shared_id}"):
        assert client.get(path).status_code == 403, path

    short = client.post(
        "/admin/users",
        data={
            "csrf_token": token(client.get("/admin/users").data.decode()),
            "full_name": "Nurse One",
            "username": "nurse1",
            "email": "nurse1@example.com",
            "phone": "0721234567",
            "password": "short",
            "confirm_password": "short",
            "role": "professional",
        },
        follow_redirects=True,
    )
    assert b"at least 6" in short.data

    made = client.post(
        "/admin/users",
        data={
            "csrf_token": token(client.get("/admin/users").data.decode()),
            "full_name": "Review Pro",
            "username": "revpro",
            "email": "revpro@example.com",
            "phone": "0731112233",
            "password": "secret1",
            "confirm_password": "secret1",
            "role": "professional",
        },
        follow_redirects=True,
    )
    assert b"User account created" in made.data
    client.post("/logout", data={"csrf_token": token(client.get("/admin").data.decode())})

    professional = client.post(
        "/login",
        data={
            "csrf_token": token(client.get("/login").data.decode()),
            "username": "revpro",
            "password": "secret1",
        },
        follow_redirects=True,
    )
    assert professional.status_code == 200
    assert b"Assigned and consented" in professional.data
    assert client.get(f"/reviews/{private_id}").status_code == 404
    opened = client.get(f"/reviews/{shared_id}")
    assert opened.status_code == 200
    noted = client.post(
        f"/reviews/{shared_id}/notes",
        data={
            "csrf_token": token(opened.data.decode()),
            "notes": "Summary reviewed. No extra detail beyond the submitted symptoms.",
        },
        follow_redirects=True,
    )
    assert b"Review notes saved" in noted.data
    followed = client.post(
        f"/reviews/{shared_id}/recommendation",
        data={
            "csrf_token": token(noted.data.decode()),
            "recommendation": "Arrange an in-person exam today and do not wait on this application.",
        },
        follow_redirects=True,
    )
    assert b"Follow-up recommendation saved" in followed.data
    history = client.get("/reviews/history")
    assert b"Summary reviewed" in history.data
    for path in ("/checker", "/lifestyle", "/dashboard", "/admin", "/profile"):
        assert client.get(path).status_code == 403, path

    with app.app_context():
        stored = fetch_one("SELECT phone, password_hash FROM users WHERE username = %s", ("admin",))
        assert stored["phone"] == "+250780000000"
        assert check_password_hash(stored["password_hash"], "admin")
        execute("DELETE FROM users WHERE username IN (%s, %s)", ("alineuwase", "revpro"))
    print("smoke ok")


if __name__ == "__main__":
    main()
