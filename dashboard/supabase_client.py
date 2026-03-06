import streamlit as st
from supabase import create_client
import os

url = "https://cwoajirwcejfdfntcqxn.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN3b2FqaXJ3Y2VqZmRmbnRjcXhuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIwMDA1MTMsImV4cCI6MjA4NzU3NjUxM30.RQwYkl-QU0-m6e4c2gJ8lVfl815c-r2cdS5z5_CluzE"

@st.cache_resource
def get_supabase():
    return create_client(url, key)

supabase = get_supabase()
