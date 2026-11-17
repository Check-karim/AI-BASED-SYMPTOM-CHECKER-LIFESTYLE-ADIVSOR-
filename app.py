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
    validate_email,
    validate_full_name,
    validate_message_body,
    validate_new_password,
    validate_phone,
    validate_subject,
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


def landing_for(user):
    if user["role"] == "admin":
        return url_for("admin_home")
    return url_for("dashboard")


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
    except pymysql.MySQLError:
        return render_template("errors/db.html"), 503
    return None


@app.context_processor
def inject_globals():
    unread = 0
    user = getattr(g, "user", None)
    if user and user["role"] == "admin":
        try:
            row = fetch_one("SELECT COUNT(*) AS total FROM messages WHERE is_read = 0")
            unread = int(row["total"]) if row else 0
        except pymysql.MySQLError:
            unread = 0
    return {
        "csrf_token": getattr(g, "csrf", ""),
        "unread_messages": unread,
        "urgency_meta": URGENCY_META,
        "current_year": datetime.now().year,
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


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/services")
def services():
    return render_template("services.html")


@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    form = request.form if request.method == "POST" else {}
    if request.method == "GET" and g.user:
        form = {
            "full_name": g.user["full_name"],
            "email": g.user["email"],
            "phone": g.user["phone"],
        }
    errors = {}
    if request.method == "POST":
        errors_name, name = validate_full_name(form.get("full_name", ""))
        errors_email, email = validate_email(form.get("email", ""))
        errors_phone, phone = validate_phone(form.get("phone", ""))
        errors_subject, subject = validate_subject(form.get("subject", ""))
        errors_body, body = validate_message_body(form.get("body", ""))
        errors = {
            key: value
            for key, value in {
                "full_name": errors_name,
                "email": errors_email,
                "phone": errors_phone,
                "subject": errors_subject,
                "body": errors_body,
            }.items()
            if value
        }
        if not errors:
            execute(
                """
                INSERT INTO messages (name, email, phone, subject, body)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (name, email, phone, subject, body),
            )
            flash("Message sent. An administrator can read it from the desk.", "success")
            return redirect(url_for("contact"))
    return render_template("contact.html", errors=errors, form=form)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(landing_for(g.user))
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
            flash("Account created. You are signed in.", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html", errors=errors, form=form)


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
            flash("Welcome back.", "success")
            return redirect(next_url or landing_for(user))
    return render_template("login.html", form=form, next_url=next_url or "")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have signed out.", "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
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
    review_count = 0
    if g.user["role"] == "professional":
        review_count = int(fetch_one("SELECT COUNT(*) AS total FROM symptom_checks")["total"])
    return render_template(
        "dashboard.html",
        checks=checks,
        plans=plans,
        counts=counts,
        review_count=review_count,
    )


@app.route("/history")
@login_required
def history():
    checks = [
        hydrate_check(row)
        for row in fetch_all(
            "SELECT * FROM symptom_checks WHERE user_id = %s ORDER BY created_at DESC",
            (g.user["id"],),
        )
    ]
    plans = [
        hydrate_plan(row)
        for row in fetch_all(
            "SELECT * FROM lifestyle_plans WHERE user_id = %s ORDER BY created_at DESC",
            (g.user["id"],),
        )
    ]
    return render_template("history.html", checks=checks, plans=plans)


@app.route("/profile", methods=["GET", "POST"])
@login_required
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
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("profile.html", errors=errors, form=form)


@app.route("/checker", methods=["GET", "POST"])
@login_required
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
    )


@app.route("/checks/<int:check_id>")
@login_required
def check_detail(check_id):
    row = hydrate_check(
        fetch_one(
            """
            SELECT c.*, u.full_name, u.username, u.email, u.phone
            FROM symptom_checks c
            JOIN users u ON u.id = c.user_id
            WHERE c.id = %s
            """,
            (check_id,),
        )
    )
    if row is None:
        abort(404)
    if g.user["role"] == "patient" and row["user_id"] != g.user["id"]:
        abort(403)
    return render_template("check_detail.html", check=row)


@app.route("/lifestyle", methods=["GET", "POST"])
@login_required
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
            return redirect(url_for("lifestyle_detail", plan_id=plan_id))
    return render_template(
        "lifestyle.html",
        errors=errors,
        form=form,
        goals=GOALS,
        activities=ACTIVITIES,
        diets=DIETS,
        sleep_options=SLEEP,
    )


@app.route("/lifestyle/<int:plan_id>")
@login_required
def lifestyle_detail(plan_id):
    row = hydrate_plan(
        fetch_one(
            """
            SELECT p.*, u.full_name, u.username
            FROM lifestyle_plans p
            JOIN users u ON u.id = p.user_id
            WHERE p.id = %s
            """,
            (plan_id,),
        )
    )
    if row is None:
        abort(404)
    if g.user["role"] != "admin" and row["user_id"] != g.user["id"]:
        abort(403)
    return render_template("lifestyle_detail.html", plan=row)


@app.route("/reviews")
@roles_required("professional", "admin")
def reviews():
    urgency = request.args.get("urgency", "")
    if urgency not in URGENCY_META:
        urgency = ""
    sql = """
        SELECT c.*, u.full_name, u.username
        FROM symptom_checks c
        JOIN users u ON u.id = c.user_id
    """
    params = []
    if urgency:
        sql += " WHERE c.urgency = %s"
        params.append(urgency)
    sql += " ORDER BY c.created_at DESC LIMIT 200"
    checks = [hydrate_check(row) for row in fetch_all(sql, params)]
    return render_template("reviews.html", checks=checks, urgency=urgency)


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
        "messages": int(fetch_one("SELECT COUNT(*) AS total FROM messages")["total"]),
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
        daily.append({"label": day.strftime("%d %b"), "count": daily_map.get(str(day), 0)})
    day_peak = max((item["count"] for item in daily), default=1) or 1
    for item in daily:
        item["pct"] = int(round((item["count"] / day_peak) * 100))
    recent = [
        hydrate_check(row)
        for row in fetch_all(
            """
            SELECT c.*, u.full_name, u.username
            FROM symptom_checks c
            JOIN users u ON u.id = c.user_id
            ORDER BY c.created_at DESC
            LIMIT 12
            """
        )
    ]
    return totals, urgency_stats, daily, recent


@app.route("/admin")
@roles_required("admin")
def admin_home():
    totals, urgency_stats, daily, recent = _report_bundle()
    newest_users = fetch_all(
        """
        SELECT full_name, username, role, created_at
        FROM users
        ORDER BY created_at DESC
        LIMIT 6
        """
    )
    return render_template(
        "admin/overview.html",
        totals=totals,
        urgency_stats=urgency_stats,
        daily=daily,
        recent=recent,
        newest_users=newest_users,
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
            flash("User account created.", "success")
            return redirect(url_for("admin_users"))
    query = (request.args.get("q") or "").strip()[:50]
    like = None
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        users = fetch_all(
            """
            SELECT id, full_name, username, email, phone, role, is_active, created_at
            FROM users
            WHERE username LIKE %s ESCAPE '\\\\'
               OR full_name LIKE %s ESCAPE '\\\\'
               OR email LIKE %s ESCAPE '\\\\'
            ORDER BY created_at DESC
            """,
            (like, like, like),
        )
    else:
        users = fetch_all(
            """
            SELECT id, full_name, username, email, phone, role, is_active, created_at
            FROM users
            ORDER BY created_at DESC
            """
        )
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
        return redirect(url_for("admin_users"))
    role = request.form.get("role", "")
    if role not in ("patient", "professional"):
        flash("Choose a valid role.", "error")
        return redirect(url_for("admin_users"))
    execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
    flash("Role updated.", "success")
    return redirect(url_for("admin_users"))


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
    flash(f"Password updated for {target['username']}.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/reports")
@roles_required("admin")
def admin_reports():
    totals, urgency_stats, daily, recent = _report_bundle()
    plans = fetch_all(
        """
        SELECT p.id, p.headline, p.created_at, u.full_name, u.username
        FROM lifestyle_plans p
        JOIN users u ON u.id = p.user_id
        ORDER BY p.created_at DESC
        LIMIT 12
        """
    )
    return render_template(
        "admin/reports.html",
        totals=totals,
        urgency_stats=urgency_stats,
        daily=daily,
        recent=recent,
        plans=plans,
        active="reports",
    )


@app.route("/admin/reports.csv")
@roles_required("admin")
def admin_reports_csv():
    rows = fetch_all(
        """
        SELECT c.created_at, u.full_name, u.username, c.urgency, c.title, c.summary, c.notes
        FROM symptom_checks c
        JOIN users u ON u.id = c.user_id
        ORDER BY c.created_at DESC
        """
    )
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["created_at", "full_name", "username", "urgency", "title", "summary", "notes"])
    for row in rows:
        writer.writerow(
            [
                row["created_at"].strftime("%Y-%m-%d %H:%M") if row["created_at"] else "",
                row["full_name"],
                row["username"],
                row["urgency"],
                row["title"],
                row["summary"],
                row["notes"] or "",
            ]
        )
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=symptom-checks.csv"},
    )


@app.route("/admin/messages")
@roles_required("admin")
def admin_messages():
    messages = fetch_all("SELECT * FROM messages ORDER BY created_at DESC")
    return render_template("admin/messages.html", messages=messages, active="messages")


@app.route("/admin/messages/<int:message_id>/read", methods=["POST"])
@roles_required("admin")
def admin_message_read(message_id):
    execute("UPDATE messages SET is_read = 1 WHERE id = %s", (message_id,))
    return redirect(url_for("admin_messages"))


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
