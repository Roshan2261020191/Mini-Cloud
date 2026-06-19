import docker
from typing import Optional

# Container resource limits
INSTANCE_TYPES = {
    "t2.nano": {"cpu": 0.25, "memory": "512m"},
    "t2.micro": {"cpu": 0.5, "memory": "1g"}
}

# Pre-built Docker Hub images - NO TAG (defaults to latest)
OS_IMAGE_MAP = {
    "Ubuntu": "roshan2261020191/minicloud-ubuntu:ssh",
    "Alpine Linux": "roshan2261020191/minicloud-alpine:ssh",
    "Debian Slim": "roshan2261020191/minicloud-debian-slim:ssh",
    "Ubuntu Minimal": "roshan2261020191/minicloud-ubuntu-minimal:ssh",
    "BusyBox": "roshan2261020191/minicloud-busybox:ssh"
}


class DockerService:
    def __init__(self):
        self.client = docker.from_env()

    def _get_or_create_network(self, subnet_id: str, subnet_cidr: str):
        """Get or create Docker network for subnet with overlap prevention"""
        network_name = f"minicloud-subnet-{subnet_id}"

        # Check if network with this name already exists
        try:
            existing_network = self.client.networks.get(network_name)
            print(f"♻️ Reusing existing network: {network_name}")
            return existing_network
        except docker.errors.NotFound:
            pass

        # Check for CIDR overlap with existing networks
        #for net in self.client.networks.list():
         #   try:
          #      ipam = net.attrs.get("IPAM", {})
           #     configs = ipam.get("Config", [])
            #    for cfg in configs:
             #       if cfg.get("Subnet") == subnet_cidr:
              #          print(f"♻️ Reusing network with matching CIDR: {net.name} ({subnet_cidr})")
               #         return net
            #except Exception:
             #   pass

        # Create new network
        print(f"📡 Creating network: {network_name} ({subnet_cidr})")

        ipam_pool = docker.types.IPAMPool(subnet=subnet_cidr)
        ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])

        return self.client.networks.create(
            network_name,
            driver="bridge",
            ipam=ipam_config,
            labels={"mini-cloud": "true", "subnet": subnet_cidr}
        )

    def _pull_image_if_needed(self, image_name: str):
        """Pull Docker image from Docker Hub if not present locally"""
        try:
            # Check if image exists locally
            self.client.images.get(image_name)
            print(f"✅ Image exists locally: {image_name}")
        except docker.errors.ImageNotFound:
            print(f"📥 Pulling image from Docker Hub: {image_name}")
            print(f"⏳ This may take 10-30 seconds...")
            try:
                # Pull image without explicit tag (Docker uses 'latest' by default)
                self.client.images.pull(image_name)
                print(f"✅ Successfully pulled: {image_name}")
            except docker.errors.NotFound:
                raise Exception(
                    f"Image not found on Docker Hub: {image_name}\n"
                    f"Please verify the image exists and is public."
                )
            except Exception as e:
                print(f"❌ Failed to pull image: {e}")
                raise Exception(
                    f"Could not pull image {image_name} from Docker Hub.\n"
                    f"Error: {str(e)}"
                )

    def create_container(
        self,
        name: str,
        os: str,
        instance_type: str,
        subnet_cidr: str,
        subnet_id: str,
        private_ip: str,
        public_ip: str,
        nat_port: int,
        public_key: Optional[str] = None
    ) -> str:
        """
        Create Docker container from pre-built image
        
        Args:
            name: Instance name
            os: Operating system
            instance_type: Instance type (t2.nano, t2.micro)
            subnet_cidr: Subnet CIDR
            private_ip: Private IP address
            public_ip: Public IP address (for display/tracking)
            nat_port: NAT port for SSH
            public_key: SSH public key (optional)
        
        Returns:
            Container ID (short form)
        """

        # Get image from mapping
        image_name = OS_IMAGE_MAP.get(os)
        if not image_name:
            raise Exception(f"Unsupported OS: {os}")

        # Pull image if needed
        try:
            self.client.images.get(image_name)
            print("✅ Image already exists")
        except:
            print("📥 Pulling image (first time)...")
            self.client.images.pull(image_name)    

        # Get resources
        resources = INSTANCE_TYPES.get(instance_type, INSTANCE_TYPES["t2.nano"])

        try:
            print(f"\n🚀 Creating Instance:")
            print(f"   Name       : {name}")
            print(f"   OS         : {os}")
            print(f"   Image      : {image_name}")
            print(f"   Private IP : {private_ip}")
            print(f"   Public IP  : {public_ip} (simulated)")
            print(f"   NAT Port   : {nat_port}")
            print(f"   Subnet     : {subnet_cidr}")
            print(f"   SSH Key    : {'✅ Provided' if public_key else '❌ None (web terminal only)'}")

            # Get or create network
            network = self._get_or_create_network(subnet_id, subnet_cidr)

            # Create host config (port binding + resources)
            host_config = self.client.api.create_host_config(
                mem_limit=resources["memory"],
                nano_cpus=int(resources["cpu"] * 1e9),
                port_bindings={
                    '22/tcp': nat_port  # Map host NAT port to container SSH
                }
            )

            # Prepare environment variables for SSH key injection
            environment = {}
            if public_key:
                # Your entrypoint.sh reads this and injects into authorized_keys
                environment["SSH_PUBLIC_KEY"] = public_key.strip()

            # Create container without networking_config (will attach after start)
            container = self.client.api.create_container(
                image=image_name,
                name=f"mini-cloud-{name}",
                host_config=host_config,
                ports={'22/tcp': {}},
                environment=environment,
                labels={
                    "mini-cloud": "true",
                    "instance-name": name,
                    "public-ip": public_ip,
                    "private-ip": private_ip,
                    "subnet-cidr": subnet_cidr,
                    "os": os,
                    "instance-type": instance_type,
                    "nat-port": str(nat_port),
                    "ssh-enabled": "true" if public_key else "false"
                }
            )

            container_id = container.get("Id")

            # Start container (entrypoint.sh runs and injects SSH key)
            self.client.api.start(container_id)
            print(f"✅ Container started: {container_id[:12]}")

            # Connect container to network with specific private IP
            self.client.networks.get(network.name).connect(
                container_id,
                ipv4_address=private_ip
            )
            print(f"🌐 Attached to network: {network.name}")
            print(f"🔒 Private IP assigned: {private_ip}")

            if public_key:
                print(f"🔐 SSH ready: ssh -p {nat_port} root@localhost")
            else:
                print(f"ℹ️ No SSH key - use web terminal")

            print(f"✅ Instance ready!\n")

            return container_id[:12]

        except Exception as e:
            print(f"❌ Container creation failed: {str(e)}")
            raise Exception(f"Failed to create container: {str(e)}")

    def start_container(self, container_id: str):
        """Start a stopped container"""
        try:
            container = self.client.containers.get(container_id)
            container.start()
            print(f"✅ Started container: {container_id}")
        except Exception as e:
            print(f"❌ Failed to start container: {e}")
            raise

    def stop_container(self, container_id: str):
        """Stop a running container"""
        try:
            container = self.client.containers.get(container_id)
            container.stop()
            print(f"✅ Stopped container: {container_id}")
        except Exception as e:
            print(f"❌ Failed to stop container: {e}")
            raise

    def delete_container(self, container_id: str):
        """Delete a container"""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=True)
            print(f"✅ Deleted container: {container_id}")
        except Exception as e:
            print(f"❌ Failed to delete container: {e}")
            raise