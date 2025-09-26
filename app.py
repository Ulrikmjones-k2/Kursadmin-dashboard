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
        st.error(f"Database-feil: {str(e)}")
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

def get_course_instructors(course_id):
    """Get instructors for a specific course by frontcore_id"""
    query = """
    SELECT
        i.full_name,
        i.email,
        i.phone_number,
        i.notes AS instructor_notes,
        ic.new_instructor,
        ic.contract_sent,
        ic.contract_signed
    FROM instructors i
    INNER JOIN instructors_coursedates ic ON i.id = ic.instructor_id
    INNER JOIN coursedates cd ON ic.coursedate_id = cd.id
    WHERE cd.frontcore_id = ?
    ORDER BY i.full_name
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params=(course_id,))
        return df
    except Exception as e:
        print(f"Error fetching course instructors for course {course_id}: {e}")
        # Check if the error is due to missing tables
        if "Invalid object name 'instructors'" in str(e) or "Invalid object name 'instructors_coursedates'" in str(e):
            print("Instructor tables not found - they may not be created yet")
        return pd.DataFrame()

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
        st.session_state.current_page = "Kursoversikt"

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

def add_dynamic_height_css():
    """Add CSS for dynamic dataframe height calculation"""
    st.markdown("""
    <style>
    .stDataFrame > div {
        height: calc(100vh - 400px) !important;
    }
    </style>
    """, unsafe_allow_html=True)

def add_compact_css():
    """Add CSS for compact layout to minimize scrolling"""
    st.markdown("""
    <style>
    /* Reduce general spacing */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
    }

    /* Compact dataframes */
    .stDataFrame {
        font-size: 0.9rem !important;
    }

    /* Reduce spacing between elements */
    .element-container {
        margin-bottom: 0.5rem !important;
    }

    /* Compact headers */
    h1, h2, h3 {
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }

    /* Reduce expander spacing */
    .streamlit-expander {
        margin-bottom: 0.5rem !important;
    }

    /* Compact columns */
    .stColumn > div {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# PAGE COMPONENTS
# =============================================================================


def show_courses_datasheet_page():
    """Display the courses datasheet page"""
    st.header("Kursoversikt")

    # Search functionality
    search_term = st.text_input(
        "Søk i kurs",
        placeholder="Søk etter tittel, sted eller status...",
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
        add_dynamic_height_css()

        st.write(f"Fant {len(display_df)} kurs")

        # Display datasheet with selection capability (CSS handles dynamic height)
        event = st.dataframe(
            display_df,
            height=400,  # Base height, CSS will override with dynamic calculation
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
    else:
        st.warning("Ingen kurs funnet eller problem med databaseforbindelse")

def show_course_details_page():
    """Display the course details page"""
    st.header("Kursdetaljer")

    if 'selected_course_id' in st.session_state and st.session_state.selected_course_id:
        course_df = get_course_by_id(st.session_state.selected_course_id)

        if not course_df.empty:
            course_data = course_df.iloc[0]

            # Apply compact CSS for minimal scrolling
            add_compact_css()

            # Back button
            if st.button("Tilbake til kursoversikt"):
                st.session_state.selected_course_id = None
                st.session_state.should_redirect = False
                st.session_state.current_page = "Kursoversikt"

                # Reset audit logging tracking to ensure back navigation gets logged
                st.session_state.last_logged_page = None
                st.session_state.last_logged_course_id = None
                st.rerun()

            st.subheader(f"{course_data['Tittel']}")

            # Compact course information in 3 columns
            col1, col2, col3 = st.columns(3)

            with col1:
                st.write(f"**ID:** {course_data['KursdatoID']}")
                st.write(f"**Sted:** {course_data['Sted']}")
                st.write(f"**Status:** {course_data['Status']}")
                st.write(f"**Ansvarlig:** {course_data['Ansvarlig'] or 'Ikke oppgitt'}")

            with col2:
                st.write(f"**Start:** {course_data['Startdato']}")
                st.write(f"**Slutt:** {course_data['Sluttdato']}")
                st.write(f"**Tid:** {course_data['Tid']}")
                fakturert_text = "Ja" if course_data['Fakturert'] else "Nei"
                st.write(f"**Fakturert:** {fakturert_text}")

            with col3:
                st.write(f"**Avdeling:** {course_data['Avdelingsnummer']}")
                st.write(f"**Fakturert av:** {course_data['Hvem fakturerte'] or 'Ikke oppgitt'}")
                if course_data['Notater']:
                    with st.expander("Notater", expanded=False):
                        st.write(course_data['Notater'])
                else:
                    st.write("**Notater:** *Ingen*")

            # Compact Instructors Section
            st.markdown("### Instruktører")

            # Get instructors for this course
            instructors_df = get_course_instructors(st.session_state.selected_course_id)

            if not instructors_df.empty:
                # Create a complete display table with all details
                display_data = []
                for idx, instructor in instructors_df.iterrows():
                    display_data.append({
                        'Navn': instructor['full_name'],
                        'E-post': instructor['email'] if pd.notna(instructor['email']) and instructor['email'] else 'Ikke oppgitt',
                        'Telefon': instructor['phone_number'] if pd.notna(instructor['phone_number']) and instructor['phone_number'] else 'Ikke oppgitt',
                        'Ny instruktør': 'Ja' if instructor['new_instructor'] else 'Nei',
                        'Kontrakt sendt': 'Ja' if instructor['contract_sent'] else 'Nei',
                        'Kontrakt signert': 'Ja' if instructor['contract_signed'] else 'Nei',
                        'Notater': instructor['instructor_notes'] if pd.notna(instructor['instructor_notes']) and instructor['instructor_notes'] else 'Ingen notater'
                    })

                # Display as complete table
                complete_df = pd.DataFrame(display_data)
                st.dataframe(complete_df, width='stretch', hide_index=True)
            else:
                st.info("Ingen instruktører registrert for dette kurset.")
        else:
            st.warning("Kurs ikke funnet")
    else:
        st.info("Ingen kurs valgt. Gå til kursoversikten og klikk på en kurstittel eller ID.")

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
        page_title="Kursadministrasjonsdashbord",
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
    with st.sidebar:
        # Display current user name
        user = get_current_user()
        if user and 'displayName' in user:
            st.write(f"Hei, **{user['displayName']}**")
        elif user and 'display_name' in user:
            st.write(f"Hei, **{user['display_name']}**")
        else:
            st.write("Hei, **Ukjent bruker**")

        show_logout_button()
        st.markdown("---")  # Add separator
        st.title("Navigasjon")

    # Check for automatic navigation to details page
    if st.session_state.get('should_redirect', False):
        st.session_state.current_page = "Kursdetaljer"
        st.session_state.should_redirect = False  # Reset flag after redirect

    # Get current page index for selectbox
    page_options = ["Kursoversikt", "Kursdetaljer"]
    current_index = page_options.index(st.session_state.current_page)

    # Navigation selectbox with proper default
    page = st.sidebar.selectbox(
        "Velg visning",
        page_options,
        index=current_index
    )

    # Update current page if user changed selection
    if page != st.session_state.current_page:
        st.session_state.current_page = page

    # Route to appropriate page with smart audit logging
    if page == "Kursoversikt":
        smart_log_page_view("Kursoversikt")  # Only logs actual navigation
        show_courses_datasheet_page()
    elif page == "Kursdetaljer":
        course_id = st.session_state.get('selected_course_id')
        smart_log_page_view("Kursdetaljer", course_id)  # Only logs actual navigation
        show_course_details_page()

# Run the application
if __name__ == "__main__":
    main()