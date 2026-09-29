"""LinkedIn Publisher: formats and dispatches approved content to Company Page."""

from typing import Optional
from database.models import Post, PostRevision
from integrations.linkedin.client import LinkedInClient, LinkedInPublishResponse


class LinkedInPublisher:
    """Formats approved post content and publishes it to LinkedIn."""

    def __init__(self, client: Optional[LinkedInClient] = None):
        self.client = client or LinkedInClient()

    def format_post_text(self, post: Post, revision: Optional[PostRevision] = None) -> str:
        """Assemble clean, final LinkedIn post text combining hook, caption, and hashtags.

        Ensures no duplicate hook or hashtags if already contained in caption.
        """
        caption = (revision.caption if revision else post.caption) or ""
        hook = (revision.hook if revision else post.hook) or ""
        hashtags = (revision.hashtags if revision else post.hashtags) or []

        # If caption does not start with hook, combine
        content_parts = []
        if hook and not caption.strip().startswith(hook.strip()):
            content_parts.append(hook.strip())

        content_parts.append(caption.strip())

        # Check if hashtags are already in caption
        tags_to_append = []
        caption_lower = caption.lower()
        for tag in hashtags:
            clean_tag = tag.strip() if tag.strip().startswith("#") else f"#{tag.strip()}"
            if clean_tag.lower() not in caption_lower:
                tags_to_append.append(clean_tag)

        if tags_to_append:
            content_parts.append(" ".join(tags_to_append))

        return "\n\n".join(content_parts).strip()

    def publish(self, post: Post, revision: Optional[PostRevision] = None) -> LinkedInPublishResponse:
        """Publish the formatted approved post to the LinkedIn Company Page.

        Args:
            post: Post database entity.
            revision: Optional specific PostRevision entity.

        Returns:
            LinkedInPublishResponse.
        """
        formatted_text = self.format_post_text(post, revision)
        image_url = (revision.image_url if revision else post.image_url) or post.image_url
        return self.client.publish_text_post(text=formatted_text, image_url=image_url)
