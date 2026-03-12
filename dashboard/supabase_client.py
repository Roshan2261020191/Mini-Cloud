import streamlit as st
from supabase import create_client
import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

print("SUPABASE_URL:", url)
print("SUPABASE_KEY:", key)

@st.cache_resource
def get_supabase():
    return create_client(url, key)

supabase = get_supabase()