from fastapi import APIRouter
from app.services.docker_service import (
    create_instance,
    start_instance,
    stop_instance,
    terminate_instance
)

router = APIRouter(prefix="/instances", tags=["Instances"])


# 🔥 CREATE INSTANCE
@router.post("/create")
def create_new_instance(data: dict):
    return create_instance(data)


# 🔥 START INSTANCE
@router.post("/start/{container_id}")
def start(container_id: str):
    return start_instance(container_id)


# 🔥 STOP INSTANCE
@router.post("/stop/{container_id}")
def stop(container_id: str):
    return stop_instance(container_id)


# 🔥 TERMINATE INSTANCE
@router.delete("/terminate/{container_id}")
def terminate(container_id: str):
    return terminate_instance(container_id)