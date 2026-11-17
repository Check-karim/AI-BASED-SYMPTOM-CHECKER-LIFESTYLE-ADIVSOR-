# AI-Based Symptom Checker & Lifestyle Advisor

Case-study web app set at King Faisal Hospital Rwanda. It stores accounts, symptom checks, lifestyle plans, and contact messages in MySQL. Guidance comes from written safety rules. It is not a diagnosis and not the hospital’s live system.

## Run

1. Start MySQL in the XAMPP control panel.
2. From this folder:

```
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

3. Open http://127.0.0.1:5000

The database `kfh_symptom_checker` is created on startup, including the administrator account.

## Sign-in

| | |
|---|---|
| Username | `admin` |
| Password | `admin` |

Passwords created or changed in the app must be at least 6 characters. The built-in administrator is the predefined exception until that password is replaced.

## Account rules

- Name: letters and spaces only. No numbers or special characters.
- Username: no spaces, cannot start with a number or a special character, letters and numbers only.
- Email must be valid. Phone must be a Rwanda mobile number (072, 073, 078, 079) or an international number starting with `+`.

## Database settings

Defaults match a local XAMPP install: host `127.0.0.1`, port `3306`, user `root`, empty password. Override with `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE`.

`schema.sql` is the same structure the app creates itself.
