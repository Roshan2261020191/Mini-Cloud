from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
import docker
import asyncio
import json
import threading
from typing import Optional
from functools import partial

router = APIRouter()
docker_client = docker.from_env()


# ===== SECURITY: Validate Container Ownership =====
async def validate_container_access(container_id: str, user_id: Optional[str] = None):
    try:
        # 🔐 ENABLE THIS IN PRODUCTION
        # from supabase_client import supabase
        # result = supabase.table("instances") \
        #     .select("user_id") \
        #     .eq("container_id", container_id) \
        #     .execute()
        #
        # if not result.data:
        #     raise HTTPException(status_code=404, detail="Instance not found")
        #
        # if user_id and result.data[0]['user_id'] != user_id:
        #     raise HTTPException(status_code=403, detail="Access denied")

        container = docker_client.containers.get(container_id)

        if container.status != "running":
            raise HTTPException(
                status_code=400,
                detail=f"Container is {container.status}, not running"
            )

        return container

    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")


# ===== SHELL DETECTION =====
def get_shell_for_container(container) -> str:
    try:
        image_name = container.attrs['Config']['Image'].lower()

        if any(os in image_name for os in ['ubuntu', 'debian', 'centos', 'fedora']):
            test = container.exec_run("/bin/bash --version", demux=False)
            if test.exit_code == 0:
                return "/bin/bash"

        return "/bin/sh"

    except Exception:
        return "/bin/sh"


# ===== TERMINAL UI =====
@router.get("/terminal/{container_id}")
async def get_terminal_page(container_id: str):
    await validate_container_access(container_id)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Terminal - {container_id}</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css" />
        <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>
    </head>
    <body style="margin:0;background:#1e1e1e;">
        <div id="terminal" style="height:100vh;"></div>

        <script>
            const term = new Terminal({{ cursorBlink: true }});
            const fitAddon = new FitAddon.FitAddon();

            term.loadAddon(fitAddon);
            term.open(document.getElementById('terminal'));
            fitAddon.fit();

            const protocol = location.protocol === 'https:' ? 'wss://' : 'ws://';
            const ws = new WebSocket(`${{protocol}}${{location.host}}/ws/terminal/{container_id}`);

            ws.onopen = () => term.writeln("✅ Connected\\r\\n");
            ws.onmessage = (e) => term.write(e.data);
            ws.onclose = () => term.writeln("\\r\\n❌ Disconnected");

            term.onData(data => ws.send(data));

            window.addEventListener('resize', () => {{
                fitAddon.fit();
                ws.send(JSON.stringify({{
                    type: 'resize',
                    cols: term.cols,
                    rows: term.rows
                }}));
            }});

            setTimeout(() => {{
                ws.send(JSON.stringify({{
                    type: 'resize',
                    cols: term.cols,
                    rows: term.rows
                }}));
            }}, 300);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


# ===== WEBSOCKET TERMINAL =====
@router.websocket("/ws/terminal/{container_id}")
async def websocket_terminal(websocket: WebSocket, container_id: str):
    await websocket.accept()

    exec_id = None
    exec_socket = None
    stop_flag = threading.Event()

    try:
        container = await validate_container_access(container_id)

        shell = get_shell_for_container(container)
        print(f"✅ Using shell: {shell}")

        # FIX #4: Better error handling
        exec_response = docker_client.api.exec_create(
            container.id,
            cmd=shell,
            stdin=True,
            tty=True
        )
        
        if not exec_response or 'Id' not in exec_response:
            raise HTTPException(500, "Failed to create exec instance")
        
        exec_id = exec_response['Id']

        exec_socket = docker_client.api.exec_start(
            exec_id,
            socket=True,
            tty=True
        )

        loop = asyncio.get_running_loop()

        # FIX #1: Determine correct socket method
        # Test which method exists
        if hasattr(exec_socket, 'recv'):
            socket_recv = exec_socket.recv
            socket_send = exec_socket.send
        else:
            socket_recv = exec_socket._sock.recv
            socket_send = exec_socket._sock.send

        # ===== READ FROM CONTAINER =====
        async def read_container():
            try:
                while not stop_flag.is_set():
                    try:
                        # FIX #2: Direct function call, no lambda
                        data = await loop.run_in_executor(
                            None,
                            socket_recv,
                            4096
                        )

                        if not data:
                            break

                        await websocket.send_text(
                            data.decode(errors="ignore")
                        )

                    except Exception as e:
                        print(f"❌ Read error: {e}")
                        break
            finally:
                stop_flag.set()

        # ===== WRITE TO CONTAINER =====
        async def write_container():
            try:
                while not stop_flag.is_set():
                    try:
                        data = await websocket.receive_text()

                        # ✅ SAFE JSON PARSE
                        msg = None
                        try:
                            msg = json.loads(data)
                        except (json.JSONDecodeError, ValueError):
                            pass

                        # ✅ HANDLE RESIZE
                        if msg and msg.get("type") == "resize":
                            rows = msg.get("rows")
                            cols = msg.get("cols")

                            if rows and cols:
                                try:
                                    docker_client.api.exec_resize(
                                        exec_id,
                                        height=rows,
                                        width=cols
                                    )
                                except Exception as e:
                                    print(f"⚠️ Resize error: {e}")
                            continue

                        # FIX #2: Use partial to avoid closure issues
                        await loop.run_in_executor(
                            None,
                            socket_send,
                            data.encode()
                        )

                    except WebSocketDisconnect:
                        print("WebSocket disconnected")
                        break
                    except Exception as e:
                        print(f"❌ Write error: {e}")
                        break
            finally:
                stop_flag.set()

        await asyncio.gather(
            read_container(),
            write_container(),
            return_exceptions=True
        )

    except HTTPException as e:
        try:
            await websocket.send_text(f"❌ {e.detail}")
        except:
            pass
    except Exception as e:
        try:
            await websocket.send_text(f"❌ Error: {str(e)}")
        except:
            pass

    finally:
        stop_flag.set()

        if exec_socket:
            try:
                exec_socket.close()
            except Exception as e:
                print(f"Socket close error: {e}")

        if exec_id:
            try:
                info = docker_client.api.exec_inspect(exec_id)
                if info.get("Running"):
                    print(f"⚠️ Exec {exec_id} still running (will auto-close)")
            except Exception as e:
                print(f"Exec inspect error: {e}")