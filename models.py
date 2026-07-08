"""
Database layer for the Email Marketing Automation System.
Uses SQLite for simplicity/portability (swap-compatible with MySQL via SQLAlchemy later).
"""
import sqlite3
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        group_id INTEGER,
        status TEXT DEFAULT 'active',   -- active, unsubscribed
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id)
    );

    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        subject TEXT NOT NULL,
        content TEXT NOT NULL,
        campaign_type TEXT DEFAULT 'promotional', -- promotional, welcome, reminder
        group_id INTEGER,
        scheduled_time TEXT,
        status TEXT DEFAULT 'draft',   -- draft, scheduled, sent
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        sent_at TEXT,
        FOREIGN KEY (group_id) REFERENCES groups(id)
    );

    CREATE TABLE IF NOT EXISTS campaign_sends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        subscriber_id INTEGER NOT NULL,
        sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
        opened INTEGER DEFAULT 0,
        opened_at TEXT,
        clicked INTEGER DEFAULT 0,
        clicked_at TEXT,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
        FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
    );

    CREATE TABLE IF NOT EXISTS automation_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trigger_type TEXT NOT NULL,     -- on_subscribe
        campaign_id INTEGER NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
    );

    CREATE TABLE IF NOT EXISTS automation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id INTEGER,
        campaign_id INTEGER,
        note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()

    # Seed a couple of default groups if none exist
    cur.execute("SELECT COUNT(*) as c FROM groups")
    if cur.fetchone()["c"] == 0:
        for g in ["General", "Newsletter", "Customers", "Leads"]:
            cur.execute("INSERT INTO groups (name) VALUES (?)", (g,))
        conn.commit()

    conn.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
