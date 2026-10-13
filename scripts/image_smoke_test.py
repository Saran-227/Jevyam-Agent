"""Explicitly invoked live image generation and storage smoke test.

Verifies live Gemini image generation API and Supabase Storage upload
in complete isolation:
- Does NOT publish to LinkedIn.
- Does NOT send approval notifications (Telegram/WhatsApp).
- Prints only success/failure, image MIME type, and the public URL.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

load_dotenv()

from config.settings import settings
from database.storage import SupabaseStorageService
from integrations.gemini import generate_gemini_image, get_gemini_client


def run_smoke_test() -> int:
    """Run an isolated live smoke test against Gemini image API and Supabase bucket."""
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        print("Status: FAILED")
        print("Error: GEMINI_API_KEY is not configured.")
        return 1

    model = getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    bucket = getattr(settings, "SUPABASE_IMAGE_BUCKET", "post-images")

    prompt = (
        "Create a professional, high-resolution minimalist 2D technical vector diagram "
        "for an enterprise tech feed. Subject: Distributed cloud workflow idempotency and queue reliability. "
        "Deep navy background with crisp slate and cyan trace lines."
    )

    try:
        client = get_gemini_client()
        image_bytes, mime_type = generate_gemini_image(
            client=client,
            prompt=prompt,
            model=model,
            aspect_ratio="1:1",
        )
    except Exception as e:
        print("Status: FAILED")
        print(f"Error (Gemini Image Generation): {e}")
        return 1

    try:
        storage = SupabaseStorageService(bucket_name=bucket)
        public_url = storage.upload_image(
            post_id="SMOKE-TEST",
            revision=1,
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
    except Exception as e:
        print("Status: FAILED")
        print(f"Image MIME Type: {mime_type}")
        print(f"Error (Supabase Storage Upload): {e}")
        return 1

    print("Status: SUCCESS")
    print(f"Image MIME Type: {mime_type}")
    print(f"Public URL: {public_url}")
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
