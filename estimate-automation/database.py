"""
Database - SQLite database for tracking processed estimates
WITH CLIENT AND PROJECT FIELDS
"""
import sqlite3
from datetime import datetime
import config


class Database:
    """SQLite database for estimate history"""
    
    def __init__(self):
        self.db_path = config.DATABASE_PATH
        self._init_db()
    
    def _get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def _init_db(self):
        """Initialize database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create estimates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS estimates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estimate_code TEXT NOT NULL,
                email_id TEXT,
                email_subject TEXT,
                email_received_at TEXT,
                word_file_path TEXT,
                pdf_file_path TEXT,
                draft_id TEXT,
                draft_to_email TEXT,
                draft_subject TEXT,
                invoice_number TEXT,
                invoice_path TEXT,
                client_name TEXT,
                project_name TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Check if columns exist, add them if not (for existing databases)
        cursor.execute("PRAGMA table_info(estimates)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'invoice_number' not in columns:
            cursor.execute("ALTER TABLE estimates ADD COLUMN invoice_number TEXT")
        if 'invoice_path' not in columns:
            cursor.execute("ALTER TABLE estimates ADD COLUMN invoice_path TEXT")
        if 'client_name' not in columns:
            cursor.execute("ALTER TABLE estimates ADD COLUMN client_name TEXT")
        if 'project_name' not in columns:
            cursor.execute("ALTER TABLE estimates ADD COLUMN project_name TEXT")
        if 'qb_invoice_id' not in columns:
            cursor.execute("ALTER TABLE estimates ADD COLUMN qb_invoice_id TEXT")
        if 'qb_url' not in columns:
            cursor.execute("ALTER TABLE estimates ADD COLUMN qb_url TEXT")
        
        # Create processing log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estimate_id INTEGER,
                action TEXT,
                status TEXT,
                message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (estimate_id) REFERENCES estimates (id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_estimate(self, estimate_code, email_id=None, email_subject=None, email_received_at=None, 
                     client_name=None, project_name=None):
        """Add a new estimate to the database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO estimates (estimate_code, email_id, email_subject, email_received_at, 
                                   client_name, project_name, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (estimate_code, email_id, email_subject, email_received_at, client_name, project_name))
        
        estimate_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return estimate_id
    
    def update_estimate(self, estimate_id, **kwargs):
        """Update an estimate record"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Build update query
        set_parts = []
        values = []
        
        for key, value in kwargs.items():
            set_parts.append(f"{key} = ?")
            values.append(value)
        
        set_parts.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(estimate_id)
        
        query = f"UPDATE estimates SET {', '.join(set_parts)} WHERE id = ?"
        cursor.execute(query, values)
        
        conn.commit()
        conn.close()
    
    def delete_estimate(self, estimate_id):
        """Delete an estimate and its logs from the database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # First delete related logs
        cursor.execute("DELETE FROM processing_log WHERE estimate_id = ?", (estimate_id,))
        
        # Then delete the estimate
        cursor.execute("DELETE FROM estimates WHERE id = ?", (estimate_id,))
        
        conn.commit()
        conn.close()
        
        return True
    
    def add_log(self, estimate_id, action, status, message=None):
        """Add a processing log entry"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO processing_log (estimate_id, action, status, message)
            VALUES (?, ?, ?, ?)
        """, (estimate_id, action, status, message))
        
        conn.commit()
        conn.close()
    
    def get_estimate(self, estimate_id):
        """Get an estimate by ID"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM estimates WHERE id = ?", (estimate_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        return dict(row) if row else None
    
    def get_estimate_by_code(self, estimate_code):
        """Get the most recent estimate by code"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM estimates 
            WHERE estimate_code = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (estimate_code,))
        row = cursor.fetchone()
        
        conn.close()
        
        return dict(row) if row else None
    
    def get_recent_estimates(self, limit=50):
        """Get recent estimates"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM estimates 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_estimate_logs(self, estimate_id):
        """Get processing logs for an estimate"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM processing_log 
            WHERE estimate_id = ? 
            ORDER BY created_at ASC
        """, (estimate_id,))
        rows = cursor.fetchall()
        
        conn.close()
        
        return [dict(row) for row in rows]
    
    def is_email_processed(self, email_id):
        """Check if an email has already been processed"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM estimates WHERE email_id = ?", (email_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        return row is not None
    
    def get_statistics(self):
        """Get processing statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Total estimates
        cursor.execute("SELECT COUNT(*) FROM estimates")
        stats["total"] = cursor.fetchone()[0]
        
        # By status
        cursor.execute("""
            SELECT status, COUNT(*) 
            FROM estimates 
            GROUP BY status
        """)
        stats["by_status"] = dict(cursor.fetchall())
        
        # Today's estimates
        cursor.execute("""
            SELECT COUNT(*) FROM estimates 
            WHERE DATE(created_at) = DATE('now')
        """)
        stats["today"] = cursor.fetchone()[0]
        
        # Count invoiced
        cursor.execute("""
            SELECT COUNT(*) FROM estimates 
            WHERE invoice_number IS NOT NULL AND invoice_number != ''
        """)
        invoiced_count = cursor.fetchone()[0]
        if "by_status" not in stats:
            stats["by_status"] = {}
        stats["by_status"]["invoiced"] = invoiced_count
        
        conn.close()
        
        return stats


# Test the database if run directly
if __name__ == "__main__":
    print("Testing Database...")
    
    db = Database()
    
    # Add test estimate
    est_id = db.add_estimate(
        estimate_code="TEST-001",
        email_subject="Test Email",
        email_received_at=datetime.now().isoformat(),
        client_name="Test Client",
        project_name="Test Project"
    )
    print(f"Created estimate ID: {est_id}")
    
    # Update it
    db.update_estimate(est_id, status="completed", pdf_file_path="/test/path.pdf")
    
    # Add log
    db.add_log(est_id, "process", "success", "Test completed")
    
    # Get it back
    estimate = db.get_estimate(est_id)
    print(f"Retrieved estimate: {estimate}")
    
    # Get statistics
    stats = db.get_statistics()
    print(f"Statistics: {stats}")
    
    # Test delete
    db.delete_estimate(est_id)
    print(f"Deleted estimate {est_id}")
    
    # Verify deletion
    estimate = db.get_estimate(est_id)
    print(f"After delete: {estimate}")
