"""FastAPI router for LinkedIn publishing operations and audit history."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from agent.exceptions import (
    LinkedInAPIError,
    LinkedInAuthError,
    LinkedInDuplicatePostError,
    LinkedInNetworkError,
    LinkedInPermissionError,
    LinkedInRateLimitError,
    LinkedInValidationError,
    MissingLinkedInCredentialsError,
    PostNotApprovedError,
    PostNotFoundError,
)
from api.dependencies import get_publishing_service
from api.schemas import PublishResponse
from api.services.publishing_service import PublishingService

router = APIRouter(prefix="", tags=["LinkedIn Publishing"])


@router.post(
    "/posts/{post_id}/publish",
    response_model=PublishResponse,
    summary="Publish an approved post to LinkedIn Company Page",
)
async def publish_post_endpoint(
    post_id: str,
    force: bool = Query(False, description="Bypass idempotency duplicate check"),
    publishing_service: PublishingService = Depends(get_publishing_service),
):
    """Publish an approved post to the Jevyam Technologies LinkedIn Company Page.

    Fails if the post is in DRAFT, PENDING_APPROVAL, REJECTED, or REGENERATING state.
    Returns existing publishing result if already published (idempotent).
    """
    try:
        result = publishing_service.publish_approved_post(post_id=post_id, force=force)
        return PublishResponse(
            status=result["status"],
            post_id=result["post_id"],
            revision=result["revision"],
            external_post_id=result.get("external_post_id"),
            post_url=result.get("post_url"),
            published_at=result.get("published_at"),
            is_duplicate=result.get("is_duplicate", False),
            message=result.get("message"),
        )
    except PostNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PostNotApprovedError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MissingLinkedInCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except (LinkedInAuthError, LinkedInPermissionError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LinkedInValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LinkedInRateLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except (LinkedInNetworkError, LinkedInAPIError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get(
    "/posts/{post_id}/publications",
    summary="Fetch publication history and audit records for a post",
)
async def get_post_publications_endpoint(
    post_id: str,
    publishing_service: PublishingService = Depends(get_publishing_service),
):
    """Fetch the audit log of all publishing attempts and outcomes for a post."""
    records = publishing_service.repos.publications.get_by_post_id(post_id)
    return {
        "post_id": post_id,
        "count": len(records),
        "publications": [r.model_dump(mode="json") for r in records],
    }
