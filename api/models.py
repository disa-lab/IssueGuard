"""
Pydantic models for API requests and responses.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class DetectionRequest(BaseModel):
    """Request model for secret detection."""
    text: str = Field(..., description="The text to analyze for secrets", min_length=1)
    max_results: Optional[int] = Field(
        default=None,
        description="Maximum number of results to return (None for all)",
        ge=1
    )
    batch_size: int = Field(
        default=32,
        description="Batch size for inference",
        ge=1,
        le=128
    )


class SecretResult(BaseModel):
    """Model for a single secret detection result."""
    candidate_string: str
    secret_type: str
    is_secret: bool
    position_start: int
    position_end: int
    pattern_id: int
    source: str
    from_cache: bool = Field(default=False, description="Whether result was retrieved from cache")


class CacheStats(BaseModel):
    """Cache statistics model."""
    hits: int = Field(description="Number of cache hits")
    misses: int = Field(description="Number of cache misses")
    hit_rate: float = Field(description="Cache hit rate percentage")


class DetectionResponse(BaseModel):
    """Response model for secret detection."""
    success: bool
    total_candidates: int
    secrets_detected: int
    detection_rate: float
    secrets: List[SecretResult]
    all_candidates: List[SecretResult] = Field(description="All candidates with their labels")
    cache_stats: CacheStats = Field(description="Cache performance statistics")
    message: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model_loaded: bool
    patterns_loaded: int
    device: str
