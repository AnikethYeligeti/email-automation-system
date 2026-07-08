"""
Email Marketing Automation System
Digital Marketing Capstone Project

Module 1: Subscriber Management
Module 2: Email Campaign Creation
Module 3: Email Automation System
Module 4: Campaign Analytics Dashboard
Module 5: Report Generation
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_file
from models import get_db, init_db, now, get_setting, set_setting
import email_sender
import csv
import io
import random
import threading
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

init_db()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _simulate_send(conn, camp_id):
    """Core send routine shared by manual 'Send now' and the automation scheduler.
    Sends a real email via SMTP if Mailtrap/SMTP is configured in Settings;
    otherwise falls back to a simulated send so the app still works out of the box.
    Engagement (opens/clicks) is randomized either way, since real open/click
    tracking would require pixel + link-redirect infrastructure (out of the
    brief's scope)."""
    campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (camp_id,)).fetchone()
    if not campaign:
        return 0

    if campaign["group_id"]:
        subs = conn.execute(
            "SELECT * FROM subscribers WHERE group_id = ? AND status = 'active'",
            (campaign["group_id"],),
        ).fetchall()
    else:
        subs = conn.execute("SELECT * FROM subscribers WHERE status = 'active'").fetchall()

    smtp_configured = email_sender.get_smtp_config(conn) is not None

    for sub in subs:
        if smtp_configured:
            success, error = email_sender.send_email(conn, sub["email"], campaign["subject"], campaign["content"])
            delivery_status = "delivered" if success else "failed"
        else:
            delivery_status = "simulated"
            error = None

        opened = 1 if delivery_status != "failed" and random.random() < 0.45 else 0
        clicked = 1 if opened and random.random() < 0.35 else 0
        conn.execute("""
            INSERT INTO campaign_sends
                (campaign_id, subscriber_id, opened, opened_at, clicked, clicked_at, delivery_status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (camp_id, sub["id"], opened, now() if opened else None, clicked, now() if clicked else None,
              delivery_status, error))

    conn.execute("UPDATE campaigns SET status = 'sent', sent_at = ? WHERE id = ?", (now(), camp_id))
    conn.commit()
    return len(subs)


def _send_single(conn, camp_id, subscriber_id):
    """Send one campaign to one subscriber (used by the on-subscribe welcome automation)."""
    campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (camp_id,)).fetchone()
    sub = conn.execute("SELECT * FROM subscribers WHERE id = ?", (subscriber_id,)).fetchone()
    if not campaign or not sub:
        return

    smtp_configured = email_sender.get_smtp_config(conn) is not None
    if smtp_configured:
        success, error = email_sender.send_email(conn, sub["email"], campaign["subject"], campaign["content"])
        delivery_status = "delivered" if success else "failed"
    else:
        delivery_status = "simulated"
        error = None

    opened = 1 if delivery_status != "failed" and random.random() < 0.45 else 0
    clicked = 1 if opened and random.random() < 0.35 else 0
    conn.execute("""
        INSERT INTO campaign_sends
            (campaign_id, subscriber_id, opened, opened_at, clicked, clicked_at, delivery_status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (camp_id, subscriber_id, opened, now() if opened else None, clicked, now() if clicked else None,
          delivery_status, error))
    conn.commit()


# ---------------------------------------------------------------------------
# MODULE 3: Background automation scheduler
# ---------------------------------------------------------------------------
def scheduler_loop():
    """Runs in a background thread. Every 15s, auto-sends any campaign whose
    scheduled_time has passed and is still marked 'scheduled'."""
    while True:
        try:
            conn = get_db()
            due = conn.execute("""
                SELECT id, name FROM campaigns
                WHERE status = 'scheduled' AND scheduled_time <= ?
            """, (datetime.now().strftime("%Y-%m-%dT%H:%M"),)).fetchall()
            for c in due:
                count = _simulate_send(conn, c["id"])
                conn.execute(
                    "INSERT INTO automation_log (campaign_id, note) VALUES (?, ?)",
                    (c["id"], f"Auto-sent '{c['name']}' to {count} subscribers on schedule.")
                )
                conn.commit()
            conn.close()
        except Exception as e:
            print("Scheduler error:", e)
        time.sleep(15)


scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
scheduler_thread.start()


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    conn = get_db()
    stats = {
        "subscribers": conn.execute("SELECT COUNT(*) c FROM subscribers WHERE status='active'").fetchone()["c"],
        "campaigns": conn.execute("SELECT COUNT(*) c FROM campaigns").fetchone()["c"],
        "sent": conn.execute("SELECT COUNT(*) c FROM campaigns WHERE status='sent'").fetchone()["c"],
        "emails_sent": conn.execute("SELECT COUNT(*) c FROM campaign_sends").fetchone()["c"],
    }
    recent_campaigns = conn.execute(
        "SELECT * FROM campaigns ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    recent_automation = conn.execute(
        "SELECT * FROM automation_log ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return render_template("index.html", stats=stats, recent_campaigns=recent_campaigns,
                            recent_automation=recent_automation)


# ---------------------------------------------------------------------------
# MODULE 1: Subscriber Management
# ---------------------------------------------------------------------------
@app.route("/subscribers")
def subscribers():
    conn = get_db()
    group_filter = request.args.get("group", "")
    search = request.args.get("search", "")

    query = """
        SELECT s.*, g.name as group_name FROM subscribers s
        LEFT JOIN groups g ON s.group_id = g.id
        WHERE 1=1
    """
    params = []
    if group_filter:
        query += " AND g.name = ?"
        params.append(group_filter)
    if search:
        query += " AND (s.name LIKE ? OR s.email LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY s.created_at DESC"

    subs = conn.execute(query, params).fetchall()
    groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    conn.close()
    return render_template("subscribers.html", subscribers=subs, groups=groups,
                            group_filter=group_filter, search=search)


def _trigger_welcome_automation(conn, subscriber_id):
    """Module 3: if an active on_subscribe automation rule exists, send that
    campaign to the newly added subscriber immediately."""
    rule = conn.execute("""
        SELECT * FROM automation_rules WHERE trigger_type = 'on_subscribe' AND active = 1
        ORDER BY id DESC LIMIT 1
    """).fetchone()
    if rule:
        _send_single(conn, rule["campaign_id"], subscriber_id)
        conn.execute(
            "INSERT INTO automation_log (rule_id, campaign_id, note) VALUES (?, ?, ?)",
            (rule["id"], rule["campaign_id"], "Sent welcome email to new subscriber.")
        )
        conn.commit()


@app.route("/subscribers/add", methods=["POST"])
def add_subscriber():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    group_id = request.form.get("group_id") or None

    if not name or not email or "@" not in email:
        flash("Please provide a valid name and email.", "error")
        return redirect(url_for("subscribers"))

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO subscribers (name, email, group_id) VALUES (?, ?, ?)",
            (name, email, group_id),
        )
        conn.commit()
        _trigger_welcome_automation(conn, cur.lastrowid)
        flash(f"Subscriber {email} added.", "success")
    except Exception as e:
        if "UNIQUE" in str(e):
            flash(f"{email} is already subscribed.", "error")
        else:
            flash("Could not add subscriber.", "error")
    conn.close()
    return redirect(url_for("subscribers"))


@app.route("/subscribers/import", methods=["POST"])
def import_subscribers():
    """Bulk import subscribers from an uploaded CSV (columns: name,email)."""
    file = request.files.get("csv_file")
    group_id = request.form.get("group_id") or None
    if not file or file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("subscribers"))

    stream = io.StringIO(file.stream.read().decode("utf-8"))
    reader = csv.DictReader(stream)
    conn = get_db()
    added, skipped = 0, 0
    for row in reader:
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip().lower()
        if not name or not email or "@" not in email:
            skipped += 1
            continue
        try:
            conn.execute(
                "INSERT INTO subscribers (name, email, group_id) VALUES (?, ?, ?)",
                (name, email, group_id),
            )
            added += 1
        except Exception:
            skipped += 1
    conn.commit()
    conn.close()
    flash(f"Import complete: {added} added, {skipped} skipped.", "success")
    return redirect(url_for("subscribers"))


@app.route("/subscribers/<int:sub_id>/delete", methods=["POST"])
def delete_subscriber(sub_id):
    conn = get_db()
    conn.execute("DELETE FROM subscribers WHERE id = ?", (sub_id,))
    conn.commit()
    conn.close()
    flash("Subscriber removed.", "success")
    return redirect(url_for("subscribers"))


@app.route("/subscribers/<int:sub_id>/toggle", methods=["POST"])
def toggle_subscriber(sub_id):
    conn = get_db()
    sub = conn.execute("SELECT status FROM subscribers WHERE id = ?", (sub_id,)).fetchone()
    new_status = "unsubscribed" if sub["status"] == "active" else "active"
    conn.execute("UPDATE subscribers SET status = ? WHERE id = ?", (new_status, sub_id))
    conn.commit()
    conn.close()
    return redirect(url_for("subscribers"))


@app.route("/groups/add", methods=["POST"])
def add_group():
    name = request.form.get("name", "").strip()
    if name:
        conn = get_db()
        try:
            conn.execute("INSERT INTO groups (name) VALUES (?)", (name,))
            conn.commit()
            flash(f"Group '{name}' created.", "success")
        except Exception:
            flash("Group already exists.", "error")
        conn.close()
    return redirect(url_for("subscribers"))


# ---------------------------------------------------------------------------
# MODULE 2: Email Campaign Creation
# ---------------------------------------------------------------------------
@app.route("/campaigns")
def campaigns():
    conn = get_db()
    camps = conn.execute("""
        SELECT c.*, g.name as group_name,
        (SELECT COUNT(*) FROM campaign_sends WHERE campaign_id = c.id) as sent_count,
        (SELECT COUNT(*) FROM campaign_sends WHERE campaign_id = c.id AND delivery_status = 'failed') as failed_count,
        (SELECT COUNT(*) FROM campaign_sends WHERE campaign_id = c.id AND delivery_status = 'delivered') as delivered_count
        FROM campaigns c
        LEFT JOIN groups g ON c.group_id = g.id
        ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("campaigns.html", campaigns=camps)


@app.route("/campaigns/new", methods=["GET", "POST"])
def new_campaign():
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        subject = request.form.get("subject", "").strip()
        content = request.form.get("content", "").strip()
        campaign_type = request.form.get("campaign_type", "promotional")
        group_id = request.form.get("group_id") or None
        scheduled_time = request.form.get("scheduled_time") or None

        if not name or not subject or not content:
            flash("Name, subject and content are required.", "error")
        else:
            status = "scheduled" if scheduled_time else "draft"
            conn.execute("""
                INSERT INTO campaigns (name, subject, content, campaign_type, group_id, scheduled_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, subject, content, campaign_type, group_id, scheduled_time, status))
            conn.commit()
            flash(f"Campaign '{name}' created as {status}.", "success")
            conn.close()
            return redirect(url_for("campaigns"))

    groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    conn.close()
    return render_template("campaign_form.html", groups=groups, campaign=None)


@app.route("/campaigns/<int:camp_id>/send", methods=["POST"])
def send_campaign(camp_id):
    conn = get_db()
    campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (camp_id,)).fetchone()
    if not campaign:
        flash("Campaign not found.", "error")
        conn.close()
        return redirect(url_for("campaigns"))
    count = _simulate_send(conn, camp_id)
    failed = conn.execute(
        "SELECT COUNT(*) c FROM campaign_sends WHERE campaign_id = ? AND delivery_status = 'failed'",
        (camp_id,)
    ).fetchone()["c"]
    smtp_on = email_sender.get_smtp_config(conn) is not None
    conn.close()
    if smtp_on:
        if failed:
            flash(f"Sent to {count} subscribers via SMTP — {failed} failed to deliver (check Settings).", "error")
        else:
            flash(f"Delivered to {count} subscribers via real SMTP (Mailtrap).", "success")
    else:
        flash(f"Campaign sent to {count} subscribers (simulated — configure SMTP in Settings for real delivery).", "success")
    return redirect(url_for("campaigns"))


@app.route("/campaigns/<int:camp_id>/delete", methods=["POST"])
def delete_campaign(camp_id):
    conn = get_db()
    conn.execute("DELETE FROM campaign_sends WHERE campaign_id = ?", (camp_id,))
    conn.execute("DELETE FROM automation_rules WHERE campaign_id = ?", (camp_id,))
    conn.execute("DELETE FROM campaigns WHERE id = ?", (camp_id,))
    conn.commit()
    conn.close()
    flash("Campaign deleted.", "success")
    return redirect(url_for("campaigns"))


# ---------------------------------------------------------------------------
# MODULE 3: Automation rules page
# ---------------------------------------------------------------------------
@app.route("/automation", methods=["GET", "POST"])
def automation():
    conn = get_db()
    if request.method == "POST":
        campaign_id = request.form.get("campaign_id")
        if campaign_id:
            # Deactivate any existing on_subscribe rule, then add the new one
            conn.execute("UPDATE automation_rules SET active = 0 WHERE trigger_type = 'on_subscribe'")
            conn.execute(
                "INSERT INTO automation_rules (trigger_type, campaign_id, active) VALUES ('on_subscribe', ?, 1)",
                (campaign_id,)
            )
            conn.commit()
            flash("Welcome automation updated.", "success")
        return redirect(url_for("automation"))

    campaigns_list = conn.execute("SELECT id, name FROM campaigns ORDER BY name").fetchall()
    active_rule = conn.execute("""
        SELECT ar.*, c.name as campaign_name FROM automation_rules ar
        JOIN campaigns c ON ar.campaign_id = c.id
        WHERE ar.trigger_type = 'on_subscribe' AND ar.active = 1
        ORDER BY ar.id DESC LIMIT 1
    """).fetchone()
    scheduled = conn.execute("""
        SELECT * FROM campaigns WHERE status = 'scheduled' ORDER BY scheduled_time
    """).fetchall()
    log = conn.execute("SELECT * FROM automation_log ORDER BY created_at DESC LIMIT 20").fetchall()
    conn.close()
    return render_template("automation.html", campaigns=campaigns_list, active_rule=active_rule,
                            scheduled=scheduled, log=log)


@app.route("/automation/disable", methods=["POST"])
def disable_automation():
    conn = get_db()
    conn.execute("UPDATE automation_rules SET active = 0 WHERE trigger_type = 'on_subscribe'")
    conn.commit()
    conn.close()
    flash("Welcome automation disabled.", "success")
    return redirect(url_for("automation"))


# ---------------------------------------------------------------------------
# MODULE 4: Campaign Analytics Dashboard
# ---------------------------------------------------------------------------
@app.route("/dashboard")
def dashboard():
    conn = get_db()

    totals = conn.execute("""
        SELECT COUNT(*) as sends,
               SUM(opened) as opens,
               SUM(clicked) as clicks
        FROM campaign_sends
    """).fetchone()
    sends = totals["sends"] or 0
    opens = totals["opens"] or 0
    clicks = totals["clicks"] or 0
    open_rate = round((opens / sends * 100), 1) if sends else 0
    click_rate = round((clicks / sends * 100), 1) if sends else 0

    # Per-campaign performance
    per_campaign = conn.execute("""
        SELECT c.name,
               COUNT(cs.id) as sends,
               SUM(cs.opened) as opens,
               SUM(cs.clicked) as clicks
        FROM campaigns c
        LEFT JOIN campaign_sends cs ON cs.campaign_id = c.id
        WHERE c.status = 'sent'
        GROUP BY c.id
        ORDER BY c.sent_at DESC
        LIMIT 10
    """).fetchall()

    campaign_labels = [row["name"] for row in per_campaign]
    campaign_open_rates = [
        round((row["opens"] or 0) / row["sends"] * 100, 1) if row["sends"] else 0
        for row in per_campaign
    ]
    campaign_click_rates = [
        round((row["clicks"] or 0) / row["sends"] * 100, 1) if row["sends"] else 0
        for row in per_campaign
    ]

    # Subscriber growth over time (cumulative by day)
    growth_rows = conn.execute("""
        SELECT substr(created_at, 1, 10) as day, COUNT(*) as c
        FROM subscribers
        GROUP BY day
        ORDER BY day
    """).fetchall()
    growth_labels = [r["day"] for r in growth_rows]
    growth_daily = [r["c"] for r in growth_rows]
    growth_cumulative = []
    running = 0
    for c in growth_daily:
        running += c
        growth_cumulative.append(running)

    # Engagement trend over time (opens/clicks by day sent)
    trend_rows = conn.execute("""
        SELECT substr(sent_at, 1, 10) as day,
               SUM(opened) as opens,
               SUM(clicked) as clicks,
               COUNT(*) as sends
        FROM campaign_sends
        GROUP BY day
        ORDER BY day
    """).fetchall()
    trend_labels = [r["day"] for r in trend_rows]
    trend_open_rate = [round((r["opens"] or 0) / r["sends"] * 100, 1) if r["sends"] else 0 for r in trend_rows]
    trend_click_rate = [round((r["clicks"] or 0) / r["sends"] * 100, 1) if r["sends"] else 0 for r in trend_rows]

    conn.close()
    return render_template(
        "dashboard.html",
        sends=sends, opens=opens, clicks=clicks, open_rate=open_rate, click_rate=click_rate,
        campaign_labels=campaign_labels, campaign_open_rates=campaign_open_rates,
        campaign_click_rates=campaign_click_rates,
        growth_labels=growth_labels, growth_cumulative=growth_cumulative,
        trend_labels=trend_labels, trend_open_rate=trend_open_rate, trend_click_rate=trend_click_rate,
    )


# ---------------------------------------------------------------------------
# MODULE 5: Report Generation
# ---------------------------------------------------------------------------
@app.route("/reports")
def reports():
    conn = get_db()
    camps = conn.execute("""
        SELECT c.*, (SELECT COUNT(*) FROM campaign_sends WHERE campaign_id = c.id) as sends,
               (SELECT SUM(opened) FROM campaign_sends WHERE campaign_id = c.id) as opens,
               (SELECT SUM(clicked) FROM campaign_sends WHERE campaign_id = c.id) as clicks
        FROM campaigns c
        WHERE c.status = 'sent'
        ORDER BY c.sent_at DESC
    """).fetchall()
    conn.close()
    return render_template("reports.html", campaigns=camps)


@app.route("/reports/subscribers/csv")
def report_subscribers_csv():
    conn = get_db()
    subs = conn.execute("""
        SELECT s.name, s.email, g.name as group_name, s.status, s.created_at
        FROM subscribers s LEFT JOIN groups g ON s.group_id = g.id
        ORDER BY s.created_at DESC
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Group", "Status", "Joined"])
    for s in subs:
        writer.writerow([s["name"], s["email"], s["group_name"] or "", s["status"], s["created_at"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=subscriber_report.csv"}
    )


@app.route("/reports/campaigns/csv")
def report_campaigns_csv():
    conn = get_db()
    camps = conn.execute("""
        SELECT c.name, c.campaign_type, c.status, c.sent_at,
               (SELECT COUNT(*) FROM campaign_sends WHERE campaign_id = c.id) as sends,
               (SELECT SUM(opened) FROM campaign_sends WHERE campaign_id = c.id) as opens,
               (SELECT SUM(clicked) FROM campaign_sends WHERE campaign_id = c.id) as clicks
        FROM campaigns c ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Campaign", "Type", "Status", "Sent At", "Recipients", "Opens", "Clicks", "Open Rate %", "Click Rate %"])
    for c in camps:
        sends = c["sends"] or 0
        opens = c["opens"] or 0
        clicks = c["clicks"] or 0
        open_rate = round(opens / sends * 100, 1) if sends else 0
        click_rate = round(clicks / sends * 100, 1) if sends else 0
        writer.writerow([c["name"], c["campaign_type"], c["status"], c["sent_at"] or "",
                          sends, opens, clicks, open_rate, click_rate])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=campaign_report.csv"}
    )


@app.route("/reports/campaign/<int:camp_id>/pdf")
def report_campaign_pdf(camp_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    conn = get_db()
    c = conn.execute("SELECT * FROM campaigns WHERE id = ?", (camp_id,)).fetchone()
    if not c:
        conn.close()
        flash("Campaign not found.", "error")
        return redirect(url_for("reports"))

    sends_row = conn.execute("""
        SELECT COUNT(*) as sends, SUM(opened) as opens, SUM(clicked) as clicks
        FROM campaign_sends WHERE campaign_id = ?
    """, (camp_id,)).fetchone()
    sends = sends_row["sends"] or 0
    opens = sends_row["opens"] or 0
    clicks = sends_row["clicks"] or 0
    open_rate = round(opens / sends * 100, 1) if sends else 0
    click_rate = round(clicks / sends * 100, 1) if sends else 0
    conn.close()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=25 * mm, bottomMargin=25 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], textColor=colors.HexColor("#4F46E5"))

    elements = [
        Paragraph("Mailflow — Campaign Performance Report", title_style),
        Spacer(1, 6),
        Paragraph(f"Generated: {now()}", styles["Normal"]),
        Spacer(1, 16),
        Paragraph(f"Campaign: {c['name']}", styles["Heading2"]),
        Paragraph(f"Subject line: {c['subject']}", styles["Normal"]),
        Paragraph(f"Type: {c['campaign_type']} · Status: {c['status']}", styles["Normal"]),
        Paragraph(f"Sent at: {c['sent_at'] or 'N/A'}", styles["Normal"]),
        Spacer(1, 16),
    ]

    table_data = [
        ["Metric", "Value"],
        ["Recipients", str(sends)],
        ["Opens", str(opens)],
        ["Clicks", str(clicks)],
        ["Open Rate", f"{open_rate}%"],
        ["Click Rate", f"{click_rate}%"],
    ]
    table = Table(table_data, colWidths=[220, 220])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E4E7EF")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F6FA")]),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)

    doc.build(elements)
    buf.seek(0)
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in c["name"])
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                      download_name=f"campaign_report_{safe_name}.pdf")


# ---------------------------------------------------------------------------
# Settings: real SMTP (Mailtrap) configuration
# ---------------------------------------------------------------------------
@app.route("/settings", methods=["GET", "POST"])
def settings():
    conn = get_db()
    if request.method == "POST":
        set_setting(conn, "smtp_host", request.form.get("smtp_host", "").strip())
        set_setting(conn, "smtp_port", request.form.get("smtp_port", "").strip())
        set_setting(conn, "smtp_username", request.form.get("smtp_username", "").strip())
        # Only overwrite the password if a new one was actually entered
        new_password = request.form.get("smtp_password", "").strip()
        if new_password:
            set_setting(conn, "smtp_password", new_password)
        set_setting(conn, "smtp_from_email", request.form.get("smtp_from_email", "").strip())
        set_setting(conn, "smtp_from_name", request.form.get("smtp_from_name", "Mailflow").strip())
        conn.close()
        flash("SMTP settings saved.", "success")
        return redirect(url_for("settings"))

    current = {
        "smtp_host": get_setting(conn, "smtp_host", ""),
        "smtp_port": get_setting(conn, "smtp_port", "587"),
        "smtp_username": get_setting(conn, "smtp_username", ""),
        "smtp_from_email": get_setting(conn, "smtp_from_email", ""),
        "smtp_from_name": get_setting(conn, "smtp_from_name", "Mailflow"),
        "has_password": bool(get_setting(conn, "smtp_password", "")),
    }
    conn.close()
    return render_template("settings.html", s=current)


@app.route("/settings/test", methods=["POST"])
def settings_test():
    conn = get_db()
    ok, message = email_sender.test_connection(conn)
    conn.close()
    flash(message, "success" if ok else "error")
    return redirect(url_for("settings"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
