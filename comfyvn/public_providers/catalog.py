from __future__ import annotations

"""
Curated pricing + review notes for public providers.

These figures are sourced from vendor pricing pages and community reviews as of
2025-11.  They are meant to give Studio operators quick heuristics when
evaluating integrations; always confirm against the vendor terms of service
before enabling live traffic.
"""

from typing import Dict, List, Mapping

ProviderEntry = Dict[str, object]
CategoryCatalog = Dict[str, List[ProviderEntry]]

CATALOG: CategoryCatalog = {
    "gpu_backends": [
        {
            "id": "runpod",
            "name": "RunPod",
            "pricing": {
                "on_demand": {
                    "RTX_4090_24GB": 0.34,
                    "RTX_6000_ADA": 0.49,
                    "A100_80GB": 1.99,
                },
                "serverless": "GPU minute billing; 10 GB RAM plan ≈ $0.0008 per GPU-second",
                "unit": "USD/hour (on-demand)",
            },
            "reviews": {
                "summary": "Popular with indie MLOps teams; praised for spot availability and fast cold starts. Complaints focus on queue spikes during model launches.",
                "sources": [
                    "https://www.runpod.io/pricing",
                    "https://www.g2.com/products/runpod/reviews",
                ],
            },
            "notes": "Supports secure volumes, websocket streaming, and serverless endpoints. Token required for live calls.",
        },
        {
            "id": "hf_inference_endpoints",
            "name": "Hugging Face Inference Endpoints",
            "pricing": {
                "instances": {
                    "n1-standard-4": 0.12,
                    "nvidia_t4": 0.60,
                    "nvidia_a10g": 1.20,
                    "nvidia_a100_80gb": 2.99,
                },
                "unit": "USD/hour (billed per minute)",
            },
            "reviews": {
                "summary": "Reliable managed inference with automatic TLS and private networking. Teams highlight seamless HF model deployment; costs spike when scaling without autosuspend.",
                "sources": ["https://huggingface.co/docs/inference-endpoints/pricing"],
            },
            "notes": "Requires paid HF subscription. Idle endpoints accrue charges until paused.",
        },
        {
            "id": "replicate",
            "name": "Replicate",
            "pricing": {
                "model_examples": {
                    "flux_pro_ultra": "≈ $0.06 per image",
                    "llama_3_8b": "$0.0008 per second",
                    "whisper_large_v3": "$0.006 per minute",
                },
                "unit": "usage dependent",
            },
            "reviews": {
                "summary": "Marketplace model pricing is transparent; developers appreciate per-second billing and hosted examples. Watch for cold starts on community-hosted models.",
                "sources": ["https://replicate.com/pricing"],
            },
            "notes": "Each model owner sets rates. Platform fee (10%) applied to API usage.",
        },
        {
            "id": "modal",
            "name": "Modal Labs",
            "pricing": {
                "gpu_rates": {
                    "A10G": 1.32,
                    "L4": 0.60,
                    "A100_80GB": 2.99,
                },
                "unit": "USD/hour (billed per second)",
            },
            "reviews": {
                "summary": "Serverless GPU workflows with instant scale-to-zero. Developers praise infra-as-code ergonomics; network egress fees and region availability can be limiting.",
                "sources": ["https://modal.com/pricing"],
            },
            "notes": "Billed per second with 1-minute minimum. Includes built-in secrets and scheduler.",
        },
    ],
    "image_video": [
        {
            "id": "runway",
            "name": "Runway API",
            "pricing": {
                "credits": {
                    "usd_per_credit": 0.01,
                    "seconds_per_clip": "12–30 credits/second (quality dependent)",
                },
                "plans": {
                    "Standard": "625 credits/month ($12)",
                    "Pro": "2250 credits/month ($35)",
                },
            },
            "reviews": {
                "summary": "Well-documented Gen-3 video with polished editor integrations. Users note strong quality but strict content safety filters.",
                "sources": [
                    "https://runwayml.com/pricing",
                    "https://www.producthunt.com/products/runway/reviews",
                ],
            },
            "notes": "API requires credit pack and organisation key. Web console shows per-clip burn.",
        },
        {
            "id": "pika",
            "name": "Pika Labs",
            "pricing": {
                "api": {
                    "720p": "$0.05 per second",
                    "1080p": "$0.07 per second",
                },
                "unit": "USD/second",
            },
            "reviews": {
                "summary": "High-energy stylistic results with fast iteration. Builders highlight Discord-first workflows; API still invite-gated for some regions.",
                "sources": ["https://pika.art/pricing"],
            },
            "notes": "Usage billed per generated second. Bulk discounts available on request.",
        },
        {
            "id": "luma_dream_machine",
            "name": "Luma Dream Machine",
            "pricing": {
                "plans": {
                    "Lite": "$9.99/month (120 fast credits)",
                    "Standard": "$29.99/month (600 fast credits)",
                    "Pro": "$99.99/month (3000 fast credits)",
                },
                "api": "Enterprise partnerships via waitlist",
            },
            "reviews": {
                "summary": "Praised for cinematic camera moves; consumer tiers limit API access. Community notes occasional queueing during large releases.",
                "sources": ["https://lumalabs.ai/dream-machine"],
            },
            "notes": "Fast vs relaxed credits determine queue priority. API currently invite-only.",
        },
        {
            "id": "fal_ai",
            "name": "fal.ai",
            "pricing": {
                "on_demand": {
                    "H100_80GB": 1.89,
                    "A100_80GB": 1.69,
                },
                "model_rates": {
                    "flux_pro": "$0.12 per image",
                    "flux_rapid": "$0.03 per image",
                },
            },
            "reviews": {
                "summary": "Developers like the async API and generous payload sizes. Reported issues: occasional backlog spikes and limited spot regions.",
                "sources": ["https://fal.ai/pricing"],
            },
            "notes": "End-to-end async jobs with webhook callbacks. Supports custom Docker containers.",
        },
    ],
    "translate_ocr_speech": [
        {
            "id": "google_translate",
            "name": "Google Cloud Translation",
            "pricing": {
                "standard": "$20 per million characters",
                "advanced": "$80 per million characters (includes glossary/context)",
                "free_tier": "First 500k characters/month free with Google Cloud trial",
            },
            "reviews": {
                "summary": "Accurate for major languages; glossaries help domain terms. Watch for quota enforcement when batching large documents.",
                "sources": ["https://cloud.google.com/translate/pricing"],
            },
            "notes": "Requires Cloud project + service account key. Supports AutoML custom models.",
        },
        {
            "id": "deepl",
            "name": "DeepL API",
            "pricing": {
                "api_free": "500k characters/month free",
                "api_pro": {
                    "base_fee": "€4.99/month",
                    "per_character": "€0.00002 per character beyond quota",
                },
            },
            "reviews": {
                "summary": "Favoured for European language nuance. Developers note limited Asian language coverage compared to Google.",
                "sources": ["https://www.deepl.com/pricing"],
            },
            "notes": "Authentication via API key header. Provides formality controls and glossary endpoints.",
        },
        {
            "id": "amazon_translate",
            "name": "Amazon Translate",
            "pricing": {
                "standard": "$15 per million characters",
                "custom_mt": "$60 per million characters",
                "free_tier": "2M characters/month for first 12 months",
            },
            "reviews": {
                "summary": "Deep AWS integration and VPC endpoints. Some teams report slower glossary propagation compared to competitors.",
                "sources": ["https://aws.amazon.com/translate/pricing/"],
            },
            "notes": "IAM roles recommended. Offers batch, real-time, and asynchronous translation.",
        },
        {
            "id": "google_vision",
            "name": "Google Cloud Vision",
            "pricing": {
                "text_detection": "$1.50 per 1000 units",
                "document_text_detection": "$1.50 per 1000 pages",
                "free_tier": "First 1000 units/month per feature",
            },
            "reviews": {
                "summary": "Fast OCR with layout metadata. Pricing granular but can escalate with bulk uploads.",
                "sources": ["https://cloud.google.com/vision/pricing"],
            },
            "notes": "Supports PDF/GCS batch processing. Combine with Document AI for complex layouts.",
        },
        {
            "id": "aws_rekognition",
            "name": "AWS Rekognition",
            "pricing": {
                "image_label": "$1 per 1000 images",
                "face_search": "$1 per 1000 images",
                "video_label": "$0.12 per minute (first 1000 minutes free for 12 months)",
            },
            "reviews": {
                "summary": "Strong face analysis; concerns around privacy policies and regional availability.",
                "sources": ["https://aws.amazon.com/rekognition/pricing/"],
            },
            "notes": "Requires regional endpoint configuration. IAM permissions critical for security.",
        },
        {
            "id": "deepgram",
            "name": "Deepgram",
            "pricing": {
                "nova-2": "$0.004 per second (~$0.24 per minute)",
                "enhanced": "$0.006 per second",
                "free_credit": "$200 usage credit for new accounts",
            },
            "reviews": {
                "summary": "Low-latency streaming and WebSocket support. Users appreciate diarization quality; occasional model updates can change accuracy.",
                "sources": ["https://deepgram.com/pricing"],
            },
            "notes": "Token-based auth. Supports async, streaming, and hosted models.",
        },
        {
            "id": "assemblyai",
            "name": "AssemblyAI",
            "pricing": {
                "speech_to_text": "$0.015 per minute",
                "realtime": "$0.0004 per second",
                "audio_intelligence": "$0.0005 per second add-on",
            },
            "reviews": {
                "summary": "Developer-friendly API with LeMUR summarisation. Free tier generous for prototyping; enterprise users mention responsive support.",
                "sources": ["https://www.assemblyai.com/pricing"],
            },
            "notes": "Offers custom models and content moderation classifiers. Requires project token.",
        },
    ],
    "llm_inference": [
        {
            "id": "openai",
            "name": "OpenAI Platform",
            "pricing": {
                "gpt-4o": {
                    "input": "$5 per 1M tokens",
                    "output": "$15 per 1M tokens",
                },
                "gpt-4o-mini": {
                    "input": "$0.15 per 1M tokens",
                    "output": "$0.60 per 1M tokens",
                },
                "realtime": "$5 per 1M input tokens + $15 per 1M output tokens",
            },
            "reviews": {
                "summary": "High-quality models with tool calling and vision support. Rate limits and content policy enforcement are common pain points.",
                "sources": ["https://openai.com/api/pricing"],
            },
            "notes": "API keys scoped per project. Pricing subject to change—monitor announcements.",
        },
        {
            "id": "anthropic",
            "name": "Anthropic Claude",
            "pricing": {
                "claude_3_5_haiku": {
                    "input": "$1 per 1M tokens",
                    "output": "$5 per 1M tokens",
                },
                "claude_3_5_sonnet": {
                    "input": "$3 per 1M tokens",
                    "output": "$15 per 1M tokens",
                },
            },
            "reviews": {
                "summary": "Strong reasoning and constitutional AI safeguards. Developers cite consistent outputs; context window currently 200k tokens.",
                "sources": ["https://www.anthropic.com/api#pricing"],
            },
            "notes": "Supports cache + prompt compression. Requires Claude Console org key.",
        },
        {
            "id": "google_gemini",
            "name": "Google Gemini",
            "pricing": {
                "gemini_2.0_flash": {
                    "input": "$0.10 per 1M tokens",
                    "output": "$0.40 per 1M tokens",
                },
                "gemini_2.0_pro": {
                    "input": "$3.50 per 1M tokens",
                    "output": "$10.50 per 1M tokens",
                },
            },
            "reviews": {
                "summary": "Tight integration with Google Cloud, Vertex AI caching. Some developers note slower rollout of new features outside US regions.",
                "sources": ["https://ai.google.dev/pricing"],
            },
            "notes": "Supports response caching (up to 85% discount). Authentication via Google service account.",
        },
        {
            "id": "openrouter",
            "name": "OpenRouter",
            "pricing": {
                "platform_fee": "10% on top of upstream provider cost",
                "examples": {
                    "gpt-4o-mini": "$0.0008 per 1K input tokens",
                    "claude-3-haiku": "$0.0012 per 1K input tokens",
                },
            },
            "reviews": {
                "summary": "Unified endpoint for multi-provider routing. Community applauds flexible model selection; caution advised for model-specific ToS.",
                "sources": ["https://openrouter.ai/pricing"],
            },
            "notes": "Requires routing key + per-provider keys when using pass-through mode.",
        },
        {
            "id": "azure_openai",
            "name": "Azure OpenAI",
            "pricing": {
                "gpt-4o": {
                    "input": "$5 per 1M tokens",
                    "output": "$15 per 1M tokens",
                },
                "gpt-4o-mini": {
                    "input": "$0.15 per 1M tokens",
                    "output": "$0.60 per 1M tokens",
                },
                "region_variation": "Rates vary by Azure region (e.g. East US vs. West Europe).",
            },
            "reviews": {
                "summary": "Enterprise compliance, VNet, and customer-managed keys available. Provisioning quotas can take days—plan ahead.",
                "sources": [
                    "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/"
                ],
            },
            "notes": "Authentication via Azure AD + resource endpoint. Supports content filters configurable per deployment.",
        },
    ],
}


def catalog_for(category: str) -> List[ProviderEntry]:
    """
    Return provider entries for *category*.  Unknown categories yield an empty list.
    """

    return list(CATALOG.get(category, ()))


def find_provider(provider_id: str) -> ProviderEntry | None:
    """
    Search the catalog for *provider_id* across all categories.
    """

    needle = provider_id.lower()
    for entries in CATALOG.values():
        for entry in entries:
            if entry.get("id", "").lower() == needle:
                return entry
    return None


__all__ = ["CATALOG", "catalog_for", "find_provider"]
