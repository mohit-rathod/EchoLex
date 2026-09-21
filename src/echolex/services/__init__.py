"""Backward-compatible service imports."""

from echolex.integrations.speech.vllm_omni_tts import (
    VLLMOmniTTSService,
)

SpeachesTTSService = VLLMOmniTTSService

__all__ = ["SpeachesTTSService", "VLLMOmniTTSService"]