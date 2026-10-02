from fastapi import FastAPI

app = FastAPI(title="Mini CDP")

@app.get("/health")
def health():
    return {"status": "ok"}