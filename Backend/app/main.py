from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import httpx

from app.api import instances
from app.api import terminal

app = FastAPI(
    title="Mini Cloud Backend",
    description="AWS-style cloud platform",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(instances.router, prefix="/instances", tags=["instances"])
app.include_router(terminal.router, prefix="", tags=["terminal"])


# ==============================
# 🔥 ROOT → STREAMLIT UI
# ==============================

@app.get("/", response_class=HTMLResponse)
async def root():
    async with httpx.AsyncClient() as client:
        r = await client.get("http://localhost:8501")
        return HTMLResponse(content=r.text)


# ==============================
# 🔥 PROXY OTHER FRONTEND ROUTES
# ==============================

@app.get("/{path:path}", response_class=HTMLResponse)
async def proxy_all(path: str):
    # Skip backend routes
    if path.startswith("instances") or path.startswith("terminal") or path.startswith("health"):
        return {"message": "Handled by backend"}

    url = f"http://localhost:8501/{path}"

    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return HTMLResponse(content=r.text)


@app.get("/health", tags=["default"])
def health():
    return {"status": "healthy"}