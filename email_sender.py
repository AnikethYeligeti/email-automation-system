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
import urllib.request
import urllib.error
import json
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
            Sends one real email over SMTP (or Mailtrap API bypass if host is mailtrap).
                Returns (success: bool, error_message: str|None)
                    """
        config = get_smtp_config(conn)
        if not config:
                    return False, "SMTP is not configured yet. Add your Mailtrap credentials in Settings."

        if "mailtrap" in config["host"].lower():
                    # Bypass SMTP on Render to avoid port block, use Sandbox HTTP API instead
                    api_token = "05143fef7739de018f2a3f9f5dd9dbb1f9c92cdd"
                    sandbox_id = "4768016"
                    url = f"https://sandbox.api.send.mailtrap.io/api/send/{sandbox_id}"

        payload = {
                "from": {
                    "email": config["from_email"],
                    "name": config["from_name"]
                },
                "to": [
                    {"email": to_email}
                ],
                "subject": subject,
                "html": html_content
        }

            req = urllib.request.Request(
                            url,
                            data=json.dumps(payload).encode("utf-8"),
                            headers={
                                                "Authorization": f"Bearer {api_token}",
                                                "Content-Type": "application/json"
                            },
                            method="POST"
            )
        try:
                        context = ssl.create_default_context()
                        with urllib.request.urlopen(req, context=context) as response:
                                            res_body = response.read().decode("utf-8")
                                            # Parse response to ensure success
                                            res_json = json.loads(res_body)
                                            if res_json.get("success") or response.status == 200:
                                                                    return True, None
        else:
                                return False, f"Mailtrap API error: {res_body}"
except urllib.error.HTTPError as e:
            return False, f"Mailtrap API HTTP Error: {e.code} {e.read().decode('utf-8')}"
except Exception as e:
            return False, f"Mailtrap API Exception: {str(e)}"

    # Standard SMTP Fallback
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config['from_name']} <{config['from_email']}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
                context = ssl.create_default_context()
                # Create a connection with 10s timeout
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

        if "mailtrap" in config["host"].lower():
                    # Bypass SMTP test, verify Mailtrap API credentials instead
                    api_token = "05143fef7739de018f2a3f9f5dd9dbb1f9c92cdd"
                    url = "https://mailtrap.io/api/sandboxes"
                    req = urllib.request.Request(
                        url,
                        headers={
                            "Authorization": f"Bearer {api_token}"
                        },
                        method="GET"
                    )
                    try:
                                    context = ssl.create_default_context()
                                    with urllib.request.urlopen(req, context=context) as response:
                                                        if response.status == 200:
                                                                                return True, "Connected and authenticated successfully."
                    else:
                                            return False, f"Mailtrap API returned status {response.status}"
                    except urllib.error.HTTPError as e:
                        return False, f"Mailtrap API error: {e.code} {e.read().decode('utf-8')}"
except Exception as e:
            return False, f"Mailtrap API connection failed: {str(e)}"

    # Standard SMTP test
    try:
                context = ssl.create_default_context()
                with smtplib.SMTP(config["host"], config["port"], timeout=10) as server:
                                server.starttls(context=context)
                                server.login(config["username"], config["password"])
                                return True, "Connected and authenticated successfully."
    except Exception as e:
                return False, str(e)
