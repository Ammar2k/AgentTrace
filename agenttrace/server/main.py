from fastapi import FastAPI

app = FastAPI(title="AgentTrace")

@app.get("/health")
def health():
    return {"status": "ok"}
