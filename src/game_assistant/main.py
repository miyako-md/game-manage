from fastapi import FastAPI

app = FastAPI(title="Game Assistant")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
