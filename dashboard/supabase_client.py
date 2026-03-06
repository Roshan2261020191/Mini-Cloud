import streamlit as st
from supabase import create_client
import os

url = os.getenv("url")
key = os.getenv("key")

@st.cache_resource
def get_supabase():
    return create_client(url, key)

supabase = get_supabase()
