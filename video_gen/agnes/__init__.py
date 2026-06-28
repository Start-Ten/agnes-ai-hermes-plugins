"""
Agnes AI Video Generation Provider
===================================

Backend for Agnes Video V2.0 — free, async text-to-video & image-to-video.
Uses submit-then-poll pattern via https://apihub.agnes-ai.com
"""

from __future__ import annotations

import json
import logging
import os
import time
import requests
from typing import Any, Dict, List, Optional

from agent.video_gen_provider import (
    VideoGenProvider,
    error_response,
    success_response,
)

logger = logging.getLogger(__name__)

API_BASE = "https://apihub.agnes-ai.com"
CREATE_ENDPOINT = f"{API_BASE}/v1/videos"
RESULT_ENDPOINT = f"{API_BASE}/agnesapi"
DEFAULT_MODEL = "agnes-video-v2.0"

_POLL_INTERVAL = 5.0
_MAX_POLL_TIME = 300  # 5 minutes


class AgnesVideoGenProvider(VideoGenProvider):
    """Agnes AI Video V2.0 backend — free text-to-video & image-to-video."""

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
                "display": "Agnes Video V2.0",
                "speed": "~60-120s",
                "strengths": "Free, text-to-video & image-to-video, native audio",
                "price": "free",
                "tier": "free",
                "modalities": ["text", "image"],
            },
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Agnes AI",
            "badge": "free",
            "tag": "Agnes Video V2.0 — free text-to-video & image-to-video with native audio",
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
            "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
            "resolutions": ["480p", "720p", "1080p"],
            "max_duration": 18,
            "min_duration": 3,
            "supports_audio": True,
            "supports_negative_prompt": True,
            "max_reference_images": 9,
        }

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        duration: Optional[int] = None,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        negative_prompt: Optional[str] = None,
        audio: Optional[bool] = None,
        seed: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        api_key = os.environ.get("AGNES_API_KEY")
        if not api_key:
            return error_response(
                error="AGNES_API_KEY not set.",
                error_type="auth_required",
                provider="agnes",
                prompt=prompt,
            )

        prompt = (prompt or "").strip()
        if not prompt:
            return error_response(
                error="prompt is required",
                error_type="missing_prompt",
                provider="agnes",
            )

        # Resolve resolution -> (width, height)
        res_map = {
            "480p": (640, 480),
            "720p": (1152, 768),
            "1080p": (1920, 1080),
        }
        w, h = res_map.get(resolution, (1152, 768))

        # Adjust dimensions based on aspect ratio
        if aspect_ratio == "9:16":
            w, h = h, w
        elif aspect_ratio == "1:1":
            w, h = 768, 768
        elif aspect_ratio == "4:3":
            w, h = 1024, 768
        elif aspect_ratio == "3:4":
            w, h = 768, 1024

        # Default duration: ~5 seconds (121 frames at 24fps)
        dur = duration or 5
        frame_rate = 24
        # num_frames must follow 8n+1 rule: 81, 121, 161, 241, 441...
        frame_choices = {3: 81, 5: 121, 7: 161, 10: 241, 18: 441}
        num_frames = 121
        for max_dur, frames in sorted(frame_choices.items()):
            if dur <= max_dur:
                num_frames = frames
                break
        num_frames = min(num_frames, 441)

        payload = {
            "model": DEFAULT_MODEL,
            "prompt": prompt,
            "height": h,
            "width": w,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }

        # Handle image-to-video
        image_url_norm = (image_url or "").strip()
        if image_url_norm:
            payload["image"] = image_url_norm

        # Handle reference images
        refs = []
        if reference_image_urls:
            for ref in reference_image_urls:
                if isinstance(ref, str) and ref.strip():
                    refs.append(ref.strip())
        if refs:
            if "extra_body" not in payload:
                payload["extra_body"] = {}
            payload["extra_body"]["image"] = refs

        if negative_prompt:
            if "extra_body" not in payload:
                payload["extra_body"] = {}
            payload["extra_body"]["negative_prompt"] = negative_prompt

        if seed is not None:
            payload["seed"] = seed

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Step 1: Create task
        try:
            resp = requests.post(CREATE_ENDPOINT, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            task_data = resp.json()
        except requests.exceptions.RequestException as exc:
            return error_response(
                error=f"Failed to create Agnes video task: {exc}",
                error_type="api_error",
                provider="agnes",
                prompt=prompt,
            )

        video_id = task_data.get("video_id") or task_data.get("id")
        if not video_id:
            return error_response(
                error="Agnes API returned no video_id",
                error_type="empty_response",
                provider="agnes",
                prompt=prompt,
            )

        # Step 2: Poll for completion
        modality_used = "image" if image_url_norm else "text"
        start = time.time()

        while (time.time() - start) < _MAX_POLL_TIME:
            try:
                poll_url = f"{RESULT_ENDPOINT}?video_id={video_id}&model_name={DEFAULT_MODEL}"
                poll_resp = requests.get(poll_url, headers=headers, timeout=30)
                poll_resp.raise_for_status()
                result = poll_resp.json()
            except requests.exceptions.RequestException as exc:
                return error_response(
                    error=f"Failed to poll Agnes video status: {exc}",
                    error_type="api_error",
                    provider="agnes",
                    model=DEFAULT_MODEL,
                    prompt=prompt,
                )

            status = result.get("status", "")
            if status == "completed":
                video_url = result.get("remixed_from_video_id")
                if not video_url:
                    return error_response(
                        error="Agnes returned 'completed' but no video URL",
                        error_type="empty_response",
                        provider="agnes",
                        model=DEFAULT_MODEL,
                        prompt=prompt,
                    )
                return success_response(
                    video=video_url,
                    model=DEFAULT_MODEL,
                    prompt=prompt,
                    modality=modality_used,
                    aspect_ratio=aspect_ratio,
                    duration=int(float(result.get("seconds", "0"))),
                    provider="agnes",
                    extra={
                        "size": result.get("size", ""),
                        "video_id": video_id,
                    },
                )
            elif status == "failed":
                err = result.get("error") or "unknown error"
                return error_response(
                    error=f"Agnes video generation failed: {err}",
                    error_type="generation_failed",
                    provider="agnes",
                    model=DEFAULT_MODEL,
                    prompt=prompt,
                )
            # Still in progress / queued — wait and poll again
            time.sleep(_POLL_INTERVAL)

        return error_response(
            error=f"Agnes video generation timed out after {_MAX_POLL_TIME}s",
            error_type="timeout",
            provider="agnes",
            model=DEFAULT_MODEL,
            prompt=prompt,
        )


def register(ctx) -> None:
    """Plugin entry point."""
    ctx.register_video_gen_provider(AgnesVideoGenProvider())
