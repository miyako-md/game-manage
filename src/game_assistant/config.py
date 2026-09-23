import tomllib
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 0.1.0 之前的模板写过 app_host/app_port，部分用户的 config.toml 仍保留这两个键。
    # 未知键会被拒绝（extra='forbid'），所以这里继续接受它们；一键启动固定监听
    # 127.0.0.1:8010，没有代码读取这两个字段。
    app_host: str = "127.0.0.1"
    app_port: int = 8010
    db_path: str = "data/assistant.db"
    stamina_seconds: int = 300
    activity_seconds: int = 3600
    announcement_seconds: int = 3600
    news_seconds: int = 14400
    bilibili_sources: dict[str, str] = {}
    bilibili_history_days: int = 60
    bilibili_poll_seconds: int = 600
    notify_provider: str = "serverchan"  # serverchan | pushplus
    notify_send_key: str = ""
    # 提醒规则：体力满推送 / 满阈值 / 活动临期天数 / 轮询失败告警阈值
    notify_stamina_full: bool = True
    stamina_threshold_percent: int = 90
    activity_remind_days: int = 3
    fail_notify_threshold: int = 3
    wuwa_enabled: bool = True
    wuwa_token: str = ""
    wuwa_token_source: str = "h5"  # legacy web token; SDK login persists ios
    wuwa_user_id: str = ""
    # 库街区 APP 端 token：已停用，只为兼容旧版配置模板，任何代码都不读取它。
    wuwa_app_token: str = ""
    # roleBox会话由页面短信登录自动取得；以下字段保留旧手填配置兼容。
    # 会话供体力、进度、角色、探索度和数据坞等能力使用。
    wuwa_b_at: str = ""
    wuwa_dev_code: str = ""
    wuwa_did: str = ""
    wuwa_role_id: str = ""
    wuwa_server_id: str = ""
    lol_enabled: bool = True
    # 异环凭据由页面短信登录取得；以下字段保留旧配置兼容。
    # 未登录时私人能力不可用，公共来源独立运行。
    nte_enabled: bool = True
    nte_access_token: str = ""
    nte_refresh_token: str = ""
    nte_device_id: str = ""
    nte_role_id: str = ""
    auth_store_path: str = ""  # empty: adjacent to db_path, *.credentials.json
    auth_allowed_origins: list[str] = [
        "http://127.0.0.1:8010", "http://localhost:8010",
        "http://127.0.0.1:5173", "http://localhost:5173",
    ]
    # 异环旧版手填活动：TOML数组表 [[nte_events]]，作为原适配器回退数据。每项
    # name/category/start/end；start/end 为 "YYYY-MM-DD HH:MM"（服务器时间
    # UTC+8）。非空时优先于原适配器扫描；API层再按手游B站主来源规则合并。
    nte_events: list[dict] = []

    model_config = {"env_prefix": "GA_"}

    @classmethod
    def load(cls, path: str = "config.toml") -> "Settings":
        p = Path(path)
        data = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return cls(**data)
