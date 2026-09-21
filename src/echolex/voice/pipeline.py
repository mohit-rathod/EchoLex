from __future__ import annotations

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from echolex.core.config import Settings
from echolex.core.prompts import SYSTEM_INSTRUCTION
from echolex.integrations.speech.vllm_omni_tts import VLLMOmniTTSService
from echolex.retrieval.service import get_retriever
from echolex.voice.processors.rag_context import RAGContextProcessor


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Initialize and run one real-time voice assistant session."""
    settings = Settings.from_env()

    stt = OpenAISTTService(
        api_key=settings.stt_api_key,
        base_url=settings.stt_base_url,
        settings=OpenAISTTService.Settings(
            model=settings.stt_model,
            language=settings.stt_language,
        ),
        ttfs_p99_latency=settings.stt_ttfs_p99_seconds,
    )

    llm = OpenAILLMService(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        settings=OpenAILLMService.Settings(
            model=settings.llm_model_name,
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=settings.llm_temperature,
            max_completion_tokens=settings.llm_max_completion_tokens,
        ),
    )

    tts = VLLMOmniTTSService(
        base_url=settings.tts_base_url,
        api_key=settings.tts_api_key,
        model=settings.tts_model,
        voice=settings.tts_voice,
        language=settings.tts_language,
        speed=settings.tts_speed,
        sample_rate=settings.tts_sample_rate,
        request_timeout_seconds=settings.tts_request_timeout_seconds,
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    rag = RAGContextProcessor(
        get_retriever(),
        timeout_seconds=settings.rag_retrieval_timeout_seconds,
        max_context_chars=settings.rag_max_context_chars,
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            rag,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=settings.tts_sample_rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client) -> None:  # noqa: ARG001
        logger.info("webrtc_client_connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client) -> None:  # noqa: ARG001
        logger.info("webrtc_client_disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments) -> None:
    """Pipecat runner entrypoint for SmallWebRTC transport."""
    connection: SmallWebRTCConnection = runner_args.webrtc_connection
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    await run_bot(transport, runner_args)
