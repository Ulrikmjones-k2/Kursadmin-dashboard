"""
Simple Audit Logging System
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import json
from typing import Dict, Any, Optional

class AuditLogger:
    """Simple audit logging system."""

    def __init__(self, db_connection_func):
        self.get_db_connection = db_connection_func
        self._ensure_audit_table_exists()

    def _ensure_audit_table_exists(self):
        """Create simple audit_log table."""
        create_table_sql = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='audit_log' AND xtype='U')
        BEGIN
            CREATE TABLE audit_log (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_name NVARCHAR(255),
                action NVARCHAR(100) NOT NULL,
                table_name NVARCHAR(100),
                record_id NVARCHAR(100),
                timestamp DATETIME2 DEFAULT GETDATE()
            );
        END
        """

        try:
            import app
            from sqlalchemy import text
            engine = app.get_engine()
            with engine.connect() as conn:
                conn.execute(text(create_table_sql))
                conn.commit()
        except Exception as e:
            print(f"⚠️ Could not create audit table: {e}")

    def log_action(self, action: str, table_name: str = None, record_id: str = None):
        """Log a simple action."""
        try:
            from auth import get_current_user
            current_user = get_current_user()

            # Safely get user name
            user_name = 'System'
            if current_user:
                user_name = current_user.get('displayName') or current_user.get('display_name') or current_user.get('name', 'Unknown User')

            audit_entry = {
                'user_name': user_name,
                'action': action,
                'table_name': table_name,
                'record_id': record_id,
                'timestamp': datetime.now()
            }

            import app
            engine = app.get_engine()
            df = pd.DataFrame([audit_entry])
            df.to_sql('audit_log', engine, if_exists='append', index=False)
        except Exception as e:
            print(f"❌ Audit logging failed: {e}")

# Global audit logger instance
audit_logger = None

def get_audit_logger():
    """Get the global audit logger instance."""
    global audit_logger
    if audit_logger is None:
        import app
        audit_logger = AuditLogger(app.get_engine)
    return audit_logger

# Simple convenience functions
def log_page_view(page_name: str, course_id: str = None):
    """Log page view."""
    logger = get_audit_logger()
    logger.log_action(f'view_{page_name}', 'coursedates', course_id)

def log_course_update(course_id: str, old_values: dict, new_values: dict):
    """Log course update."""
    logger = get_audit_logger()
    logger.log_action('update_course', 'coursedates', course_id)

def log_search_activity(search_term: str, results_count: int):
    """Log search activity."""
    logger = get_audit_logger()
    logger.log_action(f'search_{search_term}', 'coursedates')

def log_user_login(success: bool, user_id: str = None, error: str = None):
    """Log authentication events."""
    logger = get_audit_logger()
    action = 'login_success' if success else 'login_failure'
    logger.log_action(action, 'authentication')

def log_user_logout():
    """Log user logout."""
    logger = get_audit_logger()
    logger.log_action('logout', 'authentication')