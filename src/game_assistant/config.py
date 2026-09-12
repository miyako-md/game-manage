import tomllib
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_host: str = "127.0.0.1"
    app_port: int = 8010  # 8000 被 Windows HTTP.sys 系统服务永久占用
    db_path: str = "data/assistant.db"
    stamina_seconds: int = 300
    activity_seconds: int = 3600
    announcement_seconds: int = 3600
    news_seconds: int = 14400
    notify_provider: str = "serverchan"  # serverchan | pushplus
    notify_send_key: str = ""
    wuwa_enabled: bool = True
    wuwa_token: str = ""
    wuwa_user_id: str = ""

    @classmethod
    def load(cls, path: str = "config.toml") -> "Settings":
        p = Path(path)
        data = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return cls(**data)
