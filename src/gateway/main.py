import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.core.contracts.gateway import QueryRequest, QueryResponse
from src.gateway.deps import get_orchestrator_url
from src.gateway.middleware import RequestIDMiddleware

app = FastAPI(title="Multi-Agent: Gateway")
app.add_middleware(RequestIDMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    base = get_orchestrator_url()
    url = f"{base.rstrip('/')}/query"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=req.model_dump())
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"Orchestrator unavailable: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return QueryResponse(**r.json())
