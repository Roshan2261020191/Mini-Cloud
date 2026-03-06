import streamlit as st
from user import user_login
from instances import show_dashboard


if "user_id" not in st.session_state:
    user_login()
else:
    if st.button("Logout"):
        st.query_params.clear()
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

    show_dashboard()