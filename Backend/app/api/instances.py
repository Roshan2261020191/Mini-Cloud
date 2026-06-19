from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.docker_service import DockerService
from app.services.ngrok import get_ngrok_tcp_endpoint

router = APIRouter()
docker_service = DockerService()


class CreateInstanceRequest(BaseModel):
    name: str
    os: str
    instance_type: str
    subnet_id: str
    subnet_cidr: str
    private_ip: str
    public_ip: str
    nat_port: int
    public_key: Optional[str] = None


class InstanceResponse(BaseModel):
    container_id: str
    private_ip: str
    public_ip: str
    ssh_host: Optional[str]
    ssh_port: int
    status: str


@router.post("/create", response_model=InstanceResponse)
async def create_instance(request: CreateInstanceRequest):
    try:
        container_id = docker_service.create_container(
            name=request.name,
            os=request.os,
            instance_type=request.instance_type,
            subnet_id=request.subnet_id,
            subnet_cidr=request.subnet_cidr,
            private_ip=request.private_ip,
            public_ip=request.public_ip,
            nat_port=request.nat_port,
            public_key=request.public_key
        )

        # ✅ Safe ngrok handling
        ngrok_host, ngrok_port = get_ngrok_tcp_endpoint()

        if ngrok_host and ngrok_port:
            ssh_host = ngrok_host
            ssh_port = ngrok_port
        else:
            ssh_host = None
            ssh_port = request.nat_port

        return InstanceResponse(
            container_id=container_id,
            private_ip=request.private_ip,
            public_ip=request.public_ip,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            status="success"
        )

    except Exception as e:
        msg = str(e)

        if "already in use" in msg:
            raise HTTPException(status_code=400, detail="Instance name conflict")

        raise HTTPException(status_code=500, detail=msg)


@router.post("/start/{container_id}")
async def start_instance(container_id: str):
    try:
        docker_service.start_container(container_id)

        ngrok_host, ngrok_port = get_ngrok_tcp_endpoint()

        return {
            "status": "success",
            "ssh_host": ngrok_host,
            "ssh_port": ngrok_port
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop/{container_id}")
async def stop_instance(container_id: str):
    try:
        docker_service.stop_container(container_id)

        return {
            "status": "success",
            "ssh_host": None,
            "ssh_port": None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/terminate/{container_id}")
async def terminate_instance(container_id: str):
    try:
        docker_service.delete_container(container_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))