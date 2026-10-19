from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://motranscript:motranscript@127.0.0.1:3307/motranscript"
    hf_token: str = ""
    secret_key: str = "change-me-in-production"
    data_dir: Path = Path("./data")
    model_cache_dir: Path = Path("./data/models")
    whisper_model: str = "Systran/faster-whisper-large-v3"
    whisper_device: str = "auto"
    whisper_compute_type: str = "float16"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    worker_poll_interval: float = 2.0
    enable_diarization: bool = True
    lortograf_use_llm: bool = False
    inference_backend: str = "local"
    runpod_api_key: str = ""
    runpod_endpoint_id: str = ""
    runpod_job_timeout_sec: int = 2400
    public_base_url: str = ""
    transcribe_enabled: bool = True

    @property
    def sources_dir(self) -> Path:
        return self.data_dir / "sources"

    @property
    def segments_dir(self) -> Path:
        return self.data_dir / "segments"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for path in (
        settings.data_dir,
        settings.sources_dir,
        settings.segments_dir,
        settings.exports_dir,
        settings.uploads_dir,
        settings.model_cache_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings
