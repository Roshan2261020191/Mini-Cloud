from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import instances

# Create FastAPI app
app = FastAPI(title="Mini Cloud Backend")

# Enable CORS (important for frontend connection)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later you can restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root route (to avoid 404 at localhost:8000)
@app.get("/")
def home():
    return {"message": "Mini Cloud Backend is running"}

# Include instance APIs
app.include_router(instances.router)