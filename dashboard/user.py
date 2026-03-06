import streamlit as st
import uuid
from supabase_client import supabase


def user_login():

    # Restore session from URL if session_state is empty
    if "user_id" not in st.session_state:
        params = st.query_params
        if "user_id" in params:
            st.session_state.user_id = params["user_id"]
            st.rerun()

    st.title("☁️ Welcome to Mini Cloud")

    tab1, tab2 = st.tabs(["New User", "Existing User"])

    # -------- NEW USER --------
    with tab1:
        with st.form("new_user_form_1"):
            name = st.text_input("Enter your name")

            if st.form_submit_button("Create Account"):
                if name.strip():
                    check_name = supabase.table("users") \
                        .select("*") \
                        .eq("name", name.strip()) \
                        .execute()

                    check_id = supabase.table("users") \
                        .select("*") \
                        .eq("user_id", name.strip()) \
                        .execute()

                    if check_name.data or check_id.data:
                        st.error(
                            "User already exists! Please login through Existing User section."
                        )
                    else:
                        user_id = f"{name.strip()}@{str(uuid.uuid4())[:8]}"

                        supabase.table("users").insert({
                            "name": name.strip(),
                            "user_id": user_id
                        }).execute()

                        st.success("Account created!")
                        st.info(f"Your ID: **{user_id}**")
                        st.warning("Save this ID!")

                        st.session_state.user_id = user_id
                        st.query_params["user_id"] = user_id
                        st.rerun()
                else:
                    st.warning("Please enter your name")

    # -------- EXISTING USER --------
    with tab2:
        with st.form("existing_user_form_1"):
            user_id_input = st.text_input("Enter your unique ID")

            if st.form_submit_button("Login"):
                if user_id_input.strip():
                    existing = supabase.table("users") \
                        .select("*") \
                        .eq("user_id", user_id_input.strip()) \
                        .execute()

                    if existing.data:
                        st.session_state.user_id = user_id_input.strip()
                        st.query_params["user_id"] = user_id_input.strip()
                        st.rerun()
                    else:
                        st.error("Invalid ID!")
                else:
                    st.warning("Please enter your ID")