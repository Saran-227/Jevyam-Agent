"""Development and testing helper routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from agent.exceptions import PostNotEligibleForApprovalError, PostNotFoundError
from api.dependencies import get_approval_service
from api.schemas import CreateApprovalResponse
from api.services.approval_service import ApprovalService
from config.settings import settings

router = APIRouter(prefix="/api/posts", tags=["Development"])


@router.post("/{post_id}/approval", response_model=CreateApprovalResponse)
def create_post_approval_endpoint(
    post_id: str,
    service: ApprovalService = Depends(get_approval_service),
) -> CreateApprovalResponse:
    """Development helper endpoint to initiate an approval request for an existing post."""
    if not settings.DEV_ENDPOINT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development endpoints are disabled in this environment.",
        )

    try:
        return service.create_approval_request(post_id=post_id)
    except PostNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except PostNotEligibleForApprovalError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate approval request: {e}",
        ) from e
