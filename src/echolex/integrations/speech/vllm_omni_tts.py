from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TextAggregationMode, TTSService
from pipecat.utils.tracing.service_decorators import traced_tts

from echolex.core.speech_text import prepare_text_for_speech


class VLLMOmniTTSService(TTSService):
    """Pipecat adapter for the vLLM-Omni OpenAI-compatible streaming TTS endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        voice: str,
        language: str = "English",
        speed: float = 1.0,
        sample_rate: int = 24000,
        request_timeout_seconds: float = 60.0,
        api_key: str | None = None,
        **kwargs,
    ) -> None:
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than 0")
        settings = TTSSettings(model=model, voice=voice, language=None)
        super().__init__(
            sample_rate=sample_rate,
            text_aggregation_mode=TextAggregationMode.SENTENCE,
            push_start_frame=True,
            push_stop_frames=True,
            settings=settings,
            **kwargs,
        )

        self._endpoint = f"{base_url.rstrip('/')}/audio/speech"
        self._model = model
        self._voice = voice
        self._language = language
        self._speed = speed
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout_seconds, connect=3.0),
            headers=headers,
        )

    def can_generate_metrics(self) -> bool:
        return True

    async def cleanup(self) -> None:
        await self._client.aclose()
        await super().cleanup()

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        speech_text = prepare_text_for_speech(text)
        if not speech_text:
            return

        payload = {
            "model": self._model,
            "voice": self._voice,
            "input": speech_text,
            "language": self._language,
            "response_format": "pcm",
            "stream": True,
            "stream_format": "audio",
            "sample_rate": self.sample_rate,
            "speed": self._speed,
        }

        try:
            async with self._client.stream("POST", self._endpoint, json=payload) as response:
                if response.status_code != 200:
                    await response.aread()
                    logger.error("tts_http_error status={}", response.status_code)
                    yield ErrorFrame(error=f"TTS service failed with HTTP {response.status_code}")
                    return

                await self.start_tts_usage_metrics(speech_text)
                pending = b""
                first_audio = True

                async for network_chunk in response.aiter_bytes(self.chunk_size):
                    if not network_chunk:
                        continue
                    data = pending + network_chunk
                    usable = len(data) - (len(data) % 2)
                    pending = data[usable:]
                    if usable == 0:
                        continue
                    if first_audio:
                        await self.stop_ttfb_metrics()
                        first_audio = False
                    yield TTSAudioRawFrame(
                        audio=data[:usable],
                        sample_rate=self.sample_rate,
                        num_channels=1,
                        context_id=context_id,
                    )

                if pending:
                    logger.warning("tts_incomplete_pcm_byte_dropped")
                if first_audio:
                    logger.error("tts_empty_audio_stream")
                    yield ErrorFrame(error="TTS service returned no audio")

        except httpx.TimeoutException:
            logger.warning("tts_timeout endpoint={}", self._endpoint)
            yield ErrorFrame(error="TTS service timed out")
        except httpx.HTTPError as exc:
            logger.error("tts_transport_error type={}", type(exc).__name__)
            yield ErrorFrame(error="TTS service request failed")
