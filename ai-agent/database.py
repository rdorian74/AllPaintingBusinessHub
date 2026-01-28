"""
Database module for AI Agent Service
Tracks validation history and costs
"""
import sqlite3
import json
from datetime import datetime, timedelta
import config


def get_connection():
    """Get a database connection"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database tables"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Validations table - stores each validation request
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS validations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            estimate_code TEXT NOT NULL,
            pdf_path TEXT,
            validation_passed BOOLEAN,
            issues TEXT,
            confidence_score INTEGER,
            action_taken TEXT,
            cost_usd REAL DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            processing_time_ms INTEGER,
            attempts INTEGER DEFAULT 1,
            auto_corrected BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Settings table - stores agent settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Initialize default settings if not exist
    cursor.execute("""
        INSERT OR IGNORE INTO settings (key, value) VALUES ('mode', 'review')
    """)
    
    # Check if we need to add new columns to existing table
    cursor.execute("PRAGMA table_info(validations)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'attempts' not in columns:
        cursor.execute("ALTER TABLE validations ADD COLUMN attempts INTEGER DEFAULT 1")
    
    if 'auto_corrected' not in columns:
        cursor.execute("ALTER TABLE validations ADD COLUMN auto_corrected BOOLEAN DEFAULT 0")
    
    conn.commit()
    conn.close()
    
    print("✅ Database initialized")


def add_validation(estimate_code, pdf_path, passed, issues, confidence_score, 
                   action_taken, cost_usd=0, input_tokens=0, output_tokens=0,
                   processing_time_ms=0, attempts=1, auto_corrected=False):
    """
    Add a validation record
    
    Args:
        estimate_code: The estimate code (e.g., 25C-319)
        pdf_path: Path to the PDF file
        passed: Whether validation passed
        issues: List of issues found (will be stored as JSON)
        confidence_score: Confidence score (0-100)
        action_taken: What action was taken (draft_created/email_sent/flagged)
        cost_usd: Estimated cost in USD
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens used
        processing_time_ms: Processing time in milliseconds
        attempts: Number of validation attempts
        auto_corrected: Whether the PDF was auto-corrected
    
    Returns:
        ID of the new record
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    issues_json = json.dumps(issues) if isinstance(issues, list) else issues
    
    cursor.execute("""
        INSERT INTO validations 
        (estimate_code, pdf_path, validation_passed, issues, confidence_score,
         action_taken, cost_usd, input_tokens, output_tokens, processing_time_ms,
         attempts, auto_corrected)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (estimate_code, pdf_path, passed, issues_json, confidence_score,
          action_taken, cost_usd, input_tokens, output_tokens, processing_time_ms,
          attempts, auto_corrected))
    
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return record_id


def get_validation_history(limit=50):
    """Get recent validation history"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM validations 
        ORDER BY created_at DESC 
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        record = dict(row)
        # Parse issues JSON
        if record.get("issues"):
            try:
                record["issues"] = json.loads(record["issues"])
            except:
                record["issues"] = [record["issues"]]
        result.append(record)
    
    return result


def get_costs(period="today"):
    """
    Get cost summary for a period
    
    Args:
        period: "today", "week", "month", or "total"
    
    Returns:
        Dictionary with cost info
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    now = datetime.now()
    
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:  # total
        start_date = datetime(2000, 1, 1)
    
    cursor.execute("""
        SELECT 
            COUNT(*) as count,
            SUM(cost_usd) as total_cost,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens
        FROM validations
        WHERE created_at >= ?
    """, (start_date.isoformat(),))
    
    row = cursor.fetchone()
    conn.close()
    
    return {
        "period": period,
        "count": row["count"] or 0,
        "total_cost": round(row["total_cost"] or 0, 4),
        "total_input_tokens": row["total_input_tokens"] or 0,
        "total_output_tokens": row["total_output_tokens"] or 0
    }


def get_stats():
    """Get overall statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Total validations
    cursor.execute("SELECT COUNT(*) as total FROM validations")
    total = cursor.fetchone()["total"]
    
    # Passed validations
    cursor.execute("SELECT COUNT(*) as passed FROM validations WHERE validation_passed = 1")
    passed = cursor.fetchone()["passed"]
    
    # Failed validations
    cursor.execute("SELECT COUNT(*) as failed FROM validations WHERE validation_passed = 0")
    failed = cursor.fetchone()["failed"]
    
    # Auto-corrected validations
    cursor.execute("SELECT COUNT(*) as auto_corrected FROM validations WHERE auto_corrected = 1")
    auto_corrected = cursor.fetchone()["auto_corrected"]
    
    # Today's count
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cursor.execute("""
        SELECT COUNT(*) as today_count FROM validations 
        WHERE created_at >= ?
    """, (today.isoformat(),))
    today_count = cursor.fetchone()["today_count"]
    
    # Average confidence score
    cursor.execute("SELECT AVG(confidence_score) as avg_confidence FROM validations")
    avg_confidence = cursor.fetchone()["avg_confidence"] or 0
    
    # Average attempts for failed validations
    cursor.execute("""
        SELECT AVG(attempts) as avg_attempts FROM validations 
        WHERE validation_passed = 1 AND attempts > 1
    """)
    avg_attempts = cursor.fetchone()["avg_attempts"] or 1
    
    conn.close()
    
    success_rate = (passed / total * 100) if total > 0 else 0
    
    return {
        "total_validations": total,
        "passed": passed,
        "failed": failed,
        "auto_corrected": auto_corrected,
        "success_rate": round(success_rate, 1),
        "today_count": today_count,
        "avg_confidence": round(avg_confidence, 1),
        "avg_attempts": round(avg_attempts, 1)
    }


def get_setting(key, default=None):
    """Get a setting value"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    
    return row["value"] if row else default


def set_setting(key, value):
    """Set a setting value"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (key, value))
    
    conn.commit()
    conn.close()


# Initialize database when module is imported
init_database()
