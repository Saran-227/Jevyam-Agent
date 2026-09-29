"""Founder approval web routes and API endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from agent.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalSupersededError,
    PostNotFoundError,
)
from api.dependencies import get_approval_service
from api.renderer import render_approval_page, render_error_page
from api.schemas import ApprovalActionResponse, RejectApprovalRequest
from api.services.approval_service import ApprovalService

router = APIRouter(tags=["Approval"])


@router.get("/approve/{token}", response_class=HTMLResponse)
def get_approval_page(
    token: str,
    service: ApprovalService = Depends(get_approval_service),
) -> HTMLResponse:
    """Serve the founder-facing mobile-responsive approval web page."""
    try:
        page_data = service.get_approval_page_data(token)
        html_content = render_approval_page(page_data, token)
        return HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)

    except ApprovalNotFoundError:
        html = render_error_page(
            title="Approval Link Not Found",
            message="This approval link does not exist or was incorrectly formatted.",
        )
        return HTMLResponse(content=html, status_code=status.HTTP_404_NOT_FOUND)

    except ApprovalExpiredError:
        html = render_error_page(
            title="Approval Link Expired",
            message="This approval request has passed its validity window (24 hours).",
        )
        return HTMLResponse(content=html, status_code=status.HTTP_410_GONE)

    except ApprovalAlreadyProcessedError:
        html = render_error_page(
            title="Approval Request Inactive",
            message="This draft has already been reviewed, approved, or regenerated.",
        )
        return HTMLResponse(content=html, status_code=status.HTTP_410_GONE)

    except ApprovalSupersededError:
        html = render_error_page(
            title="Revision Superseded",
            message="A newer revision of this post has already been generated.",
        )
        return HTMLResponse(content=html, status_code=status.HTTP_410_GONE)

    except Exception:
        html = render_error_page(
            title="Unable to Load Draft",
            message="An unexpected server error occurred while retrieving this post. Please try again later.",
        )
        return HTMLResponse(
            content=html,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.post("/approve/{token}/yes", response_model=ApprovalActionResponse)
def approve_post(
    token: str,
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalActionResponse:
    """Confirm post approval and transition status to APPROVED."""
    try:
        return service.approve_post(token)

    except ApprovalNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    except (ApprovalExpiredError, ApprovalAlreadyProcessedError, ApprovalSupersededError) as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while approving the post.",
        ) from e


@router.post("/approve/{token}/no", response_model=ApprovalActionResponse)
def reject_and_regenerate_post(
    token: str,
    body: Optional[RejectApprovalRequest] = None,
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalActionResponse:
    """Reject post draft and trigger AI generation of next revision."""
    reason = body.reason if body else None
    try:
        return service.reject_and_regenerate(token, reason=reason)

    except ApprovalNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    except (ApprovalExpiredError, ApprovalAlreadyProcessedError, ApprovalSupersededError) as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e),
        ) from e

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while regenerating the post.",
        ) from e
