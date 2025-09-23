"""
Simple Session Management for Streamlit Authentication
"""

import streamlit as st
import pandas as pd
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from streamlit_cookies_manager import EncryptedCookieManager

# Initialize cookies at module level
cookies = EncryptedCookieManager(
    prefix="kursadmin_",
    password="k2_course_dashboard_secret_2024"
)

if not cookies.ready():
    st.stop()

class SessionManager:
    """Simple session manager with HTTP cookies."""

    def __init__(self, db_connection_func):
        self.get_db_connection = db_connection_func
        self.cookie_name = 'session_id'
        self._ensure_session_table_exists()

    def _ensure_session_table_exists(self):
        """Create/recreate sessions table with correct structure."""
        # Drop and recreate table to fix schema issues
        recreate_table_sql = """
        -- Drop existing table if it has wrong schema
        IF EXISTS (SELECT * FROM sysobjects WHERE name='user_sessions' AND xtype='U')
        BEGIN
            DROP TABLE user_sessions;
        END

        -- Create new table with correct structure
        CREATE TABLE user_sessions (
            session_id NVARCHAR(255) PRIMARY KEY,
            user_id NVARCHAR(255) NULL,
            user_info NVARCHAR(MAX) NOT NULL,
            expires_at DATETIME2 NOT NULL,
            is_active BIT DEFAULT 1
        );
        """

        try:
            import app
            from sqlalchemy import text
            engine = app.get_engine()
            with engine.connect() as conn:
                conn.execute(text(recreate_table_sql))
                conn.commit()
                print("✅ Session table recreated with correct schema")
        except Exception as e:
            print(f"⚠️ Could not recreate session table: {e}")

    def create_session(self, user_info: Dict[str, Any]) -> str:
        """Create a new session."""
        try:
            session_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(hours=24)

            session_data = {
                'session_id': session_id,
                'user_id': user_info.get('id', 'unknown'),  # Add user_id field
                'user_info': json.dumps(user_info),
                'expires_at': expires_at,
                'is_active': True
            }

            import app
            engine = app.get_engine()
            df = pd.DataFrame([session_data])
            df.to_sql('user_sessions', engine, if_exists='append', index=False)

            return session_id
        except Exception as e:
            print(f"❌ Failed to create session: {e}")
            return None

    def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Validate session and return user info."""
        if not session_id:
            print(f"❌ Session validation: No session_id provided")
            return None

        try:
            print(f"🔍 Validating session: {session_id[:8]}... in database")
            import app
            from sqlalchemy import text
            engine = app.get_engine()

            query = """
            SELECT user_info, expires_at FROM user_sessions
            WHERE session_id = :session_id AND is_active = 1 AND expires_at > GETDATE()
            """

            with engine.connect() as conn:
                result = conn.execute(text(query), {"session_id": session_id})
                row = result.fetchone()

                if row:
                    user_info_json, expires_at = row
                    print(f"✅ Session found in database, expires: {expires_at}")
                    user_info = json.loads(user_info_json)
                    print(f"✅ Session valid for user: {user_info.get('displayName', 'Unknown')}")
                    return user_info
                else:
                    print(f"❌ No valid session found in database for: {session_id[:8]}...")
                    # Check if session exists at all with simpler query
                    check_query = "SELECT session_id, is_active, expires_at FROM user_sessions WHERE session_id = :session_id"
                    try:
                        check_result = conn.execute(text(check_query), {"session_id": session_id})
                        check_row = check_result.fetchone()
                        if check_row:
                            sid, is_active, expires = check_row
                            print(f"   Session exists: active={is_active}, expires={expires}")
                        else:
                            print(f"   Session does not exist in database")
                    except Exception as check_error:
                        print(f"   Could not check session existence: {check_error}")
                    return None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            import traceback
            print(f"   Full error: {traceback.format_exc()}")
            return None

    def set_session_cookie(self, session_id: str):
        """Set persistent cookie with session ID."""
        print(f"🍪 SETTING SESSION COOKIE: {session_id[:8]}... via cookie manager")

        # Set the cookie using dictionary-like syntax
        cookies[self.cookie_name] = session_id

        # Save immediately to ensure persistence
        cookies.save()

        st.session_state.current_session_id = session_id
        print(f"✅ Session cookie set: {session_id[:8]}...")

    def get_session_cookie(self) -> Optional[str]:
        """Get session ID from cookie."""
        print(f"🔍 GETTING SESSION COOKIE...")

        # Check session state first, but validate it
        session_id = st.session_state.get('current_session_id')
        if session_id:
            print(f"🔍 Found session in session state: {session_id[:8]}... - validating...")
            # Validate this session exists in database
            if self.validate_session(session_id):
                print(f"✅ Session state session is valid")
                return session_id
            else:
                print(f"❌ Session state session is invalid - clearing")
                del st.session_state['current_session_id']

        # Read from cookie manager
        cookie_value = cookies.get(self.cookie_name)
        if cookie_value:
            print(f"✅ Found session via cookie manager: {cookie_value[:8]}...")
            # Validate this session exists in database
            if self.validate_session(cookie_value):
                st.session_state.current_session_id = cookie_value
                return cookie_value
            else:
                print(f"❌ Cookie session is invalid - clearing")
                del cookies[self.cookie_name]

        print(f"❌ No valid session cookie found")
        return None


    def clear_session_cookie(self):
        """Clear session cookie."""
        # Clear from cookie manager
        if self.cookie_name in cookies:
            del cookies[self.cookie_name]
            print(f"✅ Session cookie cleared from cookie manager")

        # Clear session state
        keys_to_clear = ['current_session_id', 'authenticated', 'user_info', 'access_token', 'token_expiry', 'auth_timestamp']
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]

        print(f"✅ Session state cleared")

# Global session manager instance
session_manager = None

def get_session_manager():
    """Get the global session manager instance."""
    global session_manager
    if session_manager is None:
        import app
        session_manager = SessionManager(app.get_engine)
    return session_manager