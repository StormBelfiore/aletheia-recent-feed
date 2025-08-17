import os
from fastapi import FastAPI
from .ui import router as ui_router

app = FastAPI(title="Aletheia Recent Feed")
app.include_router(ui_router)

@app.get("/health")
def health():
    return {"ok": True}
