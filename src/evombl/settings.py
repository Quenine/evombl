from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVOMBL_")
    database_path: Path = Path("data/evombl.duckdb")
    config_dir: Path = Path("config")
