import time
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .schemas import GenerateBatchRequest, GenerateBatchResponse
from .providers.factory import get_llm_provider

load_dotenv()

app = FastAPI(
    title="EduGen Generator Service",
    description="AIG Generation Microservice supporting Multi-Strategy synthesis & Dual Mock/Live Execution",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "edugen-generator",
        "version": "1.0.0"
    }

@app.post("/generate/batch", response_model=GenerateBatchResponse)
def generate_batch_endpoint(req: GenerateBatchRequest):
    start_time = time.time()
    try:
        provider = get_llm_provider(req.model_name)
        questions, tokens, cost = provider.generate(req)
        latency = round(time.time() - start_time, 3)

        return GenerateBatchResponse(
            run_id=str(uuid.uuid4()),
            topic_id=req.topic_id,
            model_name=req.model_name,
            strategy=req.strategy,
            questions=questions,
            latency_seconds=latency,
            tokens_used=tokens,
            estimated_cost_usd=cost
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("project.services.generator.src.main:app", host="0.0.0.0", port=8001, reload=True)
