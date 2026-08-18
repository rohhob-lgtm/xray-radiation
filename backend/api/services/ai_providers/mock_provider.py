"""
Mock AI provider — active when no real LLM is configured.

All chat/RAG/research calls return a clear "configure a real LLM" message.
LinkedIn post generation and X-ray image analysis retain lightweight demo
responses since those are standalone features that still need to work in
the absence of a real provider.
"""
from __future__ import annotations
import asyncio
from typing import List, Tuple, Optional, Dict, Any, AsyncIterator

from .base import BaseAIProvider


_NO_LLM_MESSAGE = """\
**No LLM configured — AI answers require a real language model.**

To get answers from your uploaded documents, go to **Settings** and configure one of:

- **OpenAI GPT-4o** — recommended; add your OpenAI API key
- **Ollama** — run a local model (e.g. llama3.1:70b) with no API cost
- **Microsoft Copilot** — use your Azure OpenAI deployment

Once configured, the assistant will:
1. Retrieve the most relevant passages from your knowledge base
2. Send them to the LLM together with your question
3. Return a concise, cited answer

*The current provider ("X-Ray Research Knowledge Base") is a placeholder only.*\
"""


class MockProvider(BaseAIProvider):
    provider_id = "mock"
    provider_name = "X-Ray Research Knowledge Base"
    provider_type = "mock"
    description = (
        "Placeholder provider. Configure OpenAI, Ollama, or Azure Copilot in Settings "
        "to enable real AI answers from your uploaded documents."
    )

    @property
    def is_configured(self) -> bool:
        return True

    async def chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> str:
        return _NO_LLM_MESSAGE

    async def stream_chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        words = _NO_LLM_MESSAGE.split(" ")
        for i, word in enumerate(words):
            yield word if i == len(words) - 1 else word + " "
            await asyncio.sleep(0.008)

    async def generate_linkedin_post(
        self, topic: str, tone: str, length: str, keywords: Optional[List[str]]
    ) -> Tuple[str, List[str]]:
        tone_openers = {
            "professional":       "As X-ray research and security professionals, we recognise that",
            "educational":        "Did you know that",
            "thought_leadership": "The future of X-ray research and security screening depends on",
            "case_study":         "In a recent research deployment,",
            "tips":               "Key insights for X-ray researchers and security engineers:",
        }
        opener = tone_openers.get(tone, "In the field of X-ray research and security,")
        kw_phrase = f" Focal areas: {', '.join(keywords)}." if keywords else ""
        content = (
            f"{opener} {topic} is reshaping what is possible in X-ray imaging and "
            f"security screening science.{kw_phrase}\n\n"
            f"Advances in detector physics, AI-driven threat detection, and low-dose "
            f"imaging algorithms are converging to deliver systems that are simultaneously "
            f"faster, safer, and more accurate than ever before.\n\n"
            f"At X-Ray Research & Innovation, we believe rigorous methodology and "
            f"cross-disciplinary collaboration are the foundations of breakthrough science.\n\n"
            f"What research directions are you most excited about? Let's advance the field together."
        )
        hashtags = [
            "#XRayResearch", "#RadiationPhysics",
            f"#{topic.replace(' ', '').title()[:20]}",
            "#MedicalImaging", "#SecurityScreening", "#DetectorTechnology",
        ]
        return content, hashtags[:6]

    async def analyze_xray_image(
        self, image_base64: str, scanner_type: str, context: Optional[str]
    ) -> Tuple[str, str, List[str]]:
        responses = {
            "baggage": (
                "Standard passenger baggage contents detected. Organic materials consistent "
                "with clothing and personal items. Dense metallic objects consistent with personal "
                "electronics. No anomalous shapes or concealment patterns detected.",
                "clear",
                ["Image appears clear — no items of immediate concern",
                 "Confirm metallic items are declared electronics if required by protocol",
                 "Apply physical inspection protocol if operational doubt remains"],
            ),
            "cargo": (
                "Cargo manifest cross-reference recommended. Dense packing with multiple organic "
                "and inorganic attenuation layers detected. High-Z materials present in sector C4 "
                "warrant secondary screening.",
                "low",
                ["Cross-reference with cargo manifest documentation",
                 "Apply CTX or ETD screening to high-attenuation regions",
                 "Verify shipper against Known Shipper database"],
            ),
            "vehicle": (
                "Engine compartment, cabin, and cargo areas analysed. Structural components "
                "consistent with declared vehicle type. No anomalous cavities identified.",
                "clear",
                ["Scan result: clear",
                 "Conduct secondary physical inspection if protocols mandate",
                 "Log result in vehicle screening management system"],
            ),
            "body": (
                "Body scanner analysis complete. No metallic or non-metallic concealed items "
                "detected across all anatomical regions. Scan within normal parameters.",
                "clear",
                ["No items of concern detected",
                 "Proceed with standard clearance protocol"],
            ),
        }
        findings, threat, recs = responses.get(scanner_type, responses.get("baggage", (
            "X-ray image analysis complete. Configure OpenAI in Settings for detailed AI analysis.",
            "low",
            ["Configure a real AI provider for detailed analysis"],
        )))
        if context:
            findings = f"Operator context: {context}\n\n{findings}"
        return findings, threat, recs
