# Based on the class server.py (ConnectionManager + /ws broadcast).
# Added: StaticFiles at /images, POST /upload-photo, GET /photos.
import os
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

UPLOAD_DIR = "/tmp/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()

# CORS is only for HTTP, not WS, but fine to keep
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files at /images/<filename>
app.mount("/images", StaticFiles(directory=UPLOAD_DIR), name="images")


@app.get("/")
async def root():
    return {"message": "FastAPI photo + WebSocket chat server is running"}


@app.post("/upload-photo")
async def upload_photo(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        ext = ".jpg"  # camera photos from Expo are normally jpg
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    with open(path, "wb") as f:
        f.write(contents)

    print(f"File saved: {path} ({len(contents)} bytes)")
    return {
        "filename": filename,
        "url": f"/images/{filename}",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/photos")
async def list_photos():
    photos = []
    for name in os.listdir(UPLOAD_DIR):
        full = os.path.join(UPLOAD_DIR, name)
        if os.path.isfile(full):
            ts = datetime.fromtimestamp(os.path.getmtime(full), timezone.utc).isoformat()
            photos.append({"filename": name, "url": f"/images/{name}", "uploaded_at": ts})
    photos.sort(key=lambda p: p["uploaded_at"], reverse=True)  # newest first
    return photos


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        # Send the message to all connected clients
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                print("Error sending to a client:", e)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received from client: {data}")

            # Broadcast whatever text we got (JSON from the frontend)
            await manager.broadcast(data)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print("Unexpected error in websocket:", e)
        manager.disconnect(websocket)
        try:
            await websocket.close()
        except:
            pass
