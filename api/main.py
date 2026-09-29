"""FastAPI entry point for Jevyam Technologies Approval System."""

from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import approval_router, dev_router, health_router, whatsapp_router
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown logging."""
    host = settings.API_HOST
    port = settings.API_PORT
    base_url = settings.APP_BASE_URL.rstrip("/")
    print("=" * 60)
    print("JEVYAM AI MARKETING AGENT — APPROVAL SERVICE")
    print(f"API Server initialized on: http://{host}:{port}")
    print(f"Base Approval URL: {base_url}")
    print(f"Health Check: http://{host}:{port}/health")
    print(f"WhatsApp Webhook: http://{host}:{port}/webhook/whatsapp")
    print("=" * 60)
    yield


app = FastAPI(
    title="Jevyam Technologies Approval API",
    description="Secure founder approval and revision workflow API for AI-generated LinkedIn content.",
    version="1.0.0",
    lifespan=lifespan,
)

# Register Route Handlers
app.include_router(health_router)
app.include_router(approval_router)
app.include_router(whatsapp_router)
app.include_router(dev_router)


# Global Safe Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Prevent internal stack traces or secrets from leaking to client."""
    # Note: Log internal error on server without exposing credentials to caller
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An internal server error occurred. Please contact the administrator.",
        },
    )


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )
