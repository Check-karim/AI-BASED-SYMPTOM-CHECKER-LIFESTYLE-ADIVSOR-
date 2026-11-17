import csv
import json
import secrets
from datetime import datetime, timedelta
from functools import wraps
from io import StringIO

import pymysql
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from db import close_db, execute, fetch_all, fetch_one, init_db, parse_json
from engines import (
    ACTIVITIES,
    AGE_GROUPS,
    DIETS,
    DURATIONS,
    GOALS,
    PREGNANCY,
    SEVERITIES,
    SLEEP,
    SYMPTOM_IDS,
    URGENCY_META,
    build_lifestyle,
    evaluate_symptoms,
    grouped_symptoms,
)
from validators import (
    account_errors,
    validate_bounded_text,
    validate_email,
    validate_emergency_number,
    validate_full_name,
    validate_new_password,
    validate_phone,
)

app = Flask(__name__)
app.config.from_object(Config)
app.teardown_appcontext(close_db)


def safe_next(value):
    if not value or not isinstance(value, str):
        return None
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return None
    return value


ROLE_LABELS = {
    "patient": "Patient",
    "professional": "Healthcare professional",
    "admin": "Administrator",
}

CONTENT_SLUGS = ("safety_notice", "disclaimer", "symptom_intro", "lifestyle_intro")

SETTING_DEFAULTS = {
    "registration_open": "1",
    "reviews_open": "1",
    "emergency_ambulance": "912",
    "emergency_general": "112",
}


def landing_for(user):
    if user["role"] == "admin":
        return url_for("admin_home")
    if user["role"] == "professional":
        return url_for("reviews")
    return url_for("dashboard")


def path_allowed(role, path):
    base = (path or "").split("?", 1)[0].rstrip("/") or "/"
    if role == "admin":
        return base == "/admin" or base.startswith("/admin/")
    if role == "professional":
        return base == "/reviews" or base.startswith("/reviews/")
    if role == "patient":
        return base in {
            "/dashboard",
            "/profile",
            "/checker",
            "/lifestyle",
            "/history",
            "/disclaimer",
        } or base.startswith("/checks/") or base.startswith("/lifestyle/")
    return False


def destination_for(user, next_url):
    path = safe_next(next_url)
    if path and path_allowed(user["role"], path):
        return path
    return landing_for(user)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


@app.before_request
def prepare_request():
    g.user = None
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    g.csrf = session["csrf"]
    if request.endpoint == "static":
        return None
    if request.method == "POST":
        provided = request.form.get("csrf_token", "")
        expected = session.get("csrf", "")
        if not provided or not expected or not secrets.compare_digest(provided, expected):
            abort(400)
    g.settings = dict(SETTING_DEFAULTS)
    try:
        user_id = session.get("user_id")
        if user_id:
            user = fetch_one(
                """
                SELECT id, full_name, username, email, phone, role, is_active, created_at
                FROM users WHERE id = %s
                """,
                (user_id,),
            )
            if user and user["is_active"]:
                g.user = user
            else:
                session.pop("user_id", None)
                if user and not user["is_active"]:
                    flash("This account has been disabled. Contact an administrator.", "error")
        g.settings = load_settings()
    except pymysql.MySQLError:
        return render_template("errors/db.html"), 503
    return None


def load_settings():
    found = dict(SETTING_DEFAULTS)
    for row in fetch_all("SELECT setting_key, setting_value FROM app_settings"):
        if row["setting_key"] in found:
            found[row["setting_key"]] = row["setting_value"]
    return found


def setting_on(key):
    return (getattr(g, "settings", {}) or {}).get(key) == "1"


@app.context_processor
def inject_globals():
    settings = getattr(g, "settings", None) or SETTING_DEFAULTS
    user = getattr(g, "user", None)
    return {
        "csrf_token": getattr(g, "csrf", ""),
        "urgency_meta": URGENCY_META,
        "current_year": datetime.now().year,
        "role_labels": ROLE_LABELS,
        "emergency_ambulance": settings.get("emergency_ambulance", "912"),
        "emergency_general": settings.get("emergency_general", "112"),
        "registration_open": settings.get("registration_open") == "1",
        "reviews_open": settings.get("reviews_open") == "1",
        "account_home": landing_for(user) if user else url_for("home"),
    }


@app.template_filter("when")
def format_when(value):
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y · %H:%M")
    return value or ""


def hydrate_check(row):
    if not row:
        return None
    row["symptom_ids"] = parse_json(row["symptoms"], [])
    row["guidance"] = parse_json(row["guidance"], {})
    return row


def hydrate_plan(row):
    if not row:
        return None
    row["advice"] = parse_json(row["advice"], {})
    return row


def unique_taken(field, value, ignore_id=None):
    if field not in {"username", "email", "phone"}:
        raise ValueError("Unexpected account field.")
    sql = f"SELECT id FROM users WHERE {field} = %s"
    params = [value]
    if ignore_id is not None:
        sql += " AND id <> %s"
        params.append(ignore_id)
    return fetch_one(sql, params) is not None


def start_session(user):
    session.clear()
    session["user_id"] = user["id"]
    session["csrf"] = secrets.token_hex(16)


def choice_error(value, options, message):
    allowed = {key for key, _label in options}
    if value not in allowed:
        return message
    return ""


def audit(action, detail="", user=None):
    actor = user or getattr(g, "user", None)
    execute(
        """
        INSERT INTO audit_logs (user_id, role, action, detail)
        VALUES (%s, %s, %s, %s)
        """,
        (
            actor["id"] if actor else None,
            (actor["role"] if actor else "guest")[:20],
            action[:80],
            (detail or "")[:500],
        ),
    )


def content_block(slug):
    return fetch_one(
        "SELECT slug, title, body, updated_at FROM content_blocks WHERE slug = %s",
        (slug,),
    )


def list_accounts(query):
    query = (query or "").strip()[:50]
    columns = """
        SELECT id, full_name, username, email, phone, role, is_active, created_at
        FROM users
    """
    if not query:
        return fetch_all(columns + " ORDER BY created_at DESC"), query
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{escaped}%"
    return (
        fetch_all(
            columns
            + """
            WHERE username LIKE %s ESCAPE '\\\\'
               OR full_name LIKE %s ESCAPE '\\\\'
               OR email LIKE %s ESCAPE '\\\\'
            ORDER BY created_at DESC
            """,
            (like, like, like),
        ),
        query,
    )


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/disclaimer")
def disclaimer():
    return render_template(
        "disclaimer.html",
        notice=content_block("safety_notice"),
        legal=content_block("disclaimer"),
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(landing_for(g.user))
    if not setting_on("registration_open"):
        if request.method == "POST":
            flash("Registration is closed.", "error")
        return render_template("register.html", errors={}, form={}, closed=True)
    errors = {}
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        errors, cleaned = account_errors(form)
        if not errors:
            if unique_taken("username", cleaned["username"]):
                errors["username"] = "That username is already taken."
            if unique_taken("email", cleaned["email"]):
                errors["email"] = "That email is already registered."
            if unique_taken("phone", cleaned["phone"]):
                errors["phone"] = "That phone number is already registered."
        if not errors:
            user_id = execute(
                """
                INSERT INTO users (full_name, username, email, phone, password_hash, role)
                VALUES (%s, %s, %s, %s, %s, 'patient')
                """,
                (
                    cleaned["full_name"],
                    cleaned["username"],
                    cleaned["email"],
                    cleaned["phone"],
                    generate_password_hash(cleaned["password"]),
                ),
            )
            user = fetch_one(
                """
                SELECT id, full_name, username, email, phone, role, is_active, created_at
                FROM users WHERE id = %s
                """,
                (user_id,),
            )
            start_session(user)
            audit("register", user["username"], user)
            flash("Account created. You are signed in.", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html", errors=errors, form=form, closed=False)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(landing_for(g.user))
    form = request.form if request.method == "POST" else {}
    next_url = safe_next(request.values.get("next"))
    if request.method == "POST":
        username = (form.get("username") or "").strip()
        password = form.get("password") or ""
        user = fetch_one("SELECT * FROM users WHERE username = %s", (username,))
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
        elif not user["is_active"]:
            flash("This account is disabled. Contact an administrator.", "error")
        else:
            start_session(user)
            audit("login", user["username"], user)
            flash("Welcome back.", "success")
            return redirect(destination_for(user, next_url))
    return render_template("login.html", form=form, next_url=next_url or "")


@app.route("/logout", methods=["POST"])
def logout():
    if g.user:
        audit("logout", g.user["username"])
    session.clear()
    flash("You have signed out.", "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
@roles_required("patient")
def dashboard():
    checks = [
        hydrate_check(row)
        for row in fetch_all(
            """
            SELECT * FROM symptom_checks
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 3
            """,
            (g.user["id"],),
        )
    ]
    plans = [
        hydrate_plan(row)
        for row in fetch_all(
            """
            SELECT * FROM lifestyle_plans
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 2
            """,
            (g.user["id"],),
        )
    ]
    counts = {
        "checks": int(
            fetch_one(
                "SELECT COUNT(*) AS total FROM symptom_checks WHERE user_id = %s",
                (g.user["id"],),
            )["total"]
        ),
        "plans": int(
            fetch_one(
                "SELECT COUNT(*) AS total FROM lifestyle_plans WHERE user_id = %s",
                (g.user["id"],),
            )["total"]
        ),
    }
    return render_template(
        "dashboard.html",
        checks=checks,
        plans=plans,
        counts=counts,
    )


@app.route("/history")
@roles_required("patient")
def history():
    checks = [
        hydrate_check(row)
        for row in fetch_all(
            "SELECT * FROM symptom_checks WHERE user_id = %s ORDER BY created_at DESC",
            (g.user["id"],),
        )
    ]
    return render_template("history.html", checks=checks)


@app.route("/profile", methods=["GET", "POST"])
@roles_required("patient")
def profile():
    errors = {}
    form = {
        "full_name": g.user["full_name"],
        "email": g.user["email"],
        "phone": g.user["phone"],
    }
    if request.method == "POST":
        form = request.form
        name_error, name = validate_full_name(form.get("full_name", ""))
        email_error, email = validate_email(form.get("email", ""))
        phone_error, phone = validate_phone(form.get("phone", ""))
        errors = {
            key: value
            for key, value in {
                "full_name": name_error,
                "email": email_error,
                "phone": phone_error,
            }.items()
            if value
        }
        password = form.get("password", "")
        confirm = form.get("confirm_password", "")
        current = form.get("current_password", "")
        if password or confirm:
            if not current:
                errors["current_password"] = "Enter your current password to set a new one."
            else:
                stored = fetch_one("SELECT password_hash FROM users WHERE id = %s", (g.user["id"],))
                if not stored or not check_password_hash(stored["password_hash"], current):
                    errors["current_password"] = "Current password is incorrect."
            password_error = validate_new_password(password, confirm)
            if password_error:
                errors["password"] = password_error
        if not errors:
            if unique_taken("email", email, g.user["id"]):
                errors["email"] = "That email is already registered."
            if unique_taken("phone", phone, g.user["id"]):
                errors["phone"] = "That phone number is already registered."
        if not errors:
            if password:
                execute(
                    """
                    UPDATE users
                    SET full_name = %s, email = %s, phone = %s, password_hash = %s
                    WHERE id = %s
                    """,
                    (name, email, phone, generate_password_hash(password), g.user["id"]),
                )
            else:
                execute(
                    "UPDATE users SET full_name = %s, email = %s, phone = %s WHERE id = %s",
                    (name, email, phone, g.user["id"]),
                )
            audit("profile_update", g.user["username"])
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("profile.html", errors=errors, form=form)


@app.route("/checker", methods=["GET", "POST"])
@roles_required("patient")
def checker():
    errors = {}
    form = request.form if request.method == "POST" else {}
    selected = form.getlist("symptoms") if request.method == "POST" else []
    if request.method == "POST":
        selected = []
        for symptom_id in form.getlist("symptoms"):
            if symptom_id in SYMPTOM_IDS and symptom_id not in selected:
                selected.append(symptom_id)
        if not selected:
            errors["symptoms"] = "Select at least one symptom."
        for key, options, message in (
            ("duration", DURATIONS, "Choose how long this has been going on."),
            ("severity", SEVERITIES, "Choose how much this is affecting you."),
            ("age_group", AGE_GROUPS, "Choose an age group."),
        ):
            message = choice_error(form.get(key, ""), options, message)
            if message:
                errors[key] = message
        pregnancy = form.get("pregnancy", "no")
        if form.get("age_group") == "under_12":
            pregnancy = "no"
        elif choice_error(pregnancy, PREGNANCY, "Choose an option."):
            errors["pregnancy"] = "Choose an option."
        notes = (form.get("notes") or "").strip()
        if len(notes) > 500:
            errors["notes"] = "Notes must be 500 characters or fewer."
        if form.get("acknowledge") != "yes":
            errors["acknowledge"] = "Confirm that you understand this is not a diagnosis."
        if not errors:
            result = evaluate_symptoms(
                selected,
                form.get("duration"),
                form.get("severity"),
                form.get("age_group"),
                pregnancy,
                notes,
                ambulance=g.settings.get("emergency_ambulance", "912"),
                general=g.settings.get("emergency_general", "112"),
            )
            check_id = execute(
                """
                INSERT INTO symptom_checks
                    (user_id, symptoms, duration, severity, age_group, pregnancy, notes,
                     urgency, title, summary, guidance)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    g.user["id"],
                    json.dumps(selected),
                    form.get("duration"),
                    form.get("severity"),
                    form.get("age_group"),
                    pregnancy,
                    notes or None,
                    result["urgency"],
                    result["title"],
                    result["summary"],
                    json.dumps(result["guidance"]),
                ),
            )
            audit("symptom_check", f"check {check_id} {result['urgency']}")
            return redirect(url_for("check_detail", check_id=check_id))
    return render_template(
        "checker.html",
        errors=errors,
        form=form,
        selected=selected,
        groups=grouped_symptoms(),
        durations=DURATIONS,
        severities=SEVERITIES,
        age_groups=AGE_GROUPS,
        pregnancy_options=PREGNANCY,
        intro=content_block("symptom_intro"),
    )


def patient_check(check_id):
    row = hydrate_check(
        fetch_one(
            "SELECT * FROM symptom_checks WHERE id = %s",
            (check_id,),
        )
    )
    if row is None:
        abort(404)
    if row["user_id"] != g.user["id"]:
        abort(403)
    return row


def review_for_check(check_id):
    return fetch_one(
        """
        SELECT r.notes, r.recommendation, r.updated_at, u.full_name AS professional_name
        FROM professional_reviews r
        JOIN users u ON u.id = r.professional_id
        WHERE r.check_id = %s
        """,
        (check_id,),
    )


@app.route("/checks/<int:check_id>")
@roles_required("patient")
def check_detail(check_id):
    row = patient_check(check_id)
    return render_template(
        "check_detail.html",
        check=row,
        review=review_for_check(check_id),
    )


@app.route("/checks/<int:check_id>/review-request", methods=["POST"])
@roles_required("patient")
def request_review(check_id):
    row = patient_check(check_id)
    if not setting_on("reviews_open"):
        flash("Professional review is turned off.", "error")
        return redirect(url_for("check_detail", check_id=check_id))
    if row["review_requested"]:
        flash("You already asked for a review of this check.", "info")
        return redirect(url_for("check_detail", check_id=check_id))
    execute(
        """
        UPDATE symptom_checks
        SET review_requested = 1, review_requested_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s
        """,
        (check_id, g.user["id"]),
    )
    audit("review_requested", f"check {check_id}")
    flash("You asked for a professional review. Only this check will be shared.", "success")
    return redirect(url_for("check_detail", check_id=check_id))


@app.route("/lifestyle", methods=["GET", "POST"])
@roles_required("patient")
def lifestyle():
    errors = {}
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        for key, options, message in (
            ("goal", GOALS, "Choose a focus."),
            ("activity", ACTIVITIES, "Choose an activity level."),
            ("diet", DIETS, "Choose the option closest to how you eat."),
            ("sleep_hours", SLEEP, "Choose a sleep range."),
        ):
            message = choice_error(form.get(key, ""), options, message)
            if message:
                errors[key] = message
        if not errors:
            advice = build_lifestyle(
                form.get("goal"),
                form.get("activity"),
                form.get("diet"),
                form.get("sleep_hours"),
            )
            plan_id = execute(
                """
                INSERT INTO lifestyle_plans
                    (user_id, goal, activity, diet, sleep_hours, headline, advice)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    g.user["id"],
                    form.get("goal"),
                    form.get("activity"),
                    form.get("diet"),
                    form.get("sleep_hours"),
                    advice["headline"],
                    json.dumps(advice),
                ),
            )
            audit("lifestyle_plan", f"plan {plan_id}")
            return redirect(url_for("lifestyle_detail", plan_id=plan_id))
    plans = [
        hydrate_plan(row)
        for row in fetch_all(
            "SELECT * FROM lifestyle_plans WHERE user_id = %s ORDER BY created_at DESC",
            (g.user["id"],),
        )
    ]
    return render_template(
        "lifestyle.html",
        errors=errors,
        form=form,
        goals=GOALS,
        activities=ACTIVITIES,
        diets=DIETS,
        sleep_options=SLEEP,
        plans=plans,
        intro=content_block("lifestyle_intro"),
    )


@app.route("/lifestyle/<int:plan_id>")
@roles_required("patient")
def lifestyle_detail(plan_id):
    row = hydrate_plan(
        fetch_one(
            "SELECT * FROM lifestyle_plans WHERE id = %s AND user_id = %s",
            (plan_id, g.user["id"]),
        )
    )
    if row is None:
        abort(404)
    return render_template("lifestyle_detail.html", plan=row)


def visible_submission(check_id):
    row = hydrate_check(
        fetch_one(
            """
            SELECT c.*, u.full_name, u.username
            FROM symptom_checks c
            JOIN users u ON u.id = c.user_id
            WHERE c.id = %s AND c.review_requested = 1
            """,
            (check_id,),
        )
    )
    if row is None:
        abort(404)
    review = fetch_one(
        "SELECT * FROM professional_reviews WHERE check_id = %s",
        (check_id,),
    )
    if review and review["professional_id"] != g.user["id"]:
        abort(404)
    return row, review


def save_review_field(check_id, field, text):
    if field not in {"notes", "recommendation"}:
        raise ValueError("Unexpected review field.")
    _row, review = visible_submission(check_id)
    if review is None:
        notes = text if field == "notes" else None
        recommendation = text if field == "recommendation" else None
        execute(
            """
            INSERT INTO professional_reviews (check_id, professional_id, notes, recommendation)
            VALUES (%s, %s, %s, %s)
            """,
            (check_id, g.user["id"], notes, recommendation),
        )
        return
    execute(
        f"UPDATE professional_reviews SET {field} = %s WHERE check_id = %s AND professional_id = %s",
        (text, check_id, g.user["id"]),
    )


@app.route("/reviews")
@roles_required("professional")
def reviews():
    urgency = request.args.get("urgency", "")
    if urgency not in URGENCY_META:
        urgency = ""
    sql = """
        SELECT c.*, u.full_name, u.username,
               r.id AS review_id, r.notes AS review_notes, r.recommendation AS review_recommendation
        FROM symptom_checks c
        JOIN users u ON u.id = c.user_id
        LEFT JOIN professional_reviews r ON r.check_id = c.id
        WHERE c.review_requested = 1
          AND (r.id IS NULL OR r.professional_id = %s)
    """
    params = [g.user["id"]]
    if urgency:
        sql += " AND c.urgency = %s"
        params.append(urgency)
    sql += " ORDER BY c.review_requested_at DESC, c.created_at DESC LIMIT 200"
    checks = [hydrate_check(row) for row in fetch_all(sql, params)]
    return render_template("reviews.html", checks=checks, urgency=urgency)


@app.route("/reviews/history")
@roles_required("professional")
def review_history():
    rows = []
    for row in fetch_all(
        """
        SELECT c.*, u.full_name, u.username,
               r.notes AS review_notes, r.recommendation AS review_recommendation,
               r.updated_at AS reviewed_at
        FROM professional_reviews r
        JOIN symptom_checks c ON c.id = r.check_id
        JOIN users u ON u.id = c.user_id
        WHERE r.professional_id = %s
        ORDER BY r.updated_at DESC
        """,
        (g.user["id"],),
    ):
        hydrated = hydrate_check(row)
        rows.append(hydrated)
    return render_template("review_history.html", checks=rows)


@app.route("/reviews/<int:check_id>")
@roles_required("professional")
def review_detail(check_id):
    row, review = visible_submission(check_id)
    return render_template("review_detail.html", check=row, review=review, errors={})


@app.route("/reviews/<int:check_id>/notes", methods=["POST"])
@roles_required("professional")
def review_notes(check_id):
    visible_submission(check_id)
    error, notes = validate_bounded_text(request.form.get("notes", ""), "Review notes", 10, 2000)
    if error:
        row, review = visible_submission(check_id)
        draft = dict(review or {})
        draft["notes"] = request.form.get("notes", "")
        return render_template(
            "review_detail.html",
            check=row,
            review=draft,
            errors={"notes": error},
        )
    save_review_field(check_id, "notes", notes)
    audit("review_notes", f"check {check_id}")
    flash("Review notes saved.", "success")
    return redirect(url_for("review_detail", check_id=check_id))


@app.route("/reviews/<int:check_id>/recommendation", methods=["POST"])
@roles_required("professional")
def review_recommendation(check_id):
    visible_submission(check_id)
    error, text = validate_bounded_text(
        request.form.get("recommendation", ""), "Follow-up recommendation", 10, 2000
    )
    if error:
        row, review = visible_submission(check_id)
        draft = dict(review or {})
        draft["recommendation"] = request.form.get("recommendation", "")
        return render_template(
            "review_detail.html",
            check=row,
            review=draft,
            errors={"recommendation": error},
        )
    save_review_field(check_id, "recommendation", text)
    audit("follow_up", f"check {check_id}")
    flash("Follow-up recommendation saved.", "success")
    return redirect(url_for("review_detail", check_id=check_id))


def _report_bundle():
    totals = {
        "users": int(fetch_one("SELECT COUNT(*) AS total FROM users")["total"]),
        "patients": int(
            fetch_one("SELECT COUNT(*) AS total FROM users WHERE role = 'patient'")["total"]
        ),
        "professionals": int(
            fetch_one("SELECT COUNT(*) AS total FROM users WHERE role = 'professional'")["total"]
        ),
        "checks": int(fetch_one("SELECT COUNT(*) AS total FROM symptom_checks")["total"]),
        "plans": int(fetch_one("SELECT COUNT(*) AS total FROM lifestyle_plans")["total"]),
        "review_requests": int(
            fetch_one(
                "SELECT COUNT(*) AS total FROM symptom_checks WHERE review_requested = 1"
            )["total"]
        ),
        "reviews_done": int(
            fetch_one("SELECT COUNT(*) AS total FROM professional_reviews")["total"]
        ),
    }
    urgency_rows = fetch_all(
        "SELECT urgency, COUNT(*) AS total FROM symptom_checks GROUP BY urgency"
    )
    by_urgency = {key: 0 for key in URGENCY_META}
    for row in urgency_rows:
        by_urgency[row["urgency"]] = int(row["total"])
    peak = max(by_urgency.values()) if any(by_urgency.values()) else 1
    urgency_stats = [
        {
            "key": key,
            "label": URGENCY_META[key]["label"],
            "tone": URGENCY_META[key]["tone"],
            "count": by_urgency[key],
            "pct": int(round((by_urgency[key] / peak) * 100)) if peak else 0,
        }
        for key in URGENCY_META
    ]
    start = datetime.now().date() - timedelta(days=6)
    daily_rows = fetch_all(
        """
        SELECT DATE(created_at) AS day, COUNT(*) AS total
        FROM symptom_checks
        WHERE created_at >= %s
        GROUP BY DATE(created_at)
        """,
        (start,),
    )
    daily_map = {}
    for row in daily_rows:
        day = row["day"]
        if isinstance(day, datetime):
            day = day.date()
        daily_map[str(day)] = int(row["total"])
    daily = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        daily.append(
            {
                "label": day.strftime("%d %b"),
                "day": day.isoformat(),
                "count": daily_map.get(str(day), 0),
            }
        )
    day_peak = max((item["count"] for item in daily), default=1) or 1
    for item in daily:
        item["pct"] = int(round((item["count"] / day_peak) * 100))
    return totals, urgency_stats, daily


@app.route("/admin")
@roles_required("admin")
def admin_home():
    totals, urgency_stats, daily = _report_bundle()
    activity = fetch_all(
        """
        SELECT a.created_at, a.role, a.action, a.detail, u.username
        FROM audit_logs a
        LEFT JOIN users u ON u.id = a.user_id
        ORDER BY a.created_at DESC
        LIMIT 8
        """
    )
    return render_template(
        "admin/overview.html",
        totals=totals,
        urgency_stats=urgency_stats,
        daily=daily,
        activity=activity,
        active="overview",
    )


@app.route("/admin/users", methods=["GET", "POST"])
@roles_required("admin")
def admin_users():
    errors = {}
    form = {}
    if request.method == "POST":
        form = request.form
        errors, cleaned = account_errors(form)
        role = form.get("role", "patient")
        if role not in ("patient", "professional"):
            errors["role"] = "Choose patient or healthcare professional."
        if not errors:
            if unique_taken("username", cleaned["username"]):
                errors["username"] = "That username is already taken."
            if unique_taken("email", cleaned["email"]):
                errors["email"] = "That email is already registered."
            if unique_taken("phone", cleaned["phone"]):
                errors["phone"] = "That phone number is already registered."
        if not errors:
            execute(
                """
                INSERT INTO users (full_name, username, email, phone, password_hash, role)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    cleaned["full_name"],
                    cleaned["username"],
                    cleaned["email"],
                    cleaned["phone"],
                    generate_password_hash(cleaned["password"]),
                    role,
                ),
            )
            audit("user_created", f"{cleaned['username']} {role}")
            flash("User account created.", "success")
            return redirect(url_for("admin_users"))
    users, query = list_accounts(request.args.get("q"))
    return render_template(
        "admin/users.html",
        users=users,
        errors=errors,
        form=form,
        query=query,
        active="users",
    )


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@roles_required("admin")
def admin_set_role(user_id):
    target = fetch_one("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
    if target is None:
        abort(404)
    if target["username"].lower() == "admin":
        flash("The primary administrator role cannot be changed.", "error")
        return redirect(url_for("admin_roles"))
    role = request.form.get("role", "")
    if role not in ("patient", "professional"):
        flash("Choose a valid role.", "error")
        return redirect(url_for("admin_roles"))
    if role != target["role"]:
        execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
        audit("role_changed", f"{target['username']} {target['role']} to {role}")
        flash("Role updated.", "success")
    return redirect(url_for("admin_roles"))


@app.route("/admin/users/<int:user_id>/status", methods=["POST"])
@roles_required("admin")
def admin_set_status(user_id):
    target = fetch_one("SELECT id, username, is_active FROM users WHERE id = %s", (user_id,))
    if target is None:
        abort(404)
    if target["username"].lower() == "admin":
        flash("The primary administrator account stays active.", "error")
        return redirect(url_for("admin_users"))
    new_status = 0 if target["is_active"] else 1
    execute("UPDATE users SET is_active = %s WHERE id = %s", (new_status, user_id))
    audit("account_status", f"{target['username']} {'enabled' if new_status else 'disabled'}")
    flash("Account status updated.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/password", methods=["POST"])
@roles_required("admin")
def admin_reset_password(user_id):
    target = fetch_one("SELECT id, username FROM users WHERE id = %s", (user_id,))
    if target is None:
        abort(404)
    error = validate_new_password(
        request.form.get("password", ""), request.form.get("confirm_password", "")
    )
    if error:
        flash(error, "error")
        return redirect(url_for("admin_users"))
    execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (generate_password_hash(request.form.get("password", "")), user_id),
    )
    audit("password_reset", target["username"])
    flash(f"Password updated for {target['username']}.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/roles")
@roles_required("admin")
def admin_roles():
    users, query = list_accounts(request.args.get("q"))
    return render_template("admin/roles.html", users=users, query=query, active="roles")


@app.route("/admin/guidance")
@roles_required("admin")
def admin_guidance():
    blocks = fetch_all(
        "SELECT slug, title, updated_at FROM content_blocks ORDER BY title"
    )
    return render_template("admin/guidance.html", blocks=blocks, active="guidance")


@app.route("/admin/guidance/<slug>", methods=["GET", "POST"])
@roles_required("admin")
def admin_guidance_edit(slug):
    if slug not in CONTENT_SLUGS:
        abort(404)
    block = content_block(slug)
    if block is None:
        abort(404)
    errors = {}
    if request.method == "POST":
        title_error, title = validate_bounded_text(request.form.get("title", ""), "Title", 3, 120)
        body_error, body = validate_bounded_text(request.form.get("body", ""), "Content", 20, 4000)
        errors = {key: value for key, value in {"title": title_error, "body": body_error}.items() if value}
        if not errors:
            execute(
                "UPDATE content_blocks SET title = %s, body = %s WHERE slug = %s",
                (title, body, slug),
            )
            audit("guidance_updated", slug)
            flash("Approved guidance content updated.", "success")
            return redirect(url_for("admin_guidance"))
        block = {"slug": slug, "title": request.form.get("title", ""), "body": request.form.get("body", "")}
    return render_template("admin/guidance_edit.html", block=block, errors=errors, active="guidance")


@app.route("/admin/audit")
@roles_required("admin")
def admin_audit():
    entries = fetch_all(
        """
        SELECT a.created_at, a.role, a.action, a.detail, u.username
        FROM audit_logs a
        LEFT JOIN users u ON u.id = a.user_id
        ORDER BY a.created_at DESC
        LIMIT 300
        """
    )
    return render_template("admin/audit.html", entries=entries, active="audit")


@app.route("/admin/settings", methods=["GET", "POST"])
@roles_required("admin")
def admin_settings():
    errors = {}
    current = dict(g.settings)
    if request.method == "POST":
        registration = "1" if request.form.get("registration_open") == "1" else "0"
        reviews = "1" if request.form.get("reviews_open") == "1" else "0"
        ambulance_error, ambulance = validate_emergency_number(
            request.form.get("emergency_ambulance", ""), "Ambulance number"
        )
        general_error, general = validate_emergency_number(
            request.form.get("emergency_general", ""), "Emergency number"
        )
        errors = {
            key: value
            for key, value in {
                "emergency_ambulance": ambulance_error,
                "emergency_general": general_error,
            }.items()
            if value
        }
        current = {
            "registration_open": registration,
            "reviews_open": reviews,
            "emergency_ambulance": request.form.get("emergency_ambulance", ""),
            "emergency_general": request.form.get("emergency_general", ""),
        }
        if not errors:
            for key, value in (
                ("registration_open", registration),
                ("reviews_open", reviews),
                ("emergency_ambulance", ambulance),
                ("emergency_general", general),
            ):
                execute(
                    """
                    INSERT INTO app_settings (setting_key, setting_value)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                    """,
                    (key, value),
                )
            g.settings = load_settings()
            audit("settings_updated", "registration, reviews, emergency numbers")
            flash("System settings saved.", "success")
            return redirect(url_for("admin_settings"))
    return render_template("admin/settings.html", settings=current, errors=errors, active="settings")


@app.route("/admin/reports")
@roles_required("admin")
def admin_reports():
    totals, urgency_stats, daily = _report_bundle()
    return render_template(
        "admin/reports.html",
        totals=totals,
        urgency_stats=urgency_stats,
        daily=daily,
        active="reports",
    )


@app.route("/admin/reports.csv")
@roles_required("admin")
def admin_reports_csv():
    totals, urgency_stats, daily = _report_bundle()
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric", "key", "value"])
    for key, value in totals.items():
        writer.writerow(["total", key, value])
    for row in urgency_stats:
        writer.writerow(["urgency", row["key"], row["count"]])
    for item in daily:
        writer.writerow(["checks_on_day", item["day"], item["count"]])
    audit("report_downloaded", "usage csv")
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage-report.csv"},
    )


@app.errorhandler(400)
def bad_request(_error):
    return render_template("errors/400.html"), 400


@app.errorhandler(403)
def forbidden(_error):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("errors/404.html"), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("errors/500.html"), 500


if __name__ == "__main__":
    try:
        init_db()
    except pymysql.MySQLError as exc:
        raise SystemExit(
            "Could not connect to MySQL/MariaDB. Start MySQL in XAMPP and check config.py.\n"
            f"{exc}"
        ) from exc
    print("KFH Symptom Checker at http://127.0.0.1:5000")
    print("Administrator username: admin   password: admin")
    app.run(host="127.0.0.1", port=5000, debug=True)
