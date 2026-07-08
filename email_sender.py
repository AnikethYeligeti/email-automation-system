"""
Real SMTP email delivery via Mailtrap (or any standard SMTP provider).

Mailtrap's sandbox inbox is used so real test/demo runs never reach live
inboxes -- ideal for a student project. Credentials are stored in the
`settings` table (configured from the /settings page in the UI) rather
than hardcoded, so nothing sensitive lives in source control.
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from models import get_setting


class SMTPNotConfigured(Exception):
    pass


def get_smtp_config(conn):
    host = get_setting(conn, "smtp_host")
    port = get_setting(conn, "smtp_port")
    username = get_setting(conn, "smtp_username")
    password = get_setting(conn, "smtp_password")
    from_email = get_setting(conn, "smtp_from_email")
    from_name = get_setting(conn, "smtp_from_name", "Mailflow")

    if not all([host, port, username, password, from_email]):
        return None
    return {
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "from_email": from_email,
        "from_name": from_name,
    }


def send_email(conn, to_email, subject, html_content):
    """
    Sends one real email over SMTP.
    Returns (success: bool, error_message: str|None)
    """
    config = get_smtp_config(conn)
    if not config:
        return False, "SMTP is not configured yet. Add your Mailtrap credentials in Settings."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config['from_name']} <{config['from_email']}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(config["host"], config["port"], timeout=10) as server:
            server.starttls(context=context)
            server.login(config["username"], config["password"])
            server.sendmail(config["from_email"], to_email, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)


def test_connection(conn):
    """Used by the Settings page 'Test connection' button."""
    config = get_smtp_config(conn)
    if not config:
        return False, "Please fill in all SMTP fields first."
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(config["host"], config["port"], timeout=10) as server:
            server.starttls(context=context)
            server.login(config["username"], config["password"])
        return True, "Connected and authenticated successfully."
    except Exception as e:
        return False, str(e)
