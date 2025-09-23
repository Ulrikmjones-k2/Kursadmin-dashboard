import streamlit as st
import pandas as pd
import pyodbc
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from urllib.parse import quote_plus

# Import authentication and audit modules
from auth import check_authentication, show_login_page, show_logout_button, get_current_user, cleanup_expired_sessions
from audit import log_page_view, log_course_update, log_search_activity, log_user_login, log_user_logout

# Load environment variables
load_dotenv()

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

@st.cache_resource
def get_engine():
    """Create SQLAlchemy engine using Azure SQL connection string"""
    env = os.getenv('ENVIRONMENT', 'test')
    if env == 'prod':
        connection_string = os.getenv('AZURE_SQL_PROD_CONNECTION_STRING')
    else:
        connection_string = os.getenv('AZURE_SQL_TEST_CONNECTION_STRING')

    # Convert pyodbc connection string to SQLAlchemy URL
    sqlalchemy_url = f"mssql+pyodbc:///?odbc_connect={quote_plus(connection_string)}"
    return create_engine(sqlalchemy_url)

def fetch_data(query):
    """Execute SQL query and return DataFrame"""
    try:
        engine = get_engine()
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return pd.DataFrame()


def get_courses_data():
    """Get all courses data with formatting"""
    query = """
    SELECT
        cd.id,
        cd.frontcore_id AS KursdatoID,
        cd.title AS Tittel,
        cd.location,
        FORMAT(cd.start_date, 'dd.MM.yyyy') AS Startdato,
        FORMAT(cd.end_date, 'dd.MM.yyyy') AS Sluttdato,
        CASE
            WHEN cd.Status = 'Will run' THEN 'Gjennomføres'
            WHEN cd.Status = 'To be defined' THEN 'Uavklart'
            ELSE cd.Status
        END AS Status,
        CONVERT(VARCHAR(5), cd.start_time, 108) + ' - ' + CONVERT(VARCHAR(5), cd.end_time, 108) AS Tid,
        cd.department_number AS Avdelingsnummer,
        cd.billed AS Fakturert,
        cd.responsible AS Ansvarlig,
        cd.who_billed AS [Hvem fakturerte],
        cd.notes AS [Notater],
        CASE
            WHEN cd.location IS NULL OR cd.location = ''
            THEN 'Nettstudier'
            WHEN cd.location = 'Norway' THEN 'Bedriftskurs'
            WHEN cd.location = 'Nett' THEN 'Nettundervisning'
            ELSE cd.location
        END AS Sted
    FROM
        coursedates AS cd
    WHERE ((cd.start_date >= '2025-08-01' AND cd.start_date <= '2025-10-01')
        OR (cd.end_date >= '2025-08-01' AND cd.end_date <= '2025-12-20'))
    ORDER BY cd.start_date DESC
    """
    return fetch_data(query)

def get_course_by_id(course_id):
    """Get specific course data by frontcore_id"""
    query = f"""
    SELECT
        cd.id,
        cd.frontcore_id AS KursdatoID,
        cd.title AS Tittel,
        cd.location,
        FORMAT(cd.start_date, 'dd.MM.yyyy') AS Startdato,
        FORMAT(cd.end_date, 'dd.MM.yyyy') AS Sluttdato,
        CASE
            WHEN cd.Status = 'Will run' THEN 'Gjennomføres'
            WHEN cd.Status = 'To be defined' THEN 'Uavklart'
            ELSE cd.Status
        END AS Status,
        CONVERT(VARCHAR(5), cd.start_time, 108) + ' - ' + CONVERT(VARCHAR(5), cd.end_time, 108) AS Tid,
        cd.department_number AS Avdelingsnummer,
        cd.billed AS Fakturert,
        cd.responsible AS Ansvarlig,
        cd.who_billed AS [Hvem fakturerte],
        cd.notes AS [Notater],
        CASE
            WHEN cd.location IS NULL OR cd.location = ''
            THEN 'Nettstudier'
            WHEN cd.location = 'Norway' THEN 'Bedriftskurs'
            WHEN cd.location = 'Nett' THEN 'Nettundervisning'
            ELSE cd.location
        END AS Sted
    FROM
        coursedates AS cd
    WHERE cd.frontcore_id = '{course_id}'
    """
    return fetch_data(query)

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def filter_courses(courses_df, search_term):
    """Filter courses based on search term"""
    if search_term:
        mask = (
            courses_df['Tittel'].str.contains(search_term, case=False, na=False) |
            courses_df['Sted'].str.contains(search_term, case=False, na=False) |
            courses_df['Status'].str.contains(search_term, case=False, na=False)
        )
        return courses_df[mask]
    return courses_df

def get_display_columns():
    """Get the columns to display in the datasheet"""
    return ['Tittel', 'KursdatoID', 'Sted', 'Startdato', 'Sluttdato', 'Status', 'Fakturert']

def initialize_session_state():
    """Initialize session state variables"""
    if 'selected_course_id' not in st.session_state:
        st.session_state.selected_course_id = None
    if 'should_redirect' not in st.session_state:
        st.session_state.should_redirect = False
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "Courses Datasheet"

    # Audit logging tracking to prevent duplicate page view logs
    if 'last_logged_page' not in st.session_state:
        st.session_state.last_logged_page = None
    if 'last_logged_course_id' not in st.session_state:
        st.session_state.last_logged_course_id = None

def smart_log_page_view(page_name: str, course_id: str = None):
    """
    Smart page view logging that only logs actual navigation events.

    This prevents logging every form field change as a "page view".
    Only logs when user actually navigates to a different page or course.

    Args:
        page_name: Name of the page being viewed
        course_id: Course ID if viewing course details
    """
    # Get current state
    current_page = page_name
    current_course = course_id

    # Get last logged state
    last_page = st.session_state.get('last_logged_page')
    last_course = st.session_state.get('last_logged_course_id')

    # Only log if this is actually a new navigation event
    if current_page != last_page or current_course != last_course:
        # This is a real navigation - log it
        log_page_view(page_name, course_id)

        # Update tracking to prevent duplicate logs
        st.session_state.last_logged_page = current_page
        st.session_state.last_logged_course_id = current_course

        # Debug info (can be removed later)
        print(f"📊 SMART AUDIT: Logged page view - {page_name}" +
              (f" (Course: {course_id})" if course_id else ""))
    else:
        # This is just a form rerun - don't log
        print(f"🔄 SMART AUDIT: Skipped duplicate log - {page_name}" +
              (f" (Course: {course_id})" if course_id else ""))

def initialize_course_edit_state(course_data):
    """Initialize session state for course editing"""
    if 'edit_billed' not in st.session_state:
        st.session_state.edit_billed = bool(course_data.get('Fakturert', False))
    if 'edit_responsible' not in st.session_state:
        st.session_state.edit_responsible = course_data.get('Ansvarlig', '') or ''
    if 'edit_who_billed' not in st.session_state:
        st.session_state.edit_who_billed = course_data.get('Hvem fakturerte', '') or ''
    if 'edit_notes' not in st.session_state:
        st.session_state.edit_notes = course_data.get('Notater', '') or ''

def save_course_changes(original_course_data):
    """
    Save course changes to database with comprehensive audit logging.

    Learning Note: This function demonstrates how to:
    1. Collect current form values
    2. Compare with original values
    3. Update database
    4. Log changes for GDPR compliance

    Args:
        original_course_data: The original course data before changes
    """

    try:
        # Get current values from form widgets
        current_values = {
            'billed': st.session_state.get('billed_checkbox', False),
            'responsible': st.session_state.get('responsible_input', ''),
            'who_billed': st.session_state.get('who_billed_input', ''),
            'notes': st.session_state.get('notes_textarea', '')
        }

        # Get original values for comparison
        original_values = {
            'billed': bool(original_course_data.get('Fakturert', False)),
            'responsible': original_course_data.get('Ansvarlig', '') or '',
            'who_billed': original_course_data.get('Hvem fakturerte', '') or '',
            'notes': original_course_data.get('Notater', '') or ''
        }

        # Check if any changes were made
        changes_made = any(current_values[key] != original_values[key] for key in current_values.keys())

        if not changes_made:
            st.info("No changes detected.")
            return

        # Build SQL update statement
        update_sql = """
        UPDATE coursedates
        SET billed = ?, responsible = ?, who_billed = ?, notes = ?
        WHERE frontcore_id = ?
        """

        course_id = original_course_data['KursdatoID']

        # Execute update
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(update_sql, (
                current_values['billed'],
                current_values['responsible'],
                current_values['who_billed'],
                current_values['notes'],
                course_id
            ))
            conn.commit()

        # Log the changes for GDPR compliance
        log_course_update(course_id, original_values, current_values)

        # Update session state with new values
        st.session_state.edit_billed = current_values['billed']
        st.session_state.edit_responsible = current_values['responsible']
        st.session_state.edit_who_billed = current_values['who_billed']
        st.session_state.edit_notes = current_values['notes']

        # Show success message
        st.success("✅ Changes saved successfully!")

        # Get current user for personalized message
        user = get_current_user()
        if user:
            st.info(f"Changes saved by {user['display_name']} at {pd.Timestamp.now().strftime('%H:%M:%S')}")

    except Exception as e:
        st.error(f"❌ Error saving changes: {str(e)}")

        # Log the error for troubleshooting
        user = get_current_user()
        if user:
            print(f"Save error for user {user['email']}: {str(e)}")

def add_hyperlink_css():
    """Add CSS styling for hyperlink appearance in dataframes"""
    st.markdown("""
    <style>
    .dataframe td:nth-child(1), .dataframe td:nth-child(2) {
        color: #0066cc !important;
        text-decoration: underline !important;
        cursor: pointer !important;
    }
    .dataframe td:nth-child(1):hover, .dataframe td:nth-child(2):hover {
        color: #004499 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# PAGE COMPONENTS
# =============================================================================


def show_courses_datasheet_page():
    """Display the courses datasheet page"""
    st.header("Courses Datasheet")

    # Search functionality
    search_term = st.text_input(
        "🔍 Search courses",
        placeholder="Search by title, location, or status...",
        key="search_input_simple"
    )

    # Get and filter courses data
    courses_df = get_courses_data()
    if not courses_df.empty:
        filtered_df = filter_courses(courses_df, search_term)

        # Log search activity for GDPR compliance
        if search_term:
            log_search_activity(search_term, len(filtered_df))

        # Select display columns and reset index
        display_columns = get_display_columns()
        display_df = filtered_df[display_columns].reset_index(drop=True)

        # Initialize session state and add styling
        initialize_session_state()
        add_hyperlink_css()

        st.write(f"Found {len(display_df)} courses")

        # Display datasheet with selection capability
        event = st.dataframe(
            display_df,
            height=400,
            width='stretch',
            on_select="rerun",
            selection_mode="single-row"
        )

        # Handle row selection
        if event.selection.rows and not st.session_state.should_redirect:
            selected_row = event.selection.rows[0]
            selected_course = display_df.iloc[selected_row]

            st.session_state.selected_course_id = selected_course['KursdatoID']
            st.session_state.should_redirect = True
            st.rerun()

        # Alternative course selection method
        st.subheader("💡 How to View Course Details")
        st.info("Click on any row in the table above to view detailed course information. You'll automatically be taken to the Course Details page.")

        # Optional: Keep selectbox as fallback
        with st.expander("Alternative: Use dropdown selection"):
            if len(display_df) > 0:
                # Create course options for selection
                course_options = []
                for idx, row in display_df.iterrows():
                    course_options.append(f"{row['Tittel']} ({row['KursdatoID']})")

                selected_option = st.selectbox(
                    "Choose a course to view details:",
                    course_options,
                    key="course_selector",
                    index=None,
                    placeholder="Select a course..."
                )

                if selected_option:
                    # Find the selected course
                    selected_idx = course_options.index(selected_option)
                    selected_course_id = display_df.iloc[selected_idx]['KursdatoID']

                    # Store selected course and navigate to detail page
                    st.session_state.selected_course_id = selected_course_id
                    st.info(f"Selected: {selected_option}. Navigate to 'Course Details' page to view full information.")
            else:
                st.info("No courses available for selection.")

        st.write(f"Total courses: {len(filtered_df)} / {len(courses_df)}")
    else:
        st.warning("No courses found or database connection issue")

def show_course_details_page():
    """Display the course details page"""
    st.header("Course Details")

    if 'selected_course_id' in st.session_state and st.session_state.selected_course_id:
        course_df = get_course_by_id(st.session_state.selected_course_id)

        if not course_df.empty:
            course_data = course_df.iloc[0]

            # Initialize editing state
            initialize_course_edit_state(course_data)

            # Back button
            if st.button("← Back to Courses Datasheet"):
                st.session_state.selected_course_id = None
                st.session_state.should_redirect = False
                st.session_state.current_page = "Courses Datasheet"

                # Reset audit logging tracking to ensure back navigation gets logged
                st.session_state.last_logged_page = None
                st.session_state.last_logged_course_id = None

                # Clear editing state
                for key in ['edit_billed', 'edit_responsible', 'edit_who_billed', 'edit_notes']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()

            st.subheader(f"{course_data['Tittel']}")

            # Course Information Section (Read-only)
            st.markdown("### 📋 Course Information")
            col1, col2 = st.columns(2)

            with col1:
                st.write(f"**KursdatoID:** {course_data['KursdatoID']}")
                st.write(f"**Tittel:** {course_data['Tittel']}")
                st.write(f"**Sted:** {course_data['Sted']}")
                st.write(f"**Startdato:** {course_data['Startdato']}")

            with col2:
                st.write(f"**Sluttdato:** {course_data['Sluttdato']}")
                st.write(f"**Status:** {course_data['Status']}")
                st.write(f"**Tid:** {course_data['Tid']}")
                st.write(f"**Avdelingsnummer:** {course_data['Avdelingsnummer']}")

            st.divider()

            # Administrative Details Section (Editable)
            st.markdown("### ✏️ Administrative Details")

            admin_col1, admin_col2 = st.columns(2)

            with admin_col1:
                st.text_input(
                    "Ansvarlig",
                    value=st.session_state.edit_responsible,
                    key="responsible_input"
                )

                st.checkbox(
                    "Fakturert",
                    value=st.session_state.edit_billed,
                    key="billed_checkbox"
                )

            with admin_col2:
                st.text_input(
                    "Hvem fakturerte",
                    value=st.session_state.edit_who_billed,
                    key="who_billed_input"
                )

            # Notes section (full width)
            st.text_area(
                "Notater",
                value=st.session_state.edit_notes,
                height=100,
                key="notes_textarea"
            )

            # Save button with audit logging
            st.markdown("---")
            col1, col2, col3 = st.columns([1, 1, 1])

            with col2:
                if st.button("💾 Save Changes", type="primary"):
                    save_course_changes(course_data)
        else:
            st.warning("Course not found")
    else:
        st.info("No course selected. Please go to the Courses Datasheet and click on a course title or ID.")

# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main():
    """
    Main application function with authentication wrapper.

    Learning Note: This is the authentication middleware pattern.
    We check authentication first, then show the appropriate content.
    """

    # Set page configuration
    st.set_page_config(
        page_title="Course Management Dashboard",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Clean up expired sessions on app startup (run once per session)
    if 'session_cleanup_done' not in st.session_state:
        cleanup_expired_sessions()
        st.session_state.session_cleanup_done = True

    # Check authentication status
    if not check_authentication():
        # User is not authenticated - show login page
        show_login_page()
        return

    # User is authenticated - show the main application
    show_authenticated_dashboard()


def show_authenticated_dashboard():
    """
    Show the main dashboard for authenticated users.

    Learning Note: We separate the authenticated content into its own function
    to keep the authentication logic clean and maintainable.
    """

    initialize_session_state()

    # Show user info and logout button in sidebar
    show_logout_button()

    st.sidebar.markdown("---")  # Add separator
    st.sidebar.title("Navigation")

    # Check for automatic navigation to details page
    if st.session_state.get('should_redirect', False):
        st.session_state.current_page = "Course Details"
        st.session_state.should_redirect = False  # Reset flag after redirect

    # Get current page index for selectbox
    page_options = ["Courses Datasheet", "Course Details"]
    current_index = page_options.index(st.session_state.current_page)

    # Navigation selectbox with proper default
    page = st.sidebar.selectbox(
        "Select View",
        page_options,
        index=current_index
    )

    # Update current page if user changed selection
    if page != st.session_state.current_page:
        st.session_state.current_page = page

    # Route to appropriate page with smart audit logging
    if page == "Courses Datasheet":
        smart_log_page_view("Courses Datasheet")  # Only logs actual navigation
        show_courses_datasheet_page()
    elif page == "Course Details":
        course_id = st.session_state.get('selected_course_id')
        smart_log_page_view("Course Details", course_id)  # Only logs actual navigation
        show_course_details_page()

# Run the application
if __name__ == "__main__":
    main()