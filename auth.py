"""
Simple Microsoft Authentication for Streamlit Dashboard
Session-based with simple cookie persistence
"""

import streamlit as st
import msal
import os
import requests
from dotenv import load_dotenv
from streamlit_cookies_manager import EncryptedCookieManager

load_dotenv()

# Initialize cookie manager
cookies = EncryptedCookieManager(
    prefix="dashboard_",
    password="simple_dashboard_secret_2024"
)

if not cookies.ready():
    st.stop()

# Azure AD Configuration
TENANT_ID = os.getenv('AZURE_TENANT_ID')
CLIENT_ID = os.getenv('AZURE_CLIENT_ID')
CLIENT_SECRET = os.getenv('AZURE_CLIENT_SECRET')
AUTHORITY = os.getenv('AZURE_AUTHORITY')
REDIRECT_URI = os.getenv('AZURE_REDIRECT_URI')
SCOPES = ["User.Read"]

def get_msal_app():
    """Create MSAL application."""
    return msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )

def get_login_url():
    """Generate Microsoft login URL."""
    app = get_msal_app()
    return app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

def handle_login_callback():
    """Process Microsoft's callback with auth code."""
    auth_code = st.query_params.get('code')
    if not auth_code:
        return False

    try:
        # Exchange code for token
        app = get_msal_app()
        result = app.acquire_token_by_authorization_code(
            auth_code,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )

        if "access_token" in result:
            # Get user info from Microsoft Graph
            headers = {'Authorization': f'Bearer {result["access_token"]}'}
            response = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers)

            if response.status_code == 200:
                user_info = response.json()

                # Store in session state
                st.session_state.authenticated = True
                st.session_state.user_info = user_info
                st.session_state.access_token = result["access_token"]

                # NEW: Also set cookie for persistence
                set_user_cookie(user_info)

                # Clear URL parameters
                st.query_params.clear()
                st.success(f"Welcome, {user_info.get('displayName', 'User')}!")
                return True

    except Exception as e:
        st.error(f"Login failed: {str(e)}")

    return False

def is_authenticated():
    """Check if user is logged in this session."""
    return st.session_state.get('authenticated', False)

def get_current_user():
    """Get current user info."""
    return st.session_state.get('user_info')

def logout():
    """Logout user."""
    # Clear all auth-related session state
    keys_to_clear = ['authenticated', 'user_info', 'access_token', 'cookie_checked']
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    # NEW: Also clear cookie
    clear_user_cookie()

# Simple cookie functions
def set_user_cookie(user_info):
    """Set cookie with user info after login."""
    if cookies.ready():
        # Store just the user's name and email as simple string
        user_data = f"{user_info.get('displayName', 'Unknown')}|{user_info.get('mail', 'no-email')}"
        cookies['user'] = user_data
        cookies.save()
        print(f"🍪 SET COOKIE: Cookie name='user', Value='{user_data}'")
        print(f"🍪 SET COOKIE: Set for user: {user_info.get('displayName', 'Unknown')}")
        print(f"🍪 SET COOKIE: Location=browser cookie store with prefix 'dashboard_'")
    else:
        print("⚠️ SET COOKIE: Cookies not ready - cannot set cookie")

def check_existing_cookie():
    """Check if user has valid cookie (just report, don't login)."""
    print(f"🔍 CHECK COOKIE: Starting cookie search...")
    print(f"🔍 CHECK COOKIE: Looking for cookie name='user' with prefix 'dashboard_'")

    if cookies.ready():
        print(f"✅ CHECK COOKIE: Cookie manager is ready")
        user_data = cookies.get('user')
        print(f"🔍 CHECK COOKIE: Raw cookie value: '{user_data}'")

        if user_data and '|' in user_data:
            try:
                # Parse the stored data
                name, email = user_data.split('|', 1)
                print(f"✅ CHECK COOKIE: Found valid cookie!")
                print(f"✅ CHECK COOKIE: Cookie name='user', Full value='{user_data}'")
                print(f"✅ CHECK COOKIE: Parsed name='{name}', email='{email}'")
                print(f"✅ CHECK COOKIE: Location=browser cookie store with prefix 'dashboard_'")
                st.info(f"🍪 Found existing cookie for: {name}")
                return True
            except ValueError:
                print("❌ CHECK COOKIE: Invalid cookie format - clearing")
                del cookies['user']
                cookies.save()
        else:
            print("❌ CHECK COOKIE: No valid cookie found (empty or invalid format)")
    else:
        print("⚠️ CHECK COOKIE: Cookies not ready - cannot check cookie")
    return False

def clear_user_cookie():
    """Clear user cookie on logout."""
    print(f"🧹 CLEAR COOKIE: Starting cookie cleanup...")
    if cookies.ready() and 'user' in cookies:
        old_value = cookies.get('user')
        del cookies['user']
        cookies.save()
        print(f"🧹 CLEAR COOKIE: Deleted cookie name='user' with value='{old_value}'")
        print(f"🧹 CLEAR COOKIE: Location=browser cookie store with prefix 'dashboard_'")
        print("✅ CLEAR COOKIE: Cookie successfully cleared")
    else:
        print("❌ CLEAR COOKIE: No cookie to clear or cookies not ready")

def show_login_page():
    """Display login page."""
    st.title("🔐 Login Required")
    st.write("Please sign in with your Microsoft account to access the Course Management Dashboard.")

    # NEW: Check for existing cookie first (just report, don't login)
    if 'cookie_checked' not in st.session_state:
        check_existing_cookie()  # Just check and display info
        st.session_state.cookie_checked = True

    # Handle callback if present
    if st.query_params.get('code'):
        if handle_login_callback():
            st.rerun()

    # Show login button
    login_url = get_login_url()

    st.markdown(f"""
    <div style="text-align: center; margin: 40px 0;">
        <a href="{login_url}" target="_self" style="
            display: inline-block;
            background: linear-gradient(90deg, #0078d4 0%, #106ebe 100%);
            color: white;
            padding: 16px 32px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s ease;
        " onmouseover="this.style.transform='translateY(-2px)'"
           onmouseout="this.style.transform='translateY(0)'">
            🚀 Sign in with Microsoft
        </a>
    </div>
    """, unsafe_allow_html=True)

def show_logout_button():
    """Display logout button."""
    with st.sidebar:
        if st.button("🚪 Logout", type="secondary"):
            logout()
            st.rerun()

# Main authentication check function
def check_authentication():
    """Main function to check authentication status."""
    # Handle callback first
    if st.query_params.get('code') and not is_authenticated():
        handle_login_callback()

    return is_authenticated()

# Placeholder functions for compatibility
def cleanup_expired_sessions():
    """Placeholder - no session cleanup needed."""
    pass