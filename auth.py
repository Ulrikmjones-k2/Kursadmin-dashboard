"""
Simple Azure AD Authentication for Streamlit
"""

import streamlit as st
import msal
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from session_manager import get_session_manager

load_dotenv()

class AzureADAuth:
    """Simple Azure AD authentication handler."""

    def __init__(self):
        self.tenant_id = os.getenv('AZURE_TENANT_ID')
        self.client_id = os.getenv('AZURE_CLIENT_ID')
        self.client_secret = os.getenv('AZURE_CLIENT_SECRET')
        self.authority = os.getenv('AZURE_AUTHORITY')
        self.redirect_uri = os.getenv('AZURE_REDIRECT_URI')
        self.scopes = ["User.Read"]

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise ValueError("Missing Azure AD configuration")

    def get_msal_app(self):
        """Create MSAL application instance."""
        return msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority
        )

    def get_auth_url(self):
        """Generate Azure AD login URL."""
        app = self.get_msal_app()
        return app.get_authorization_request_url(
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )

    def handle_auth_callback(self):
        """Handle callback from Azure AD."""
        code = st.query_params.get('code')
        if not code:
            return False

        try:
            app = self.get_msal_app()
            result = app.acquire_token_by_authorization_code(
                code,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )

            if "access_token" in result:
                user_info = self._get_user_info(result["access_token"])
                if user_info:
                    # Store in session state
                    st.session_state.authenticated = True
                    st.session_state.user_info = user_info
                    st.session_state.access_token = result["access_token"]
                    st.session_state.token_expiry = datetime.now() + timedelta(hours=1)
                    st.session_state.auth_timestamp = datetime.now()

                    # Create persistent session
                    session_mgr = get_session_manager()
                    session_id = session_mgr.create_session(user_info)
                    if session_id:
                        session_mgr.set_session_cookie(session_id)

                    # Clear URL parameters
                    st.query_params.clear()
                    return True

        except Exception as e:
            st.error(f"Authentication failed: {e}")

        return False

    def _get_user_info(self, access_token):
        """Get user info from Microsoft Graph."""
        try:
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Failed to get user info: {e}")
        return None

    def is_authenticated(self):
        """Check if user is authenticated."""
        # Check session state first
        if st.session_state.get('authenticated'):
            token_expiry = st.session_state.get('token_expiry')
            if token_expiry and datetime.now() < token_expiry:
                return True

        # Try to restore from persistent session
        session_mgr = get_session_manager()
        session_id = session_mgr.get_session_cookie()
        if session_id:
            user_info = session_mgr.validate_session(session_id)
            if user_info:
                # Restore session state
                st.session_state.authenticated = True
                st.session_state.user_info = user_info
                st.session_state.access_token = "restored_session"
                st.session_state.token_expiry = datetime.now() + timedelta(hours=24)
                st.session_state.auth_timestamp = datetime.now()
                return True

        return False

    def logout(self):
        """Logout user."""
        # Clear persistent session
        session_mgr = get_session_manager()
        session_mgr.clear_session_cookie()

        # Clear additional session state
        if 'login_cookie_check' in st.session_state:
            del st.session_state['login_cookie_check']

# Global instance
azure_auth = AzureADAuth()

# Simple convenience functions
def check_authentication():
    """Check if user is authenticated."""
    # Handle auth callback first
    if st.query_params.get('code'):
        azure_auth.handle_auth_callback()

    return azure_auth.is_authenticated()

def show_login_page():
    """Show login page."""
    st.title("🔐 Login Required")
    st.write("Please sign in to access the Course Management Dashboard.")

    # First, try to read existing cookies immediately
    session_mgr = get_session_manager()

    # Try to get session cookie directly from session manager
    if 'login_cookie_check' not in st.session_state:
        print(f"🔍 LOGIN PAGE: Checking for existing session...")
        session_id = session_mgr.get_session_cookie()
        if session_id:
            print(f"🔍 LOGIN PAGE: Found session ID from cookie: {session_id[:8]}...")
            user_info = session_mgr.validate_session(session_id)
            if user_info:
                print(f"✅ LOGIN PAGE: Session valid - restoring authentication for {user_info.get('displayName', 'Unknown')}")
                # Restore session state
                st.session_state.authenticated = True
                st.session_state.user_info = user_info
                st.session_state.access_token = "restored_session"
                st.session_state.token_expiry = datetime.now() + timedelta(hours=24)
                st.session_state.auth_timestamp = datetime.now()
                st.session_state.current_session_id = session_id

                print(f"🔄 LOGIN PAGE: Authentication restored, refreshing...")
                st.rerun()
            else:
                print(f"❌ LOGIN PAGE: Session invalid - will show login form")
        else:
            print(f"❌ LOGIN PAGE: No session cookie found - will show login form")

        st.session_state.login_cookie_check = True


    # Show login form
    if st.button("🚀 Sign in with Microsoft", type="primary"):
        auth_url = azure_auth.get_auth_url()

        # Use HTML button that stays in same tab (the working solution!)
        html_button = f"""
        <div style="text-align: center; margin: 20px 0;">
            <a href="{auth_url}" target="_self" style="
                display: inline-block;
                background-color: #0078d4;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 16px;
                border: none;
                cursor: pointer;
            ">🔗 Click here to login with Microsoft</a>
        </div>
        """
        st.html(html_button)

def show_logout_button():
    """Show logout button."""
    if st.button("🚪 Logout"):
        azure_auth.logout()
        st.rerun()

def get_current_user():
    """Get current user info."""
    return st.session_state.get('user_info')

def cleanup_expired_sessions():
    """Cleanup expired sessions."""
    pass  # Simplified - no cleanup needed