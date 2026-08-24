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
        """Initialize the Speaches TTS service adapter.

        Args:
            base_url: Base HTTP URL for the Speaches server endpoint.
            model: Name of the TTS model to invoke (e.g., kokoro model ID).
            voice: Voice identifier to use (bypasses standard OpenAI rigid checks).
            speed: Playback or synthesis speech speed multiplier.
            sample_rate: Audio output sample rate in Hertz.
            request_timeout_seconds: Maximum HTTP request/streaming timeout duration.
            **kwargs: Additional configuration parameters passed to parent TTSService.
        """
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
        """Indicate whether this service can track processing metrics.

        Returns:
            True, as this adapter tracks time-to-first-byte (TTFB) and usage.
        """
        return True

    async def cleanup(self) -> None:
        """Clean up underlying network clients gracefully during shutdown."""
        await super().cleanup()
        await self._client.aclose()

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        """Request streaming PCM audio from the Speaches TTS backend.

        Chunks text by sentence, posts payload to the API, and yields raw audio frames
        while preserving byte boundaries for PCM16 audio blocks.

        Args:
            text: Text segment to be synthesized into speech.
            context_id: Unique correlation string tracking the active turn context.

        Yields:
            TTSAudioRawFrame chunks containing raw PCM data, or ErrorFrame items on failure.
        """
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
                # Handle non-success response codes by capturing part of the error payload
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:1000]
                    yield ErrorFrame(
                        error=f"Speaches TTS failed: HTTP {response.status_code}: {body}"
                    )
                    return

                await self.start_tts_usage_metrics(text)
                pending = b""
                first_audio = True
                
                # Stream binary chunks asynchronously from the server response
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

                    # Stop and record Time-To-First-Byte metrics on the first valid audio block
                    if first_audio:
                        await self.stop_ttfb_metrics()
                        first_audio = False

                    yield TTSAudioRawFrame(
                        audio=data[:usable],
                        sample_rate=self.sample_rate,
                        num_channels=1,
                        context_id=context_id,
                    )

                # Log a minor warning if an unaligned single byte remains trailing at stream close
                if pending:
                    logger.warning("Dropping one incomplete PCM byte from Speaches TTS response")
                    
        except httpx.TimeoutException as exc:
            yield ErrorFrame(error=f"Speaches TTS timed out: {exc}")
        except httpx.HTTPError as exc:
            yield ErrorFrame(error=f"Speaches TTS request failed: {exc}")