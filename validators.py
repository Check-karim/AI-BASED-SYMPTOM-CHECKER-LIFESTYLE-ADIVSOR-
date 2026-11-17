import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
RWANDA_PHONE_RE = re.compile(r"^(?:\+250|250|0)7[2389]\d{7}$")
INTL_PHONE_RE = re.compile(r"^\+[1-9]\d{8,14}$")


def validate_full_name(raw):
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if not name:
        return "Enter your name.", ""
    if any(ch.isdigit() or (not ch.isalpha() and ch != " ") for ch in name):
        return "Name cannot contain numbers or special characters.", ""
    if len(name) < 2:
        return "Enter your full name using letters only.", ""
    if len(name) > 60:
        return "Name must be 60 characters or fewer.", ""
    return "", name


def validate_username(raw):
    username = raw or ""
    if not username.strip():
        return "Enter a username.", ""
    if any(ch.isspace() for ch in username):
        return "Username cannot contain spaces.", ""
    if username[0].isdigit():
        return "Username cannot start with a number.", ""
    if not username[0].isalpha():
        return "Username cannot start with a special character.", ""
    if len(username) < 3:
        return "Username must be at least 3 characters.", ""
    if len(username) > 20:
        return "Username must be 20 characters or fewer.", ""
    if any(not (ch.isalpha() or ch.isdigit()) for ch in username):
        return "Username can only contain letters and numbers.", ""
    if username.lower() == "admin":
        return "This username is reserved.", ""
    return "", username


def validate_email(raw):
    email = (raw or "").strip().lower()
    if not email:
        return "Enter an email address.", ""
    if (
        len(email) > 120
        or ".." in email
        or email.startswith(".")
        or "@." in email
        or not EMAIL_RE.fullmatch(email)
    ):
        return "Enter a valid email address.", ""
    return "", email


def normalize_phone(raw):
    return re.sub(r"[\s\-().]", "", (raw or "").strip())


def validate_phone(raw):
    phone = normalize_phone(raw)
    if not phone:
        return "Enter a phone number.", ""
    if RWANDA_PHONE_RE.fullmatch(phone):
        if phone.startswith("+"):
            canonical = phone
        elif phone.startswith("250"):
            canonical = f"+{phone}"
        else:
            canonical = f"+250{phone[1:]}"
        return "", canonical
    if INTL_PHONE_RE.fullmatch(phone):
        return "", phone
    return (
        "Enter a valid phone number: a Rwanda mobile number (072, 073, 078, or 079) or an international number starting with +.",
        "",
    )


def validate_new_password(password, confirm):
    password = password or ""
    confirm = confirm or ""
    if password.strip() == "" or len(password) < 6:
        return "Password must be at least 6 characters."
    if len(password) > 128:
        return "Password must be 128 characters or fewer."
    if password != confirm:
        return "Passwords do not match."
    return ""


def validate_subject(raw):
    subject = re.sub(r"\s+", " ", (raw or "").strip())
    if len(subject) < 3:
        return "Enter a subject of at least 3 characters.", ""
    if len(subject) > 120:
        return "Subject must be 120 characters or fewer.", ""
    if any(not (ch.isalnum() or ch in " .,:'-") for ch in subject):
        return "Subject can only contain letters, numbers, and basic punctuation.", ""
    return "", subject


def validate_message_body(raw):
    body = (raw or "").strip()
    if len(body) < 10:
        return "Message must be at least 10 characters.", ""
    if len(body) > 1000:
        return "Message must be 1000 characters or fewer.", ""
    return "", body


def account_errors(form, *, require_password=True):
    """Shared registration and admin-create checks. Returns errors, cleaned."""
    errors = {}
    cleaned = {}

    name_error, name = validate_full_name(form.get("full_name", ""))
    if name_error:
        errors["full_name"] = name_error
    else:
        cleaned["full_name"] = name

    user_error, username = validate_username(form.get("username", ""))
    if user_error:
        errors["username"] = user_error
    else:
        cleaned["username"] = username

    email_error, email = validate_email(form.get("email", ""))
    if email_error:
        errors["email"] = email_error
    else:
        cleaned["email"] = email

    phone_error, phone = validate_phone(form.get("phone", ""))
    if phone_error:
        errors["phone"] = phone_error
    else:
        cleaned["phone"] = phone

    if require_password:
        password_error = validate_new_password(
            form.get("password", ""), form.get("confirm_password", "")
        )
        if password_error:
            errors["password"] = password_error
        else:
            cleaned["password"] = form.get("password", "")

    return errors, cleaned
