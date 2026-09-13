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
    # 提醒规则（M3）：体力满推送 / 满阈值 / 活动临期天数 / 轮询失败告警阈值
    notify_stamina_full: bool = True
    stamina_threshold_percent: int = 90
    activity_remind_days: int = 3
    fail_notify_threshold: int = 3
    wuwa_enabled: bool = True
    wuwa_token: str = ""
    wuwa_user_id: str = ""
    # 库街区 APP 端 token：预留字段，当前功能未消费（保留）
    wuwa_app_token: str = ""
    # roleBox 三件套（库街区 APP 内 WebView 会话抓包，教程见 README）：
    # 用于探索度/数据坞；留空 = 该功能未启用，不影响其它功能
    wuwa_b_at: str = ""
    wuwa_dev_code: str = ""
    wuwa_did: str = ""
    lol_enabled: bool = True
    # 异环（塔吉多社区 bbs.tajiduo.com）凭据，抓取教程见 README；
    # 留空 = 仅官方公告可用（公告为匿名接口，无需凭据）
    nte_enabled: bool = True
    nte_access_token: str = ""
    nte_refresh_token: str = ""

    model_config = {"env_prefix": "GA_"}

    @classmethod
    def load(cls, path: str = "config.toml") -> "Settings":
        p = Path(path)
        data = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return cls(**data)
