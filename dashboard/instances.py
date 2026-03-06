import streamlit as st
from supabase_client import supabase
from datetime import datetime
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import random
import uuid
import requests   # 🔥 NEW


OS_CONFIG = {
    "Ubuntu": ["t2.nano", "t2.micro"],
    "Alpine Linux": ["t2.nano", "t2.micro"],
    "Debian Slim": ["t2.nano", "t2.micro"],
    "Ubuntu Minimal": ["t2.nano", "t2.micro"],
    "BusyBox": ["t2.nano", "t2.micro"]
}


def show_dashboard():

    # 🔐 keep user logged in
    if "user_id" not in st.session_state:
        params = st.query_params
        if "user_id" in params:
            st.session_state.user_id = params["user_id"]
        else:
            st.switch_page("login.py")

    st.title("☁️ Mini Cloud Dashboard")
    st.write(f"Welcome, **{st.session_state.user_id}**")

    default_option = "Proceed without a key pair (Not recommended)"

    # -------- SESSION --------
    if "show_key_form" not in st.session_state:
        st.session_state.show_key_form = False

    if "pending_download" not in st.session_state:
        st.session_state.pending_download = False

    if "creating_instance" not in st.session_state:
        st.session_state.creating_instance = False

    if "selected_key" not in st.session_state:
        st.session_state.selected_key = default_option

    if "reset_form" not in st.session_state:
        st.session_state.reset_form = False

    if "instance_name_input" not in st.session_state:
        st.session_state.instance_name_input = ""

    if "selected_os" not in st.session_state:
        st.session_state.selected_os = None

    if "selected_instance_type" not in st.session_state:
        st.session_state.selected_instance_type = None


    # -------- RESET FORM --------
    if st.session_state.reset_form:
        st.session_state.instance_name_input = ""
        st.session_state.selected_os = None
        st.session_state.selected_instance_type = None
        st.session_state.selected_key = default_option
        st.session_state.reset_form = False


    # -------- CREATE INSTANCE --------
    st.subheader("Create Instance")

    col1, col2 = st.columns(2)

    with col1:
        instance_name = st.text_input("Instance Name", key="instance_name_input")

    with col2:
        os_type = st.selectbox(
            "Operating System",
            list(OS_CONFIG.keys()),
            key="selected_os",
            index=None,
            placeholder="Select OS..."
        )

    instance_type = None
    if os_type:
        instance_type = st.selectbox(
            "Instance Type",
            OS_CONFIG[os_type],
            key="selected_instance_type",
            index=None,
            placeholder="Select Type..."
        )


    # -------- FETCH KEYS --------
    key_response = supabase.table("ssh_keys") \
        .select("key_name") \
        .eq("user_id", st.session_state.user_id) \
        .execute()

    user_keys = key_response.data if key_response.data else []

    key_options = [default_option]
    if user_keys:
        key_options += [k["key_name"] for k in user_keys]

    if st.session_state.selected_key not in key_options:
        st.session_state.selected_key = default_option

    selected_key = st.selectbox(
        "Key pair name",
        key_options,
        index=key_options.index(st.session_state.selected_key)
    )

    st.session_state.selected_key = selected_key


    # -------- CREATE NEW KEY --------
    if st.button("Create new key pair"):
        st.session_state.show_key_form = not st.session_state.show_key_form


    # -------- KEY FORM --------
    if st.session_state.show_key_form:

        st.subheader("Create SSH Key Pair")

        key_name = st.text_input("Key Pair Name")
        key_format = st.selectbox(
            "Private Key Format",
            [".pem", ".ppk"],
            index=None,
            placeholder="Select format..."
        )

        if st.button("Create Key Pair Now"):

            if not key_name.strip():
                st.warning("Enter key name")

            elif not key_format:
                st.warning("Select format")

            else:
                existing = supabase.table("ssh_keys") \
                    .select("id") \
                    .eq("user_id", st.session_state.user_id) \
                    .eq("key_name", key_name.strip()) \
                    .execute()

                if existing.data:
                    st.warning("Key already exists")

                else:
                    private_key_obj = rsa.generate_private_key(
                        public_exponent=65537,
                        key_size=2048
                    )

                    private_key = private_key_obj.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption()
                    )

                    public_key = private_key_obj.public_key().public_bytes(
                        encoding=serialization.Encoding.OpenSSH,
                        format=serialization.PublicFormat.OpenSSH
                    )

                    supabase.table("ssh_keys").insert({
                        "user_id": st.session_state.user_id,
                        "key_name": key_name.strip(),
                        "public_key": public_key.decode()
                    }).execute()

                    st.session_state.selected_key = key_name.strip()
                    st.session_state.private_key = private_key
                    st.session_state.filename = f"{key_name}{key_format}"
                    st.session_state.pending_download = True
                    st.session_state.show_key_form = False

                    st.success("Key created!")
                    st.rerun()


    # -------- DOWNLOAD --------
    if st.session_state.pending_download:

        col1, col2 = st.columns([2, 1])

        with col1:
            st.download_button(
                "Download Private Key",
                data=st.session_state.private_key,
                file_name=st.session_state.filename
            )

        with col2:
            if st.button("I have downloaded"):
                st.session_state.pending_download = False
                del st.session_state.private_key
                del st.session_state.filename
                st.rerun()


    # -------- CREATE INSTANCE BUTTON --------
    create_clicked = st.button(
        "Create Instance",
        use_container_width=True,
        disabled=st.session_state.creating_instance
    )

    if create_clicked:
        st.session_state.creating_instance = True

        if not instance_name.strip():
            st.warning("Enter instance name")
            st.session_state.creating_instance = False

        elif not os_type:
            st.warning("Select OS")
            st.session_state.creating_instance = False

        elif not instance_type:
            st.warning("Select type")
            st.session_state.creating_instance = False

        else:
            duplicate = supabase.table("instances") \
                .select("id") \
                .eq("user_id", st.session_state.user_id) \
                .eq("name", instance_name.strip()) \
                .execute()

            if duplicate.data:
                st.warning("Instance already exists")
                st.session_state.creating_instance = False

            else:
                key_to_store = None
                if st.session_state.selected_key != default_option:
                    key_to_store = st.session_state.selected_key

                backend_url = "http://127.0.0.1:8000/instances/create"

                payload = {
                    "name": instance_name.strip(),
                    "os": os_type,
                    "instance_type": instance_type   # 🔥 IMPORTANT
                }

                try:
                    with st.spinner("Launching instance..."):
                        response = requests.post(backend_url, json=payload)

                    if response.status_code == 200:
                        result = response.json()

                        public_ip = result["public_ip"]
                        private_ip = result["private_ip"]
                        container_id = result["container_id"]

                        ssh_cmd = f"ssh ubuntu@{public_ip}"

                        supabase.table("instances").insert({
                            "user_id": st.session_state.user_id,
                            "name": instance_name.strip(),
                            "os": os_type,
                            "instance_type": instance_type,
                            "status": "Running",
                            "created_at": datetime.utcnow().isoformat(),
                            "public_ip": public_ip,
                            "private_ip": private_ip,
                            "container_id": container_id,
                            "ssh_command": ssh_cmd,
                            "key_pair": key_to_store
                        }).execute()

                        st.session_state.creating_instance = False
                        st.session_state.reset_form = True
                        st.success("Instance created!")
                        st.rerun()

                    else:
                        st.error("Backend error")
                        st.session_state.creating_instance = False

                except Exception as e:
                    st.error(f"Connection failed: {e}")
                    st.session_state.creating_instance = False


    # -------- INSTANCE LIST --------
    st.subheader("Your Instances")

    response = supabase.table("instances") \
        .select("*") \
        .eq("user_id", st.session_state.user_id) \
        .order("created_at", desc=True) \
        .execute()

    instances = response.data

    if not instances:
        st.info("No instances created yet")
        return

    for inst in instances:

        st.markdown(f"### {inst['name']}")

        c1, c2, c3, c4 = st.columns(4)
        c1.write("OS"); c1.write(inst.get("os", "-"))
        c2.write("Type"); c2.write(inst.get("instance_type", "-"))
        c3.write("Public IP"); c3.write(inst.get("public_ip", "-"))
        c4.write("Private IP"); c4.write(inst.get("private_ip", "-"))

        c5, c6, c7, c8 = st.columns(4)
        c5.write("Container"); c5.code(inst.get("container_id", "-"))
        c6.write("Key Pair"); c6.write(inst.get("key_pair", "—"))
        c7.write("SSH"); c7.code(inst.get("ssh_command", "-"))
        created = inst.get("created_at", "")
        c8.write("Created"); c8.write(created[:16].replace("T", " "))

        a1, a2, a3 = st.columns(3)

        if a1.button("Start", key=f"s_{inst['id']}"):
            requests.post(f"http://127.0.0.1:8000/instances/start/{inst['container_id']}")
            supabase.table("instances").update({"status": "Running"}).eq("id", inst["id"]).execute()
            st.rerun()

        if a2.button("Stop", key=f"st_{inst['id']}"):
            requests.post(f"http://127.0.0.1:8000/instances/stop/{inst['container_id']}")
            supabase.table("instances").update({"status": "Stopped"}).eq("id", inst["id"]).execute()
            st.rerun()

        if a3.button("Terminate", key=f"d_{inst['id']}"):
            requests.delete(f"http://127.0.0.1:8000/instances/terminate/{inst['container_id']}")
            supabase.table("instances").delete().eq("id", inst["id"]).execute()
            st.rerun()

        st.divider()