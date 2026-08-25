from echolex.chunking import TextChunk as PublicTextChunk
from echolex.config import Settings as PublicSettings
from echolex.core.config import Settings
from echolex.domain.models import TextChunk


def test_original_config_import_path_is_preserved() -> None:
    assert PublicSettings is Settings


def test_original_chunk_model_import_path_is_preserved() -> None:
    assert PublicTextChunk is TextChunk
