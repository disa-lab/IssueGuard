"""
API route handlers.
"""

from fastapi import APIRouter, HTTPException

from .models import (
    DetectionRequest,
    DetectionResponse,
    SecretResult,
    CacheStats,
    HealthResponse
)
from .service import SecretDetectionService


# Create router
router = APIRouter()

# Global service instance (will be set by app initialization)
detection_service: SecretDetectionService = None


def set_detection_service(service: SecretDetectionService):
    """Set the global detection service instance."""
    global detection_service
    detection_service = service


@router.get("/", response_model=dict)
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Secret Detection API",
        "version": "1.0.0",
        "endpoints": {
            "/detect": "POST - Detect secrets in text",
            "/health": "GET - Health check",
            "/docs": "GET - Interactive API documentation",
            "/redoc": "GET - Alternative API documentation"
        }
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    if detection_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    stats = detection_service.get_stats()
    
    return HealthResponse(
        status="healthy",
        model_loaded=True,
        patterns_loaded=stats['patterns_loaded'],
        device=stats['device']
    )


@router.post("/detect", response_model=DetectionResponse)
async def detect_secrets_endpoint(request: DetectionRequest):
    """
    Detect secrets in the provided text.
    
    Args:
        request: DetectionRequest with text and parameters
    
    Returns:
        DetectionResponse with detected secrets and all candidates
    """
    if detection_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Run detection (async)
        result = await detection_service.detect_secrets(
            text=request.text,
            max_results=request.max_results,
            batch_size=request.batch_size
        )
        
        # Format secrets for response
        secrets = []
        for secret in result['secrets']:
            secrets.append(SecretResult(
                candidate_string=secret['candidate_string'],
                secret_type=secret['secret_type'],
                is_secret=secret['is_secret'],
                position_start=secret['position'][0],
                position_end=secret['position'][1],
                pattern_id=secret['pattern_id'],
                source=secret['source'],
                from_cache=secret.get('from_cache', False)
            ))
        
        # Format all candidates for response
        all_candidates = []
        for candidate in result['all_candidates']:
            all_candidates.append(SecretResult(
                candidate_string=candidate['candidate_string'],
                secret_type=candidate['secret_type'],
                is_secret=candidate['is_secret'],
                position_start=candidate['position'][0],
                position_end=candidate['position'][1],
                pattern_id=candidate['pattern_id'],
                source=candidate['source'],
                from_cache=candidate.get('from_cache', False)
            ))
        
        return DetectionResponse(
            success=result['success'],
            total_candidates=result['total_candidates'],
            secrets_detected=result['secrets_detected'],
            detection_rate=result['detection_rate'],
            secrets=secrets,
            all_candidates=all_candidates,
            cache_stats=CacheStats(
                hits=result['cache_stats']['hits'],
                misses=result['cache_stats']['misses'],
                hit_rate=result['cache_stats']['hit_rate']
            ),
            message=result['message']
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during detection: {str(e)}")
