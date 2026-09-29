"""Health check routes."""

from fastapi import APIRouter
from api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Public health check endpoint."""
    return HealthResponse(status="ok", service="jevyam-approval-api")
