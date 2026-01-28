"""
Database - SQLite database for Bid/Addendum Agent
All Painting Ltd.

Tables:
- bid_tracker: Master database of all bids (with addendum tracking)
- processing_log: Every email processed with status/reason
- gc_contacts: General contractor database (builds over time)
- settings: Agent settings (mode, etc.)
"""
import sqlite3
import json
from datetime import datetime, timedelta
import config


class Database:
    """SQLite database for bid tracking"""
    
    def __init__(self):
        self.db_path = config.DATABASE_PATH
        self._init_db()
    
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # =================================================================
        # BID TRACKER - Master database of all bids
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bid_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Project identification
                project_name TEXT,
                bid_reference_number TEXT,
                project_address TEXT,
                project_type TEXT,
                
                -- General Contractor info
                gc_company TEXT,
                gc_contact_name TEXT,
                gc_contact_email TEXT,
                gc_phone TEXT,
                
                -- Bid details
                bid_due_date TEXT,
                bid_due_time TEXT,
                bid_location TEXT,
                scope_of_work TEXT,
                
                -- Tracking
                original_bid_email_date TEXT,
                current_addendum INTEGER DEFAULT 0,
                addendum_dates TEXT,
                
                -- Status
                status TEXT DEFAULT 'open',
                
                -- Notes and metadata
                notes TEXT,
                source_email_ids TEXT,
                all_email_subjects TEXT,
                
                -- Duplicate detection
                match_confidence TEXT DEFAULT 'high',
                possible_duplicate_of INTEGER,
                
                -- Timestamps
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (possible_duplicate_of) REFERENCES bid_tracker (id)
            )
        """)
        
        # =================================================================
        # PROCESSING LOG - Every email processed
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Email info
                message_id TEXT UNIQUE,
                internet_message_id TEXT,
                subject TEXT,
                from_address TEXT,
                from_name TEXT,
                cc_addresses TEXT,
                received_at TEXT,
                body_preview TEXT,
                
                -- Processing results
                status TEXT,
                category TEXT,
                skip_reason TEXT,
                matched_keywords TEXT,
                
                -- Claude analysis
                claude_summary TEXT,
                claude_extracted_data TEXT,
                
                -- Bid tracker link
                bid_tracker_id INTEGER,
                
                -- Action taken
                action_taken TEXT,
                draft_id TEXT,
                
                -- Cost tracking
                cost_usd REAL DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                
                -- Timestamps
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (bid_tracker_id) REFERENCES bid_tracker (id)
            )
        """)
        
        # =================================================================
        # GC CONTACTS - General contractor database
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gc_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Company info
                company_name TEXT,
                email_domain TEXT UNIQUE,
                
                -- Contact info
                contact_name TEXT,
                contact_email TEXT,
                phone TEXT,
                
                -- Tracking
                first_seen_date TEXT,
                last_seen_date TEXT,
                bid_count INTEGER DEFAULT 1,
                
                -- Notes
                notes TEXT,
                
                -- Timestamps
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # =================================================================
        # SETTINGS - Agent settings
        # =================================================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Initialize default settings
        cursor.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('mode', 'draft')
        """)
        
        # Create indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_processing_log_internet_message_id 
            ON processing_log(internet_message_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_processing_log_from_subject 
            ON processing_log(from_address, subject)
        """)
        
        conn.commit()
        conn.close()
        
        print("✅ Database initialized")
    
    # =====================================================================
    # BID TRACKER OPERATIONS
    # =====================================================================
    
    def add_bid(self, project_name, gc_company, gc_contact_email, **kwargs):
        """Add a new bid to the tracker"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Build the insert query dynamically
        fields = ['project_name', 'gc_company', 'gc_contact_email']
        values = [project_name, gc_company, gc_contact_email]
        
        for key, value in kwargs.items():
            fields.append(key)
            if isinstance(value, (list, dict)):
                values.append(json.dumps(value))
            else:
                values.append(value)
        
        placeholders = ', '.join(['?' for _ in fields])
        field_names = ', '.join(fields)
        
        cursor.execute(f"""
            INSERT INTO bid_tracker ({field_names})
            VALUES ({placeholders})
        """, values)
        
        bid_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return bid_id
    
    def update_bid(self, bid_id, **kwargs):
        """Update a bid record"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        set_parts = []
        values = []
        
        for key, value in kwargs.items():
            set_parts.append(f"{key} = ?")
            if isinstance(value, (list, dict)):
                values.append(json.dumps(value))
            else:
                values.append(value)
        
        set_parts.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(bid_id)
        
        query = f"UPDATE bid_tracker SET {', '.join(set_parts)} WHERE id = ?"
        cursor.execute(query, values)
        
        conn.commit()
        conn.close()
    
    def get_bid(self, bid_id):
        """Get a bid by ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM bid_tracker WHERE id = ?", (bid_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            result = dict(row)
            # Parse JSON fields
            for field in ['addendum_dates', 'source_email_ids', 'all_email_subjects']:
                if result.get(field):
                    try:
                        result[field] = json.loads(result[field])
                    except:
                        pass
            return result
        return None
    
    def find_matching_bid(self, project_name=None, gc_company=None, bid_reference=None, 
                          bid_due_date=None, project_address=None):
        """
        Find a potentially matching bid for deduplication
        
        Returns: (bid_id, confidence) or (None, None)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Try exact match on bid reference number first
        if bid_reference:
            cursor.execute("""
                SELECT id FROM bid_tracker 
                WHERE bid_reference_number = ? AND status = 'open'
            """, (bid_reference,))
            row = cursor.fetchone()
            if row:
                conn.close()
                return row['id'], 'high'
        
        # Try matching on project name + GC company
        if project_name and gc_company:
            cursor.execute("""
                SELECT id, project_name, gc_company FROM bid_tracker 
                WHERE status = 'open'
            """)
            rows = cursor.fetchall()
            
            for row in rows:
                # Fuzzy match - check if significant words match
                existing_name = (row['project_name'] or '').lower()
                existing_gc = (row['gc_company'] or '').lower()
                new_name = project_name.lower()
                new_gc = gc_company.lower()
                
                # Check for substantial overlap
                name_words = set(new_name.split())
                existing_words = set(existing_name.split())
                common_words = name_words & existing_words
                
                gc_match = (new_gc in existing_gc) or (existing_gc in new_gc)
                name_match = len(common_words) >= 2 or (new_name in existing_name) or (existing_name in new_name)
                
                if gc_match and name_match:
                    conn.close()
                    return row['id'], 'high'
        
        # Try matching on GC company + bid due date
        if gc_company and bid_due_date:
            cursor.execute("""
                SELECT id FROM bid_tracker 
                WHERE gc_company LIKE ? AND bid_due_date = ? AND status = 'open'
            """, (f"%{gc_company}%", bid_due_date))
            row = cursor.fetchone()
            if row:
                conn.close()
                return row['id'], 'medium'
        
        conn.close()
        return None, None
    
    def increment_addendum(self, bid_id, addendum_date=None):
        """Increment addendum count and add date"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get current addendum info
        cursor.execute("SELECT current_addendum, addendum_dates FROM bid_tracker WHERE id = ?", (bid_id,))
        row = cursor.fetchone()
        
        if row:
            current = row['current_addendum'] or 0
            dates = json.loads(row['addendum_dates']) if row['addendum_dates'] else []
            
            new_addendum = current + 1
            if addendum_date:
                dates.append(addendum_date)
            
            cursor.execute("""
                UPDATE bid_tracker 
                SET current_addendum = ?, addendum_dates = ?, updated_at = ?
                WHERE id = ?
            """, (new_addendum, json.dumps(dates), datetime.now().isoformat(), bid_id))
            
            conn.commit()
        
        conn.close()
    
    def add_email_to_bid(self, bid_id, email_id, subject):
        """Add an email reference to a bid"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT source_email_ids, all_email_subjects FROM bid_tracker WHERE id = ?", (bid_id,))
        row = cursor.fetchone()
        
        if row:
            email_ids = json.loads(row['source_email_ids']) if row['source_email_ids'] else []
            subjects = json.loads(row['all_email_subjects']) if row['all_email_subjects'] else []
            
            if email_id not in email_ids:
                email_ids.append(email_id)
            if subject not in subjects:
                subjects.append(subject)
            
            cursor.execute("""
                UPDATE bid_tracker 
                SET source_email_ids = ?, all_email_subjects = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(email_ids), json.dumps(subjects), datetime.now().isoformat(), bid_id))
            
            conn.commit()
        
        conn.close()
    
    def get_open_bids(self, limit=100):
        """Get all open bids"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM bid_tracker 
            WHERE status = 'open'
            ORDER BY bid_due_date ASC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_recent_bids(self, limit=50):
        """Get recent bids"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM bid_tracker 
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        
        conn.close()
        
        return [dict(row) for row in rows]
    
    # =====================================================================
    # PROCESSING LOG OPERATIONS
    # =====================================================================
    
    def add_processing_log(self, message_id, subject, from_address, status, **kwargs):
        """Add a processing log entry"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check if already processed
        cursor.execute("SELECT id FROM processing_log WHERE message_id = ?", (message_id,))
        if cursor.fetchone():
            conn.close()
            return None  # Already processed
        
        fields = ['message_id', 'subject', 'from_address', 'status']
        values = [message_id, subject, from_address, status]
        
        for key, value in kwargs.items():
            fields.append(key)
            if isinstance(value, (list, dict)):
                values.append(json.dumps(value))
            else:
                values.append(value)
        
        placeholders = ', '.join(['?' for _ in fields])
        field_names = ', '.join(fields)
        
        cursor.execute(f"""
            INSERT INTO processing_log ({field_names})
            VALUES ({placeholders})
        """, values)
        
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return log_id
    
    def is_email_processed(self, message_id):
        """Check if an email has already been processed"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM processing_log WHERE message_id = ?", (message_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        return row is not None
    
    def is_email_processed_by_internet_id(self, internet_message_id):
        """
        Check if an email with this internet_message_id has been processed.
        This catches the same email being processed under different message_ids
        (e.g., when the email appears in different folders or is forwarded).
        """
        if not internet_message_id:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id FROM processing_log WHERE internet_message_id = ?", 
            (internet_message_id,)
        )
        row = cursor.fetchone()
        
        conn.close()
        
        return row is not None
    
    def get_processing_by_subject_and_sender(self, subject, from_address, hours_back=24):
        """
        Check if we've already processed an email with similar subject from same sender.
        Used for additional duplicate detection (same thread).
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Strip common prefixes for comparison
        clean_subject = subject
        for prefix in ['FW:', 'Fwd:', 'RE:', 'Re:', 'AW:', 'Aw:']:
            clean_subject = clean_subject.replace(prefix, '').strip()
        
        since = (datetime.now() - timedelta(hours=hours_back)).isoformat()
        
        cursor.execute("""
            SELECT id, status, category FROM processing_log 
            WHERE from_address = ? 
            AND created_at >= ?
            AND (subject LIKE ? OR subject LIKE ?)
        """, (from_address, since, f"%{clean_subject}%", f"{subject}"))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_processing_log(self, limit=100, status_filter=None):
        """Get processing log entries"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if status_filter:
            cursor.execute("""
                SELECT * FROM processing_log 
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (status_filter, limit))
        else:
            cursor.execute("""
                SELECT * FROM processing_log 
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # =====================================================================
    # GC CONTACTS OPERATIONS
    # =====================================================================
    
    def add_or_update_gc(self, email_domain, company_name=None, contact_name=None, 
                         contact_email=None, phone=None):
        """Add or update a GC contact"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute("SELECT id, bid_count FROM gc_contacts WHERE email_domain = ?", (email_domain,))
        row = cursor.fetchone()
        
        now = datetime.now().isoformat()
        
        if row:
            # Update existing
            bid_count = (row['bid_count'] or 0) + 1
            cursor.execute("""
                UPDATE gc_contacts 
                SET company_name = COALESCE(?, company_name),
                    contact_name = COALESCE(?, contact_name),
                    contact_email = COALESCE(?, contact_email),
                    phone = COALESCE(?, phone),
                    last_seen_date = ?,
                    bid_count = ?,
                    updated_at = ?
                WHERE email_domain = ?
            """, (company_name, contact_name, contact_email, phone, now, bid_count, now, email_domain))
            gc_id = row['id']
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO gc_contacts 
                (email_domain, company_name, contact_name, contact_email, phone, 
                 first_seen_date, last_seen_date, bid_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (email_domain, company_name, contact_name, contact_email, phone, now, now))
            gc_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return gc_id
    
    def get_gc_contacts(self, limit=100):
        """Get all GC contacts"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM gc_contacts 
            ORDER BY bid_count DESC, last_seen_date DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        
        conn.close()
        
        return [dict(row) for row in rows]
    
    def is_known_gc(self, email_domain):
        """Check if an email domain is a known GC"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM gc_contacts WHERE email_domain = ?", (email_domain,))
        row = cursor.fetchone()
        
        conn.close()
        
        return row is not None
    
    # =====================================================================
    # SETTINGS OPERATIONS
    # =====================================================================
    
    def get_setting(self, key, default=None):
        """Get a setting value"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        
        conn.close()
        
        return row['value'] if row else default
    
    def set_setting(self, key, value):
        """Set a setting value"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    # =====================================================================
    # STATISTICS
    # =====================================================================
    
    def get_statistics(self):
        """Get overall statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Total bids
        cursor.execute("SELECT COUNT(*) as total FROM bid_tracker")
        stats["total_bids"] = cursor.fetchone()["total"]
        
        # Open bids
        cursor.execute("SELECT COUNT(*) as open FROM bid_tracker WHERE status = 'open'")
        stats["open_bids"] = cursor.fetchone()["open"]
        
        # Total emails processed
        cursor.execute("SELECT COUNT(*) as total FROM processing_log")
        stats["total_emails_processed"] = cursor.fetchone()["total"]
        
        # Emails forwarded/drafted
        cursor.execute("SELECT COUNT(*) as forwarded FROM processing_log WHERE status = 'forwarded'")
        stats["emails_forwarded"] = cursor.fetchone()["forwarded"]
        
        cursor.execute("SELECT COUNT(*) as drafted FROM processing_log WHERE status = 'draft_created'")
        stats["drafts_created"] = cursor.fetchone()["drafted"]
        
        # Emails skipped
        cursor.execute("SELECT COUNT(*) as skipped FROM processing_log WHERE status = 'skipped'")
        stats["emails_skipped"] = cursor.fetchone()["skipped"]
        
        # GC contacts
        cursor.execute("SELECT COUNT(*) as total FROM gc_contacts")
        stats["gc_contacts"] = cursor.fetchone()["total"]
        
        # Today's activity
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT COUNT(*) as today FROM processing_log 
            WHERE DATE(created_at) = ?
        """, (today,))
        stats["emails_today"] = cursor.fetchone()["today"]
        
        # Total API cost
        cursor.execute("SELECT COALESCE(SUM(cost_usd), 0) as total_cost FROM processing_log")
        stats["total_cost"] = round(cursor.fetchone()["total_cost"], 4)
        
        conn.close()
        
        return stats
    
    def get_costs(self, period="today"):
        """Get cost summary for a period"""
        conn = self._get_connection()
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
                COALESCE(SUM(cost_usd), 0) as total_cost,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens
            FROM processing_log
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


# Test the database if run directly
if __name__ == "__main__":
    print("Testing Database...")
    
    db = Database()
    
    # Test adding a bid
    bid_id = db.add_bid(
        project_name="Test Library Renovation",
        gc_company="ABC Construction",
        gc_contact_email="bids@abc-construction.com",
        bid_due_date="2025-02-01",
        bid_due_time="2:00 PM"
    )
    print(f"Created bid ID: {bid_id}")
    
    # Test adding processing log
    log_id = db.add_processing_log(
        message_id="test-123",
        subject="Invitation to Bid - Library",
        from_address="bids@abc-construction.com",
        status="forwarded",
        category="new_bid"
    )
    print(f"Created log ID: {log_id}")
    
    # Test GC contact
    gc_id = db.add_or_update_gc(
        email_domain="abc-construction.com",
        company_name="ABC Construction Ltd.",
        contact_name="John Smith"
    )
    print(f"Created/updated GC ID: {gc_id}")
    
    # Get statistics
    stats = db.get_statistics()
    print(f"Statistics: {stats}")
