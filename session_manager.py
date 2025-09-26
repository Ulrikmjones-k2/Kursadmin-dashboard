"""
Simple Session Management for Streamlit Authentication with Cookie Fallback
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
    """Simple session manager with HTTP cookies and fallback authentication."""

    def __init__(self, db_connection_func):
        self.get_db_connection = db_connection_func
        self.cookie_name = 'session_id'
        self.user_info_cookie = 'user_info'  # NEW: Store user info in cookies too
        self._ensure_session_table_exists()

    def _ensure_session_table_exists(self):
        """Create/recreate sessions table with correct structure."""
        recreate_table_sql = """
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='user_sessions' AND xtype='U')
        BEGIN
            CREATE TABLE user_sessions (
                session_id NVARCHAR(255) PRIMARY KEY,
                user_id NVARCHAR(255) NULL,
                user_info NVARCHAR(MAX) NOT NULL,
                expires_at DATETIME2 NOT NULL,
                is_active BIT DEFAULT 1
            );
        END
        """

        try:
            import app
            from sqlalchemy import text
            engine = app.get_engine()
            with engine.connect() as conn:
                conn.execute(text(recreate_table_sql))
                conn.commit()
        except Exception as e:
            print(f"⚠️ Could not create session table: {e}")

    def create_session(self, user_info: Dict[str, Any]) -> str:
        """Create a new session with enhanced cookie storage."""
        try:
            session_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(hours=24)
            
            # Add expiration to user info for cookie storage
            enhanced_user_info = user_info.copy()
            enhanced_user_info['expires_at'] = expires_at.isoformat()

            # Try to store in database (don't fail if database is down)
            try:
                session_data = {
                    'session_id': session_id,
                    'user_id': user_info.get('id', 'unknown'),
                    'user_info': json.dumps(enhanced_user_info),
                    'expires_at': expires_at,
                    'is_active': True
                }
                import app
                engine = app.get_engine()
                df = pd.DataFrame([session_data])
                df.to_sql('user_sessions', engine, if_exists='append', index=False)
                print("✅ Session stored in database")
            except Exception as db_error:
                print(f"⚠️ Database storage failed, continuing with cookie-only session: {db_error}")

            return session_id
        except Exception as e:
            print(f"❌ Failed to create session: {e}")
            return None

    def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Validate session with multiple fallbacks."""
        if not session_id:
            return None

        # Try database first
        user_info = self._try_database_validation(session_id)
        if user_info:
            print("✅ Used database session authentication")
            return user_info

        # Fallback: Try cookie-stored user info
        user_info = self._try_cookie_validation()
        if user_info:
            print("✅ Using cookie fallback authentication")
            return user_info

        return None

    def _try_database_validation(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Try to validate via database."""
        try:
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
                    return json.loads(user_info_json)
        except Exception as e:
            print(f"⚠️ Database validation failed: {e}")
        return None

    def _try_cookie_validation(self) -> Optional[Dict[str, Any]]:
        """Try to validate via cookie-stored user info."""
        try:
            user_info_json = cookies.get(self.user_info_cookie)
            if not user_info_json:
                return None

            user_info = json.loads(user_info_json)
            print("✅ Found user info in cookies")
            print(f"User info from cookie: {user_info}")
            
            # Check if cookie has expired
            expires_at_str = user_info.get('expires_at')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now() >= expires_at:
                    # Clean up expired cookie
                    if self.user_info_cookie in cookies:
                        del cookies[self.user_info_cookie]
                    return None

            return user_info
        except Exception as e:
            print(f"⚠️ Cookie validation failed: {e}")
            # Clean up corrupted cookie
            if self.user_info_cookie in cookies:
                del cookies[self.user_info_cookie]
        return None

    def set_session_cookie(self, session_id: str):
        """Set persistent cookies with session ID and user info."""
        # Set session ID cookie
        cookies[self.cookie_name] = session_id
        
        # NEW: Also store user info in cookie for fallback
        user_info = st.session_state.get('user_info')
        if user_info:
            enhanced_user_info = user_info.copy()
            expires_at = st.session_state.get('token_expiry', datetime.now() + timedelta(hours=24))
            enhanced_user_info['expires_at'] = expires_at.isoformat()
            cookies[self.user_info_cookie] = json.dumps(enhanced_user_info)

        cookies.save()
        st.session_state.current_session_id = session_id

    def get_session_cookie(self) -> Optional[str]:
        """Get session ID from cookie."""
        # Check session state first
        session_id = st.session_state.get('current_session_id')
        if session_id and self.validate_session(session_id):
            return session_id

        # Read from cookie manager
        cookie_value = cookies.get(self.cookie_name)
        if cookie_value and self.validate_session(cookie_value):
            st.session_state.current_session_id = cookie_value
            return cookie_value

        return None

    def clear_session_cookie(self):
        """Clear all session cookies and state."""
        print(f"🧹 CLEAR SESSION: Starting cookie and session cleanup...")

        # Clear cookies
        for cookie_name in [self.cookie_name, self.user_info_cookie]:
            if cookie_name in cookies:
                print(f"🧹 CLEAR SESSION: Found cookie {cookie_name}, deleting...")
                del cookies[cookie_name]

        cookies.save()
        print(f"✅ Session cookies cleared from cookie manager and browser")

        # Clear session state
        keys_to_clear = ['current_session_id', 'authenticated', 'user_info', 'access_token', 'token_expiry', 'auth_timestamp']
        cleared_keys = []
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
                cleared_keys.append(key)

        print(f"✅ Session state cleared: {cleared_keys}")
        print(f"🧹 CLEAR SESSION: Cleanup completed")
# Global session manager instance
session_manager = None

def get_session_manager():
    """Get the global session manager instance."""
    global session_manager
    if session_manager is None:
        import app
        session_manager = SessionManager(app.get_engine)
    return session_manager