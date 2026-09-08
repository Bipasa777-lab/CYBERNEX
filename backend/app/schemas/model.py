from typing import Optional
from pydantic import BaseModel, ConfigDict


class AIModelSchema(BaseModel):
    id: str
    name: str
    role: str
    category: str  # GENERAL, CODING, VISION, EMBEDDING
    status: str  # ONLINE, OFFLINE, BUSY
    localInference: bool = True
    contextWindow: str = "128,000 tokens"
    vramUsage: str = "0.0 GB"
    gpuLoad: int = 0
    throughput: str = "0 t/s"
    lastCheck: str = "1s ago"

    model_config = ConfigDict(from_attributes=True)


class ModelRouteResult(BaseModel):
    selected_model: str
    category: str
    reason: str
