from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TextAggregationMode, TTSService
from pipecat.utils.tracing.service_decorators import traced_tts


class SpeachesTTSService(TTSService):
    """Pipecat TTS adapter for Speaches' OpenAI-compatible Kokoro/Piper endpoint.

    Pipecat's OpenAITTSService intentionally validates OpenAI's fixed voice names.
    Kokoro uses its own IDs (for example ``af_heart``), so this small adapter avoids
    that provider-specific validation while retaining Pipecat's native TTS frame flow,
    sentence aggregation, interruption semantics, and metrics.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        voice: str,
        speed: float = 1.0,
        sample_rate: int = 24000,
        request_timeout_seconds: float = 30.0,
        **kwargs,
    ) -> None:
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
        self._speed = speed
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout_seconds, connect=3.0),
        )

    def can_generate_metrics(self) -> bool:
        return True

    async def cleanup(self) -> None:
        await super().cleanup()
        await self._client.aclose()

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        payload = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "pcm",
            "stream_format": "audio",
            "sample_rate": self.sample_rate,
            "speed": self._speed,
        }

        try:
            async with self._client.stream("POST", self._endpoint, json=payload) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:1000]
                    yield ErrorFrame(
                        error=f"Speaches TTS failed: HTTP {response.status_code}: {body}"
                    )
                    return

                await self.start_tts_usage_metrics(text)
                pending = b""
                first_audio = True
                async for network_chunk in response.aiter_bytes(self.chunk_size):
                    if not network_chunk:
                        continue

                    # PCM16 must contain complete 2-byte samples. HTTP chunk boundaries
                    # are arbitrary, so carry a trailing odd byte into the next chunk.
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
                    logger.warning("Dropping one incomplete PCM byte from Speaches TTS response")
        except httpx.TimeoutException as exc:
            yield ErrorFrame(error=f"Speaches TTS timed out: {exc}")
        except httpx.HTTPError as exc:
            yield ErrorFrame(error=f"Speaches TTS request failed: {exc}")
