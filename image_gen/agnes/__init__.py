"""
Agnes AI Image Generation Provider
===================================

Backend for Agnes Image 2.1 Flash — free, OpenAI-compatible image generation.
Supports text-to-image and image-to-image via https://apihub.agnes-ai.com
"""

from __future__ import annotations

import json
import logging
import os
import requests
from typing import Any, Dict, List, Optional

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    normalize_reference_images,
    save_b64_image,
    save_url_image,
    success_response,
)

logger = logging.getLogger(__name__)

API_BASE = "https://apihub.agnes-ai.com"
API_ENDPOINT = f"{API_BASE}/v1/images/generations"
DEFAULT_MODEL = "agnes-image-2.1-flash"

# Map Hermes aspect ratios to Agnes sizes
_ASPECT_SIZES = {
    "landscape": "1024x768",
    "square": "1024x1024",
    "portrait": "768x1024",
}


class AgnesImageGenProvider(ImageGenProvider):
    """Agnes AI Image 2.1 Flash backend — free text-to-image & image-to-image."""

    @property
    def name(self) -> str:
        return "agnes"

    @property
    def display_name(self) -> str:
        return "Agnes AI"

    def is_available(self) -> bool:
        return bool(os.environ.get("AGNES_API_KEY"))

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": DEFAULT_MODEL,
                "display": "Agnes Image 2.1 Flash",
                "speed": "~10s",
                "strengths": "Free, text-to-image & image-to-image, up to 4K",
                "price": "free",
            },
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Agnes AI",
            "badge": "free",
            "tag": "Agnes Image 2.1 Flash — free text-to-image & image editing",
            "env_vars": [
                {
                    "key": "AGNES_API_KEY",
                    "prompt": "Agnes AI API key",
                    "url": "https://platform.agnes-ai.com",
                },
            ],
        }

    def capabilities(self) -> Dict[str, Any]:
        return {
            "modalities": ["text", "image"],
            "max_reference_images": 9,
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            return error_response(
                error="Prompt is required",
                error_type="invalid_argument",
                provider="agnes",
            )

        api_key = os.environ.get("AGNES_API_KEY")
        if not api_key:
            return error_response(
                error="AGNES_API_KEY not set. Run `hermes tools` → Image Generation → Agnes AI to configure.",
                error_type="auth_required",
                provider="agnes",
            )

        size = _ASPECT_SIZES.get(aspect_ratio, _ASPECT_SIZES["landscape"])

        # Collect source images
        sources: List[str] = []
        if isinstance(image_url, str) and image_url.strip():
            sources.append(image_url.strip())
        for ref in (normalize_reference_images(reference_image_urls) or []):
            sources.append(ref)

        is_edit = bool(sources)
        modality = "image" if is_edit else "text"

        payload = {
            "model": DEFAULT_MODEL,
            "prompt": prompt,
            "size": size,
            "extra_body": {
                "response_format": "url",
            },
        }

        if is_edit:
            payload["extra_body"]["image"] = sources

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(API_ENDPOINT, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            return error_response(
                error="Agnes AI image generation timed out after 120s",
                error_type="timeout",
                provider="agnes",
                prompt=prompt,
            )
        except requests.exceptions.RequestException as exc:
            return error_response(
                error=f"Agnes AI API error: {exc}",
                error_type="api_error",
                provider="agnes",
                prompt=prompt,
            )

        items = data.get("data") or []
        if not items:
            return error_response(
                error="Agnes AI returned no image data",
                error_type="empty_response",
                provider="agnes",
                prompt=prompt,
            )

        result_url = items[0].get("url")
        b64 = items[0].get("b64_json")
        revised = items[0].get("revised_prompt")

        if result_url:
            try:
                saved = save_url_image(result_url, prefix=f"agnes_{DEFAULT_MODEL}")
                image_ref = str(saved)
            except Exception as exc:
                logger.warning("Could not cache Agnes image: %s", exc)
                image_ref = result_url
        elif b64:
            try:
                saved = save_b64_image(b64, prefix=f"agnes_{DEFAULT_MODEL}")
                image_ref = str(saved)
            except Exception as exc:
                return error_response(
                    error=f"Could not save Agnes image: {exc}",
                    error_type="io_error",
                    provider="agnes",
                    prompt=prompt,
                )
        else:
            return error_response(
                error="Agnes AI returned neither URL nor b64_json",
                error_type="empty_response",
                provider="agnes",
                prompt=prompt,
            )

        extra = {"size": size}
        if revised:
            extra["revised_prompt"] = revised

        return success_response(
            image=image_ref,
            model=DEFAULT_MODEL,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            provider="agnes",
            modality=modality,
            extra=extra,
        )


def register(ctx) -> None:
    """Plugin entry point."""
    ctx.register_image_gen_provider(AgnesImageGenProvider())
