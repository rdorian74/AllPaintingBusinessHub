"""
Follow Up Manager - Database
Simple SQLite operations
"""
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from config import DATABASE_PATH

@contextmanager
def get_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_database():
    """Initialize database tables"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS estimates (
                id INTEGER PRIMARY KEY,
                estimate_code TEXT UNIQUE NOT NULL,
                estimate_date TEXT,
                gc_company TEXT,
                contact_name TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                project_name TEXT,
                project_address TEXT,
                scope_summary TEXT,
                total_amount REAL,
                status TEXT DEFAULT 'waiting',
                revision_number INTEGER DEFAULT 0,
                display_code TEXT,
                original_message_id TEXT,
                original_subject TEXT,
                last_contact_date TEXT,
                next_followup_date TEXT,
                followup_count INTEGER DEFAULT 0,
                stop_followup INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS communications (
                id INTEGER PRIMARY KEY,
                estimate_id INTEGER,
                email_id TEXT UNIQUE,
                conversation_id TEXT,
                direction TEXT,
                subject TEXT,
                body_text TEXT,
                body_preview TEXT,
                from_email TEXT,
                to_email TEXT,
                email_date TEXT,
                has_attachment INTEGER DEFAULT 0,
                is_followup INTEGER DEFAULT 0,
                followup_number INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (estimate_id) REFERENCES estimates(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS followups (
                id INTEGER PRIMARY KEY,
                estimate_id INTEGER,
                followup_number INTEGER,
                scheduled_date TEXT,
                draft_content TEXT,
                draft_subject TEXT,
                outlook_draft_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                sent_at TEXT,
                FOREIGN KEY (estimate_id) REFERENCES estimates(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Default settings
        defaults = [
            ("first_followup_days", "17"),
            ("subsequent_followup_days", "10"),
            ("daily_scan_enabled", "false"),
            ("daily_scan_time", "07:00"),
        ]
        for key, val in defaults:
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
        
        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_est_code ON estimates(estimate_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_est ON communications(estimate_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_conv ON communications(conversation_id)")

# === Settings ===

def get_setting(key, default=None):
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key, value):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

def get_all_settings():
    with get_connection() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT * FROM settings")}

# === Estimates ===

def create_estimate(data):
    with get_connection() as conn:
        data["created_at"] = datetime.now().isoformat()
        data["updated_at"] = datetime.now().isoformat()
        cols = ", ".join(data.keys())
        vals = ", ".join(["?" for _ in data])
        conn.execute(f"INSERT INTO estimates ({cols}) VALUES ({vals})", list(data.values()))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def get_estimate(estimate_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM estimates WHERE id=?", (estimate_id,)).fetchone()
        return dict(row) if row else None

def get_estimate_by_code(code):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM estimates WHERE estimate_code=?", (code,)).fetchone()
        return dict(row) if row else None

def get_all_estimates(status_filter=None):
    with get_connection() as conn:
        if status_filter and status_filter != "all":
            rows = conn.execute("SELECT * FROM estimates WHERE status=? ORDER BY next_followup_date", (status_filter,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM estimates ORDER BY next_followup_date").fetchall()
        return [dict(r) for r in rows]

def update_estimate(estimate_id, data):
    with get_connection() as conn:
        data["updated_at"] = datetime.now().isoformat()
        sets = ", ".join([f"{k}=?" for k in data.keys()])
        conn.execute(f"UPDATE estimates SET {sets} WHERE id=?", list(data.values()) + [estimate_id])

# === Communications ===

def create_communication(data):
    with get_connection() as conn:
        data["created_at"] = datetime.now().isoformat()
        cols = ", ".join(data.keys())
        vals = ", ".join(["?" for _ in data])
        conn.execute(f"INSERT OR IGNORE INTO communications ({cols}) VALUES ({vals})", list(data.values()))

def email_exists(email_id):
    with get_connection() as conn:
        return conn.execute("SELECT 1 FROM communications WHERE email_id=?", (email_id,)).fetchone() is not None

def get_communications_for_estimate(estimate_id):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM communications WHERE estimate_id=? ORDER BY email_date", (estimate_id,)).fetchall()
        return [dict(r) for r in rows]

# === Followups ===

def create_followup(data):
    with get_connection() as conn:
        data["created_at"] = datetime.now().isoformat()
        cols = ", ".join(data.keys())
        vals = ", ".join(["?" for _ in data])
        conn.execute(f"INSERT INTO followups ({cols}) VALUES ({vals})", list(data.values()))
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def get_followups_for_estimate(estimate_id):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM followups WHERE estimate_id=? ORDER BY followup_number", (estimate_id,)).fetchall()
        return [dict(r) for r in rows]

def update_followup(followup_id, data):
    with get_connection() as conn:
        sets = ", ".join([f"{k}=?" for k in data.keys()])
        conn.execute(f"UPDATE followups SET {sets} WHERE id=?", list(data.values()) + [followup_id])

# === Stats & Maintenance ===

def get_database_stats():
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM estimates").fetchone()[0]
        by_status = {}
        totals_by_status = {}
        
        # Count and sum by status
        for row in conn.execute("""
            SELECT status, COUNT(*) as cnt, COALESCE(SUM(total_amount), 0) as total_amount 
            FROM estimates GROUP BY status
        """):
            status = row["status"] or "waiting"
            by_status[status] = row["cnt"]
            totals_by_status[status] = row["total_amount"]
        
        draft_ready = conn.execute("SELECT COUNT(DISTINCT estimate_id) FROM followups WHERE status='draft_ready'").fetchone()[0]
        
        # Total amount overall
        total_amount = conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM estimates").fetchone()[0]
        
        return {
            "total_estimates": total, 
            "by_status": by_status, 
            "totals_by_status": totals_by_status,
            "total_amount": total_amount,
            "draft_ready": draft_ready
        }

def get_db_last_update():
    """Get last update time"""
    with get_connection() as conn:
        row = conn.execute("SELECT MAX(updated_at) as last FROM estimates").fetchone()
        return row["last"] if row else None

def delete_estimate(estimate_id):
    """Delete estimate and related records"""
    with get_connection() as conn:
        conn.execute("DELETE FROM communications WHERE estimate_id=?", (estimate_id,))
        conn.execute("DELETE FROM followups WHERE estimate_id=?", (estimate_id,))
        conn.execute("DELETE FROM estimates WHERE id=?", (estimate_id,))

def clear_database():
    with get_connection() as conn:
        conn.execute("DELETE FROM communications")
        conn.execute("DELETE FROM followups")
        conn.execute("DELETE FROM estimates")

def export_to_csv():
    """Export estimates to CSV - returns dict of {filename: content}"""
    import csv
    import io
    
    result = {}
    
    # Export estimates
    estimates = get_all_estimates()
    if estimates:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=estimates[0].keys())
        writer.writeheader()
        writer.writerows(estimates)
        result["estimates.csv"] = output.getvalue()
    
    # Export communications
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM communications ORDER BY email_date DESC").fetchall()
        if rows:
            comms = [dict(r) for r in rows]
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=comms[0].keys())
            writer.writeheader()
            writer.writerows(comms)
            result["communications.csv"] = output.getvalue()
    
    # Export followups
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM followups ORDER BY created_at DESC").fetchall()
        if rows:
            followups = [dict(r) for r in rows]
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=followups[0].keys())
            writer.writeheader()
            writer.writerows(followups)
            result["followups.csv"] = output.getvalue()
    
    return result

def export_to_sql():
    """Export as SQL statements"""
    estimates = get_all_estimates()
    statements = []
    
    for est in estimates:
        cols = ", ".join(est.keys())
        vals = ", ".join([f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" if v else "NULL" for v in est.values()])
        statements.append(f"INSERT INTO estimates ({cols}) VALUES ({vals});")
    
    return "\n".join(statements)
