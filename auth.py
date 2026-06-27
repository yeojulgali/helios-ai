import streamlit as st
from supabase import create_client


def clear_auth_session():
    keys = [
        "user_id",
        "user_email",
        "supabase_access_token",
        "supabase_refresh_token",
    ]

    for key in keys:
        if key in st.session_state:
            del st.session_state[key]


def get_supabase_client():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]

    client = create_client(url, key)

    access_token = st.session_state.get("supabase_access_token")
    refresh_token = st.session_state.get("supabase_refresh_token")

    if access_token and refresh_token:
        try:
            response = client.auth.set_session(access_token, refresh_token)
            session = getattr(response, "session", None)

            if session:
                st.session_state["supabase_access_token"] = session.access_token
                st.session_state["supabase_refresh_token"] = session.refresh_token

        except Exception:
            clear_auth_session()

    return client


def save_auth_session(auth_response):
    user = getattr(auth_response, "user", None)
    session = getattr(auth_response, "session", None)

    if not session:
        return user, None

    session_user = getattr(session, "user", None)

    if session_user:
        user = session_user

    st.session_state["supabase_access_token"] = session.access_token
    st.session_state["supabase_refresh_token"] = session.refresh_token

    if user:
        st.session_state["user_id"] = user.id
        st.session_state["user_email"] = user.email

    return user, session


def sign_up(email: str, password: str):
    client = get_supabase_client()

    response = client.auth.sign_up({
        "email": email,
        "password": password,
    })

    user, session = save_auth_session(response)

    return user, session


def sign_in(email: str, password: str):
    client = get_supabase_client()

    response = client.auth.sign_in_with_password({
        "email": email,
        "password": password,
    })

    user, session = save_auth_session(response)

    return user, session


def sign_out():
    try:
        client = get_supabase_client()
        client.auth.sign_out()
    except Exception:
        pass

    clear_auth_session()


def is_logged_in():
    return "user_id" in st.session_state and "user_email" in st.session_state


def get_current_user_id():
    return st.session_state.get("user_id")


def get_current_user_email():
    return st.session_state.get("user_email")