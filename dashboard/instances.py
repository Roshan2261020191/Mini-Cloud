import streamlit as st
from supabase_client import supabase
from datetime import datetime
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import random
import uuid
import requests
import ipaddress
import os


# ==========  OS and Instance Types ==========
OS_CONFIG = {
    "Ubuntu": ["t2.nano", "t2.micro"],
    "Alpine Linux": ["t2.nano", "t2.micro"],
    "Debian Slim": ["t2.nano", "t2.micro"],
    "Ubuntu Minimal": ["t2.nano", "t2.micro"],
    "BusyBox": ["t2.nano", "t2.micro"]
}

# OS to SSH user mapping - ALL USE ROOT
OS_SSH_USER = {
    "Ubuntu": "ubuntu",
    "Alpine Linux": "root",
    "Debian Slim": "admin",
    "Ubuntu Minimal": "ubuntu",
    "BusyBox": "root"
}


# ========== IP ALLOCATION - 100% DYNAMIC ==========

def get_next_available_private_ip(subnet_cidr, used_ips):
    """Allocate REAL private IP from Subnet CIDR"""
    try:
        network = ipaddress.ip_network(subnet_cidr, strict=False)
        
        reserved_ips = [
            str(network.network_address),
            str(network.network_address + 1),
            str(network.network_address + 2),
            str(network.network_address + 3),
            str(network.broadcast_address)
        ]
        
        for ip in network.hosts():
            ip_str = str(ip)
            if ip_str not in reserved_ips and ip_str not in used_ips:
                return ip_str
        
        return None
    except Exception as e:
        print(f"Error allocating private IP: {e}")
        return None


def get_next_available_public_ip(used_public_ips):
    """Allocate REAL public IP from NAT pool"""
    try:
        nat_pools = [
            "192.0.2.0/24",
            "198.51.100.0/24",
            "203.0.113.0/24"
        ]
        
        for cidr in nat_pools:
            network = ipaddress.ip_network(cidr, strict=False)
            
            reserved = [
                str(network.network_address),
                str(network.broadcast_address)
            ]
            
            for ip in network.hosts():
                ip_str = str(ip)
                if ip_str not in reserved and ip_str not in used_public_ips:
                    return ip_str
        
        return None
    except Exception as e:
        print(f"Error allocating public IP: {e}")
        return None


def allocate_nat_port(public_ip):
    """
    Allocate unique NAT port with database tracking.
    Port range: 20000-29999 (10,000 ports available)
    """
    try:
        existing = supabase.table("nat_mappings").select("nat_port").eq("public_ip", public_ip).execute()
        
        if existing.data:
            return existing.data[0]['nat_port']
        
        all_mappings = supabase.table("nat_mappings").select("nat_port").execute()
        used_ports = {mapping['nat_port'] for mapping in all_mappings.data if mapping.get('nat_port')}
        
        for port in range(20000, 30000):
            if port not in used_ports:
                return port
        
        raise Exception("No available NAT ports!")
        
    except Exception as e:
        print(f"Error allocating NAT port: {e}")
        raise


# ========== OVERLAP DETECTION (AWS LOGIC) ==========

def check_subnet_overlap(new_subnet_cidr, vpc_id):
    """
    Check if new subnet overlaps with existing subnets in the SAME VPC.
    AWS Behavior: Overlap allowed across different VPCs, blocked within same VPC.
    """
    try:
        new_network = ipaddress.ip_network(new_subnet_cidr, strict=False)
        
        existing_subnets = supabase.table("subnets") \
            .select("cidr, name") \
            .eq("vpc_id", vpc_id) \
            .execute()
        
        if not existing_subnets.data:
            return True, None
        
        for subnet in existing_subnets.data:
            existing_cidr = subnet['cidr']
            existing_name = subnet['name']
            existing_network = ipaddress.ip_network(existing_cidr, strict=False)
            
            if new_network.overlaps(existing_network):
                error_msg = f"Overlaps with existing subnet '{existing_name}' ({existing_cidr}) in this VPC"
                return False, error_msg
        
        return True, None
        
    except ValueError as e:
        return False, f"Invalid CIDR format: {str(e)}"
    except Exception as e:
        return False, f"Error checking overlap: {str(e)}"


# ========== VPC/SUBNET CALCULATIONS ==========

def calculate_vpc_ips(cidr_block):
    """Calculate total IPs for VPC (NO -5)"""
    try:
        network = ipaddress.ip_network(cidr_block, strict=False)
        return network.num_addresses
    except ValueError:
        return 0


def calculate_subnet_ips(cidr_block):
    """Calculate USABLE IPs for Subnet (WITH -5)"""
    try:
        network = ipaddress.ip_network(cidr_block, strict=False)
        total_ips = network.num_addresses
        
        if network.prefixlen == 32:
            return 1
        
        available = total_ips - 5
        return max(0, available)
    except ValueError:
        return 0


def calculate_subnet_total_ips(cidr_block):
    """Calculate TOTAL IPs for VPC accounting"""
    try:
        network = ipaddress.ip_network(cidr_block, strict=False)
        return network.num_addresses
    except ValueError:
        return 0


def validate_subnet_in_vpc(subnet_cidr, vpc_cidr):
    """Validate subnet is inside VPC"""
    try:
        vpc_network = ipaddress.ip_network(vpc_cidr, strict=False)
        subnet_network = ipaddress.ip_network(subnet_cidr, strict=False)
        return subnet_network.subnet_of(vpc_network)
    except ValueError:
        return False


def show_dashboard():
    st.write("CURRENT USER:", st.session_state.user_id)
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

    # -------- SESSION STATE --------
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
    if "show_vpc_form" not in st.session_state:
        st.session_state.show_vpc_form = False
    if "show_subnet_form" not in st.session_state:
        st.session_state.show_subnet_form = False
    if "action_message" not in st.session_state:
        st.session_state.action_message = None
    if "refresh_vpcs" not in st.session_state:
        st.session_state.refresh_vpcs = 0

    # -------- RESET FORM --------
    if st.session_state.reset_form:
        st.session_state.instance_name_input = ""
        st.session_state.selected_os = None
        st.session_state.selected_instance_type = None
        st.session_state.selected_key = default_option
        st.session_state.reset_form = False

    # -------- TABS --------
    tab1, tab2, tab3 = st.tabs(["🖥️ Instances", "🌐 VPC & Subnets", "🔑 SSH Keys"])

    # ==================== TAB 1: INSTANCES ====================
    with tab1:
        st.subheader("⚡ Launch New Instance")

        with st.expander("📋 Instance Configuration", expanded=True):
            col1, col2 = st.columns(2)

            with col1:
                instance_name = st.text_input("Instance Name", key="instance_name_input", placeholder="e.g., web-server-01")

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

            # -------- FETCH VPCs --------
            vpc_response = supabase.table("vpcs").select("*").eq("user_id", st.session_state.user_id).execute()
            user_vpcs = vpc_response.data if vpc_response.data else []

            vpc_options = []
            if user_vpcs:
                vpc_options = [f"{vpc['name']} ({vpc['cidr']}) - {vpc.get('available_ips', 0)} IPs" for vpc in user_vpcs]

            col3, col4 = st.columns(2)

            with col3:
                selected_vpc_display = st.selectbox(
                    "Select VPC",
                    vpc_options,
                    index=None,
                    placeholder="Choose VPC..." if vpc_options else "No VPCs - Create in VPC tab",
                    key=f"vpc_select_{st.session_state.refresh_vpcs}"
                )

            selected_vpc_id = None
            selected_vpc_name_final = None
            if selected_vpc_display:
                selected_vpc_name_final = selected_vpc_display.split(" (")[0]
                selected_vpc_id = next((vpc['id'] for vpc in user_vpcs if vpc['name'] == selected_vpc_name_final), None)

            # -------- FETCH SUBNETS --------
            selected_subnet_id = None
            selected_subnet_name_final = None
            
            with col4:
                if selected_vpc_id:
                    subnet_response = supabase.table("subnets") \
                    .select("*") \
                    .eq("user_id", st.session_state.user_id) \
                    .execute()
                    user_subnets = [
                        s for s in (subnet_response.data or [])
                        if s["vpc_id"] == selected_vpc_id]

                    subnet_options = []
                    if user_subnets:
                        subnet_options = [f"{subnet['name']} ({subnet['cidr']}) - {subnet['available_ips']} IPs" for subnet in user_subnets]

                    selected_subnet_display = st.selectbox(
                        "Select Subnet",
                        subnet_options,
                        index=None,
                        placeholder="Choose Subnet..." if subnet_options else "No Subnets in VPC",
                        key=f"subnet_select_{st.session_state.refresh_vpcs}"
                    )

                    if selected_subnet_display:
                        selected_subnet_name_final = selected_subnet_display.split(" (")[0]
                        selected_subnet_id = next((subnet['id'] for subnet in user_subnets if subnet['name'] == selected_subnet_name_final), None)
                else:
                    st.selectbox("Select Subnet", [], index=None, placeholder="Select VPC first", disabled=True)

            # -------- FETCH KEYS --------
            key_response = supabase.table("ssh_keys").select("key_name").eq("user_id", st.session_state.user_id).execute()
            user_keys = key_response.data if key_response.data else []

            key_options = [default_option]
            if user_keys:
                key_options += [k["key_name"] for k in user_keys]

            if st.session_state.selected_key not in key_options:
                st.session_state.selected_key = default_option

            selected_key = st.selectbox(
                "🔐 SSH Key Pair",
                key_options,
                index=key_options.index(st.session_state.selected_key)
            )

            st.session_state.selected_key = selected_key

            if st.button("➕ Create new key pair", use_container_width=True):
                st.session_state.show_key_form = not st.session_state.show_key_form

        # -------- KEY FORM --------
        if st.session_state.show_key_form:
            with st.expander("🔑 Create SSH Key Pair", expanded=True):
                key_name = st.text_input("Key Pair Name")
                key_format = st.selectbox("Private Key Format", [".pem", ".ppk"], index=None, placeholder="Select format...")

                if st.button("Create Key Pair Now"):
                    if not key_name.strip():
                        st.warning("Enter key name")
                    elif not key_format:
                        st.warning("Select format")
                    else:
                        existing = supabase.table("ssh_keys").select("id").eq("user_id", st.session_state.user_id).eq("key_name", key_name.strip()).execute()

                        if existing.data:
                            st.warning("Key already exists")
                        else:
                            private_key_obj = rsa.generate_private_key(public_exponent=65537, key_size=2048)
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
                                "public_key": public_key.decode(),
                                "key_format": key_format 
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
            st.warning("⚠️ Download your private key now! You won't be able to download it again.")
            col1, col2 = st.columns([3, 1])

            with col1:
                st.download_button("⬇️ Download Private Key", data=st.session_state.private_key, file_name=st.session_state.filename, use_container_width=True)

            with col2:
                if st.button("✅ Done", use_container_width=True):
                    st.session_state.pending_download = False
                    del st.session_state.private_key
                    del st.session_state.filename
                    st.rerun()

        # -------- CREATE INSTANCE --------
        st.markdown("---")
        create_clicked = st.button("🚀 Launch Instance", use_container_width=True, disabled=st.session_state.creating_instance, type="primary")

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
            elif not selected_vpc_id:
                st.warning("Select VPC")
                st.session_state.creating_instance = False
            elif not selected_subnet_id:
                st.warning("Select Subnet")
                st.session_state.creating_instance = False
            else:
                duplicate = supabase.table("instances").select("id").eq("user_id", st.session_state.user_id).eq("name", instance_name.strip()).execute()

                if duplicate.data:
                    st.warning("Instance already exists")
                    st.session_state.creating_instance = False
                else:
                    subnet_data = supabase.table("subnets").select("*").eq("id", selected_subnet_id).execute()
                    
                    if not subnet_data.data:
                        st.error("Subnet not found!")
                        st.session_state.creating_instance = False
                    elif subnet_data.data[0]['available_ips'] <= 0:
                        st.error("No available IPs in this subnet!")
                        st.session_state.creating_instance = False
                    else:
                        subnet = subnet_data.data[0]
                        subnet_cidr = subnet['cidr']
                        used_ips = subnet.get('used_ips', []) or []
                        
                        private_ip = get_next_available_private_ip(subnet_cidr, used_ips)
                        
                        if not private_ip:
                            st.error("Failed to allocate private IP!")
                            st.session_state.creating_instance = False
                        else:
                            all_instances = supabase.table("instances").select("public_ip").execute()
                            used_public_ips = [inst['public_ip'] for inst in all_instances.data if inst.get('public_ip')]
                            
                            public_ip = get_next_available_public_ip(used_public_ips)
                            
                            if not public_ip:
                                st.error("Failed to allocate public IP!")
                                st.session_state.creating_instance = False
                            else:
                                try:
                                    nat_port = allocate_nat_port(public_ip)
                                    ssh_user = OS_SSH_USER.get(os_type, "root")
                                    
                                    # Fetch public key if user selected one
                                    public_key_to_inject = None
                                    key_to_store = None
                                    
                                    if st.session_state.selected_key != default_option:
                                        key_to_store = st.session_state.selected_key
                                        
                                        # Fetch public key from database
                                        key_to_store = None
                                        key_format = None
                                        public_key_to_inject = None

                                        if st.session_state.selected_key != default_option:
                                            key_to_store = st.session_state.selected_key

                                            key_data = supabase.table("ssh_keys") \
                                                .select("public_key, key_format") \
                                                .eq("user_id", st.session_state.user_id) \
                                                .eq("key_name", key_to_store) \
                                                .execute()
                                        
                                            if key_data.data:
                                                record = key_data.data[0]
                                                public_key_to_inject = record["public_key"]
                                                key_format = record["key_format"]
                                            else:
                                                raise Exception("SSH key not found or invalid")

                                    BASE_BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
                                    backend_url = f"{BASE_BACKEND_URL}/instances/create"
                                    
                                    payload = {
                                        "name": instance_name.strip(),
                                        "os": os_type,
                                        "instance_type": instance_type,
                                        "subnet_id": selected_subnet_id,
                                        "subnet_cidr": subnet_cidr,
                                        "private_ip": private_ip,
                                        "public_ip": public_ip,
                                        "nat_port": nat_port,
                                        "public_key": public_key_to_inject  # Include SSH key
                                    }

                                    with st.spinner(f"🔄 Launching instance (may take 30-60 seconds on first run)..."):
                                        response = requests.post(backend_url, json=payload, timeout=120)

                                    if response.status_code == 200:
                                        result = response.json()
                                        st.write("BACKEND URL:", backend_url)
                                        st.write("BACKEND RESPONSE:", result)
                                        container_id = result["container_id"]
                                        
                                        # Updated SSH command
                                        ssh_host = result.get("ssh_host")
                                        ssh_port = result.get("ssh_port")
                                       

                                        if public_key_to_inject and key_format == ".pem":
                                            ssh_cmd = f'ssh -i "{key_to_store}.pem" -p {ssh_port} {ssh_user}@{ssh_host}'
                                        elif public_key_to_inject and key_format == ".ppk":
                                            ssh_cmd = "None"      
                                        else:
                                            ssh_cmd = f"ssh -p {ssh_port} {ssh_user}@{ssh_host}"

                                        instance_response = supabase.table("instances").insert({
                                             "user_id": st.session_state.user_id,
                                             "name": instance_name.strip(),
                                             "os": os_type,
                                             "instance_type": instance_type,
                                             "status": "Running",
                                             "created_at": datetime.utcnow().isoformat(),

                                             "public_ip": public_ip,
                                             "private_ip": private_ip,
                                             "container_id": container_id,

                                             "nat_port": nat_port,

                                             # ✅ SOURCE OF TRUTH
                                             "ssh_host": ssh_host,
                                             "ssh_port": ssh_port,

                                             "key_pair": key_to_store,
                                             "key_format": key_format,

                                             "vpc_id": selected_vpc_id,
                                             "subnet_id": selected_subnet_id,
                                             "vpc_name": selected_vpc_name_final,
                                             "subnet_name": selected_subnet_name_final
                                        }).execute()

                                        instance_id = instance_response.data[0]['id']

                                        supabase.table("nat_mappings").insert({
                                            "public_ip": public_ip,
                                            "private_ip": private_ip,
                                            "nat_port": nat_port,
                                            "instance_id": instance_id
                                        }).execute()

                                        used_ips.append(private_ip)
                                        supabase.table("subnets").update({
                                            "available_ips": subnet['available_ips'] - 1,
                                            "used_ips": used_ips
                                        }).eq("id", selected_subnet_id).execute()

                                        st.session_state.creating_instance = False
                                        st.session_state.reset_form = True
                                        st.session_state.refresh_vpcs += 1
                                        # UPDATED SUCCESS MESSAGE - Will auto-disappear
                                        st.session_state.action_message = ("success", f"✅ Instance '{instance_name.strip()}' created successfully!")
                                        st.rerun()
                                    else:
                                        st.error(f"Backend error: {response.text}")
                                        st.session_state.creating_instance = False
                                        
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                                    st.session_state.creating_instance = False

        # -------- INSTANCE LIST --------
        st.markdown("---")
        st.subheader("📊 Your Running Instances")

        # Show auto-disappearing success message
        if st.session_state.action_message:
            msg_type, msg_text = st.session_state.action_message
            if msg_type == "success":
                success_placeholder = st.empty()
                success_placeholder.success(msg_text)
                # Auto-clear after rerun
                st.session_state.action_message = None
                import time
                time.sleep(3)
                success_placeholder.empty()
            elif msg_type == "error":
                st.error(msg_text)
                st.session_state.action_message = None

        response = supabase.table("instances").select("*").eq("user_id", st.session_state.user_id).order("created_at", desc=True).execute()
        instances = response.data

        if not instances:
            st.info("💡 No instances created yet!")
        else:
            for inst in instances:
                with st.container():
                    col_header1, col_header2 = st.columns([3, 1])
                    with col_header1:
                        status_color = "🟢" if inst.get("status") == "Running" else "🔴"
                        st.markdown(f"### {status_color} {inst['name']}")
                    with col_header2:
                        st.markdown(f"**Status:** `{inst.get('status', 'Unknown')}`")

                    st.markdown("##### 💻 System")
                    sys_col1, sys_col2, sys_col3, sys_col4 = st.columns(4)
                    
                    with sys_col1:
                        st.write("**OS**")
                        st.info(inst.get("os", "-"))
                    with sys_col2:
                        st.write("**Type**")
                        st.info(inst.get("instance_type", "-"))
                    with sys_col3:
                        st.write("**VPC**")
                        st.info(inst.get("vpc_name", "-"))
                    with sys_col4:
                        st.write("**Subnet**")
                        st.info(inst.get("subnet_name", "-"))

                    # UPDATED: REMOVED NAT PORT DISPLAY
                    st.markdown("##### 🌐 Network (REAL IPs)")
                    
                    net_col1, net_col2 = st.columns(2)
                    
                    with net_col1:
                        st.write("**Public IP**")
                        st.code(inst.get("public_ip", "-"), language=None)
                    
                    with net_col2:
                        st.write("**Private IP**")
                        st.code(inst.get("private_ip", "-"), language=None)

                    # UPDATED: SSH ACCESS
                    st.markdown("##### 🔐 SSH Access")

                ssh_host = inst.get("ssh_host")
                ssh_port = inst.get("ssh_port")
                key_format = inst.get("key_format")
                key_name = inst.get("key_pair")
                os_type = inst.get("os")

                OS_SSH_USER = {
                    "Ubuntu": "ubuntu",
                    "Ubuntu Minimal": "ubuntu",
                    "Debian Slim": "debian",
                    "Alpine Linux": "root",
                    "BusyBox": "root"
                }

                ssh_user = OS_SSH_USER.get(os_type, "root")

                # Instance status check
                if inst.get("status") != "Running":
                    st.warning("⚠️ Instance is stopped. Start it to connect.")

                elif not ssh_host or not ssh_port:
                    st.error("❌ SSH endpoint not available")

                else:
                    # ✅ PEM → Show SSH command
                    if key_format == ".pem":
                        ssh_cmd = f'ssh -i "{key_name}.pem" -p {ssh_port} {ssh_user}@{ssh_host}'
                        st.code(ssh_cmd, language="bash")

                    # ✅ PPK → Show PuTTY instructions
                    elif key_format == ".ppk":
                        st.warning("⚠️ Use PuTTY to connect")

                        st.code(f"""
                Host Name: {ssh_host}
                Port: {ssh_port}
                User: {ssh_user}

                Steps:
                1. Open PuTTY
                2. Enter Host Name and Port
                3. Go to Connection → SSH → Auth
                4. Browse and select {key_name}.ppk
                5. Click Open
                """, language="text")

                    # ❌ Invalid case
                    else:
                        st.error("Invalid key format")      

                    # ACTIONS WITH CONNECT BUTTON

                    st.markdown("##### ⚙️ Actions")
                    a1, a2, a3, a4, _ = st.columns([1, 1, 1, 1, 2])
                    
                    with a1:
                        container_id = inst['container_id']

                        # ✅ Default (local)
                        backend_url = "http://localhost:8000"
                        
                        # ✅ If ngrok is used
                        if os.getenv("BACKEND_URL"):
                            backend_url = os.getenv("BACKEND_URL")
                    
                        terminal_url = f"{backend_url}/terminal/{container_id}"
                        
                        try:
                            st.link_button(
                                "🔗 Connect",
                                terminal_url,
                                use_container_width=True
                            )
                        except AttributeError:
                            if st.button("🔗 Connect", key=f"c_{inst['id']}", use_container_width=True):
                                st.session_state[f"show_url_{inst['id']}"] = True
                            
                            if st.session_state.get(f"show_url_{inst['id']}", False):
                                st.code(terminal_url)
                                st.caption("Copy and open in browser")

                    with a2:
                        if st.button("▶️ Start", key=f"s_{inst['id']}", use_container_width=True):
                            BASE_BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
                            
                            try:
                                res = requests.post(
                                    f"{BASE_BACKEND_URL}/instances/start/{inst['container_id']}",
                                    timeout=30
                                )
                                
                                if res.status_code == 200:
                                    data = res.json()
                                    supabase.table("instances").update({
                                        "status": "Running",
                                        "ssh_host": data.get("ssh_host"),
                                        "ssh_port": data.get("ssh_port")
                                    }).eq("id", inst["id"]).execute()
                                    st.success("✅ Instance started")
                                else:
                                    st.error("❌ Failed to start instance")
                                    
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
                            
                            st.rerun()
                    with a3:
                        if st.button("⏸️ Stop", key=f"st_{inst['id']}", use_container_width=True):
                            BASE_BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
                            
                            try:
                                res = requests.post(
                                    f"{BASE_BACKEND_URL}/instances/stop/{inst['container_id']}",
                                    timeout=30
                                )

                                if res.status_code == 200:
                                    supabase.table("instances").update({
                                        "status": "Stopped",
                                        "ssh_host": None,
                                        "ssh_port": None
                                    }).eq("id", inst["id"]).execute()
                                    st.success("✅ Instance stopped")
                                else:
                                    st.error("❌ Failed to stop instance")
                                    
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
                            
                            st.rerun() 

                    with a4:
                        if st.button("🗑️ Terminate", key=f"d_{inst['id']}", use_container_width=True):
                            supabase.table("instances").delete().eq("id", inst["id"]).execute()
                            
                            subnet_id = inst.get("subnet_id")
                            private_ip = inst.get("private_ip")
                            
                            if subnet_id and private_ip:
                                try:
                                    subnet_data = supabase.table("subnets").select("available_ips, used_ips").eq("id", subnet_id).execute()
                                    if subnet_data.data:
                                        current_ips = subnet_data.data[0]['available_ips']
                                        used_ips = subnet_data.data[0].get('used_ips', []) or []
                                        
                                        if private_ip in used_ips:
                                            used_ips.remove(private_ip)
                                        
                                        supabase.table("subnets").update({
                                            "available_ips": current_ips + 1,
                                            "used_ips": used_ips
                                        }).eq("id", subnet_id).execute()
                                except:
                                    pass
                            
                            try:
                                requests.delete(f"http://127.0.0.1:8000/instances/terminate/{inst['container_id']}", timeout=30)
                            except:
                                pass
                            
                            st.session_state.refresh_vpcs += 1
                            st.rerun()

                    st.markdown("---")

    # ==================== TAB 2: VPC & SUBNETS ====================
    with tab2:
        col_vpc, col_subnet = st.columns(2)

        with col_vpc:
            st.subheader("🌐 VPCs")

            if st.button("➕ Create VPC"):
                st.session_state.show_vpc_form = not st.session_state.show_vpc_form

            if st.session_state.show_vpc_form:
                vpc_name = st.text_input("VPC Name", key="vpc_name_input")
                vpc_cidr = st.text_input("CIDR Block", placeholder="e.g., 10.0.0.0/16", key="vpc_cidr_input")
                
                if vpc_cidr.strip():
                    vpc_total = calculate_vpc_ips(vpc_cidr.strip())
                    if vpc_total > 0:
                        st.info(f"📊 **{vpc_total:,}** total IPs")

                if st.button("Create VPC Now"):
                    if not vpc_name.strip():
                        st.warning("Enter VPC name")
                    elif not vpc_cidr.strip():
                        st.warning("Enter CIDR")
                    else:
                        existing = supabase.table("vpcs").select("id").eq("user_id", st.session_state.user_id).eq("name", vpc_name.strip()).execute()

                        if existing.data:
                            st.warning("VPC exists")
                        else:
                            total_ips = calculate_vpc_ips(vpc_cidr.strip())
                            
                            if total_ips == 0:
                                st.error("Invalid CIDR")
                            else:
                                supabase.table("vpcs").insert({
                                    "user_id": st.session_state.user_id,
                                    "name": vpc_name.strip(),
                                    "cidr": vpc_cidr.strip(),
                                    "total_ips": total_ips,
                                    "available_ips": total_ips,
                                    "created_at": datetime.utcnow().isoformat()
                                }).execute()

                                st.session_state.show_vpc_form = False
                                st.session_state.refresh_vpcs += 1
                                st.success(f"✅ VPC created!")
                                st.rerun()

            st.markdown("### Your VPCs")
            vpc_list = supabase.table("vpcs").select("*").eq("user_id", st.session_state.user_id).execute()

            if not vpc_list.data:
                st.info("No VPCs")
            else:
                for vpc in vpc_list.data:
                    with st.container():
                        st.markdown(f"**{vpc['name']}**")
                        st.write(f"CIDR: {vpc['cidr']}")
                        st.write(f"IPs: {vpc.get('available_ips', 0):,} / {vpc.get('total_ips', 0):,}")

                        if st.button("🗑️ Delete", key=f"del_vpc_{vpc['id']}"):
                            instances_check = supabase.table("instances").select("id").eq("vpc_id", vpc['id']).execute()

                            if instances_check.data:
                                st.error("Has instances!")
                            else:
                                supabase.table("subnets").delete().eq("vpc_id", vpc['id']).execute()
                                supabase.table("vpcs").delete().eq("id", vpc['id']).execute()
                                st.session_state.refresh_vpcs += 1
                                st.success("✅ VPC and subnets deleted!")
                                st.rerun()

                        st.divider()

        with col_subnet:
            st.subheader("📡 Subnets")

            vpc_for_subnet = supabase.table("vpcs").select("*").eq("user_id", st.session_state.user_id).execute()

            if not vpc_for_subnet.data:
                st.info("Create VPC first")
                st.session_state.show_subnet_form = False
            else:
                if st.button("➕ Create Subnet"):
                    st.session_state.show_subnet_form = not st.session_state.show_subnet_form

                if st.session_state.show_subnet_form:
                    vpc_options_subnet = [f"{vpc['name']} ({vpc['cidr']}) - {vpc.get('available_ips', 0):,} IPs" for vpc in vpc_for_subnet.data]
                    selected_vpc_for_subnet = st.selectbox("Select VPC", vpc_options_subnet, key=f"subnet_vpc_select_{st.session_state.refresh_vpcs}")

                    subnet_name = st.text_input("Subnet Name", key="subnet_name_input")
                    subnet_cidr = st.text_input("CIDR Block", placeholder="e.g., 10.0.1.0/24", key="subnet_cidr_input")
                    
                    subnet_ips = 0
                    subnet_total_ips = 0
                    is_valid_subnet = False
                    has_overlap = False
                    validation_messages = []
                    
                    if subnet_cidr.strip() and selected_vpc_for_subnet:
                        selected_vpc_name = selected_vpc_for_subnet.split(" (")[0]
                        vpc_data = next((vpc for vpc in vpc_for_subnet.data if vpc['name'] == selected_vpc_name), None)
                        
                        if vpc_data:
                            vpc_cidr = vpc_data['cidr']
                            vpc_id = vpc_data['id']
                            
                            is_inside_vpc = validate_subnet_in_vpc(subnet_cidr.strip(), vpc_cidr)
                            
                            if not is_inside_vpc:
                                validation_messages.append(("error", f"❌ Subnet MUST be inside VPC CIDR ({vpc_cidr})"))
                            else:
                                validation_messages.append(("success", f"✅ Inside VPC ({vpc_cidr})"))
                                
                                overlap_ok, overlap_error = check_subnet_overlap(subnet_cidr.strip(), vpc_id)
                                
                                if not overlap_ok:
                                    validation_messages.append(("error", f"❌ {overlap_error}"))
                                    has_overlap = True
                                else:
                                    validation_messages.append(("success", "✅ No overlap in this VPC"))
                                    
                                    subnet_ips = calculate_subnet_ips(subnet_cidr.strip())
                                    subnet_total_ips = calculate_subnet_total_ips(subnet_cidr.strip())
                                    
                                    if subnet_ips > 0:
                                        validation_messages.append(("info", f"📊 **{subnet_ips:,}** usable IPs ({subnet_total_ips:,} total, AWS reserves 5)"))
                                        is_valid_subnet = True
                                    else:
                                        validation_messages.append(("error", "❌ Invalid CIDR"))
                    
                    for msg_type, msg_text in validation_messages:
                        if msg_type == "success":
                            st.success(msg_text)
                        elif msg_type == "error":
                            st.error(msg_text)
                        elif msg_type == "info":
                            st.info(msg_text)

                    if st.button("Create Subnet Now"):
                        if not subnet_name.strip():
                            st.warning("⚠️ Enter name")
                        elif not subnet_cidr.strip():
                            st.warning("⚠️ Enter CIDR")
                        elif not is_valid_subnet:
                            st.error("❌ Validation failed!")
                        elif has_overlap:
                            st.error("❌ Overlap detected!")
                        elif subnet_ips == 0:
                            st.error("❌ No usable IPs")
                        else:
                            selected_vpc_name = selected_vpc_for_subnet.split(" (")[0]
                            vpc_id = next((vpc['id'] for vpc in vpc_for_subnet.data if vpc['name'] == selected_vpc_name), None)
                            vpc_data = next((vpc for vpc in vpc_for_subnet.data if vpc['id'] == vpc_id), None)
                            vpc_available = vpc_data.get('available_ips', 0)
                            
                            if subnet_total_ips > vpc_available:
                                st.error(f"❌ Need {subnet_total_ips:,}, VPC has {vpc_available:,}")
                            else:
                                existing = supabase.table("subnets").select("id").eq("vpc_id", vpc_id).eq("name", subnet_name.strip()).execute()

                                if existing.data:
                                    st.warning("⚠️ Name exists")
                                else:
                                    final_ok, final_error = check_subnet_overlap(subnet_cidr.strip(), vpc_id)
                                    
                                    if not final_ok:
                                        st.error(f"❌ {final_error}")
                                    else:
                                        supabase.table("subnets").insert({
                                            "user_id": st.session_state.user_id, 
                                            "vpc_id": vpc_id,
                                            "name": subnet_name.strip(),
                                            "cidr": subnet_cidr.strip(),
                                            "available_ips": subnet_ips,
                                            "created_at": datetime.utcnow().isoformat()
                                        }).execute()
                                        
                                        new_vpc_available = vpc_available - subnet_total_ips
                                        supabase.table("vpcs").update({
                                            "available_ips": new_vpc_available
                                        }).eq("id", vpc_id).execute()

                                        st.session_state.show_subnet_form = False
                                        st.session_state.refresh_vpcs += 1
                                        st.success(f"✅ Created! VPC has {new_vpc_available:,} IPs left")
                                        st.rerun()

                st.markdown("### Your Subnets")
                subnet_list = supabase.table("subnets") \
                    .select("*, vpcs(name)") \
                    .eq("user_id", st.session_state.user_id) \
                    .execute()   
                       
                if not subnet_list.data:
                    st.info("No subnets")
                else:
                    for subnet in subnet_list.data:
                        with st.container():
                            st.markdown(f"**{subnet['name']}**")
                            st.write(f"VPC: {subnet['vpcs']['name']}")
                            st.write(f"CIDR: {subnet['cidr']}")
                            st.write(f"Available: {subnet['available_ips']:,}")

                            if st.button("🗑️ Delete", key=f"del_sub_{subnet['id']}"):
                                instances_check = supabase.table("instances").select("id").eq("subnet_id", subnet['id']).execute()

                                if instances_check.data:
                                    st.error("Has instances!")
                                else:
                                    total = calculate_subnet_total_ips(subnet['cidr'])
                                    vpc_id = subnet['vpc_id']
                                    
                                    supabase.table("subnets").delete().eq("id", subnet['id']).execute()
                                    
                                    vpc_data = supabase.table("vpcs").select("available_ips").eq("id", vpc_id).execute()
                                    if vpc_data.data:
                                        supabase.table("vpcs").update({
                                            "available_ips": vpc_data.data[0]['available_ips'] + total
                                        }).eq("id", vpc_id).execute()
                                    
                                    st.session_state.refresh_vpcs += 1
                                    st.success(f"✅ Deleted! {total:,} IPs returned")
                                    st.rerun()

                            st.divider()

    # ==================== TAB 3: SSH KEYS ====================
    with tab3:
        st.subheader("🔑 SSH Keys")

        key_list = supabase.table("ssh_keys").select("*").eq("user_id", st.session_state.user_id).execute()

        if not key_list.data:
            st.info("No keys")
        else:
            for key in key_list.data:
                with st.container():
                    st.markdown(f"**{key['key_name']}**")
                    st.code(key['public_key'])

                    if st.button("🗑️ Delete", key=f"del_key_{key['id']}"):
                        supabase.table("ssh_keys").delete().eq("id", key['id']).execute()
                        st.rerun()

                    st.divider()