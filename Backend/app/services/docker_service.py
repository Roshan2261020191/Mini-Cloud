import docker
import requests

client = docker.from_env()

INSTANCE_CONFIG = {
    "t2.nano": {"cpu": 0.25, "memory": "256m"},
    "t2.micro": {"cpu": 0.5, "memory": "512m"}
}


def create_instance(data):
    name = data.get("name")
    os_type = data.get("os")
    instance_type = data.get("instance_type", "t2.nano")

    image_map = {
        "Ubuntu": "ubuntu:latest",
        "Alpine Linux": "alpine:latest",
        "Debian Slim": "debian:latest",
        "BusyBox": "busybox"
    }

    image = image_map.get(os_type, "ubuntu:latest")

    # 🔥 Prevent duplicate containers
    try:
        old = client.containers.get(name)
        return {"error": "Instance with this name already exists"}
    except:
        pass

    config = INSTANCE_CONFIG.get(instance_type, INSTANCE_CONFIG["t2.nano"])

    print(f"Launching {instance_type} → CPU {config['cpu']} Memory {config['memory']}")

    container = client.containers.run(
        image,
        name=name,
        command="sleep infinity",
        detach=True,
        tty=True,
        mem_limit=config["memory"],
        cpu_period=100000,
        cpu_quota=int(config["cpu"] * 100000)
    )

    container.reload()

    # 🔥 Reliable private IP
    private_ip = container.attrs["NetworkSettings"]["Networks"]["bridge"]["IPAddress"]

    try:
        public_ip = requests.get("https://api.ipify.org", timeout=5).text
    except:
        public_ip = "Not available"

    return {
        "message": "Instance created",
        "container_id": container.id,
        "private_ip": private_ip,
        "public_ip": public_ip,
        "instance_type": instance_type
    }


def stop_instance(container_id):
    try:
        container = client.containers.get(container_id)
        container.stop()
        return {"message": "Instance stopped"}
    except Exception as e:
        return {"error": str(e)}


def start_instance(container_id):
    try:
        container = client.containers.get(container_id)
        container.start()
        return {"message": "Instance started"}
    except Exception as e:
        return {"error": str(e)}


def terminate_instance(container_id):
    try:
        container = client.containers.get(container_id)
        container.stop()
        container.remove()
        return {"message": "Instance terminated"}
    except Exception as e:
        return {"error": str(e)}