import tomllib
from pathlib import Path
from typing import Literal, get_args

from pydantic_settings import BaseSettings
from pydantic import Field


WuwaPublicIpUrl = Literal['https://api.ipify.org', 'https://api64.ipify.org', 'https://checkip.amazonaws.com']
WUWA_PUBLIC_IP_URLS = get_args(WuwaPublicIpUrl)


class Settings(BaseSettings):
    # 0.1.0 之前的模板写过 app_host/app_port，部分用户的 config.toml 仍保留这两个键。
    # 未知键会被拒绝（extra='forbid'），所以这里继续接受它们；一键启动固定监听
    # 127.0.0.1:8010，没有代码读取这两个字段。
    app_host: str = "127.0.0.1"
    app_port: int = 8010
    db_path: str = "data/assistant.db"
    # Explicit cloud entrypoint only; never reuse/import the local single-user DB.
    cloud_db_path: str = "data/cloud.db"
    cloud_allowed_origins: list[str] = ["https://localhost"]
    cloud_session_seconds: int = Field(default=14 * 86400, ge=60, le=90 * 86400)
    cloud_invite_seconds: int = Field(default=48 * 3600, ge=60, le=7 * 86400)
    cloud_recovery_seconds: int = Field(default=900, ge=60, le=3600)
    # Operator-only updater paths; never accepted from API request parameters.
    system_update_enabled: bool = False
    system_update_branch: Literal["main", "codex/cloud-qq-public"] = "main"
    system_update_state_dir: str = ''
    system_update_install_root: str = ''
    cloud_body_limit_bytes: int = Field(default=65536, ge=1024, le=1048576)
    # Independent fixed service credential, provisioned by the operator.
    qq_app_id: str = Field(default='', max_length=256)
    qq_service_token: str = Field(default='', max_length=4096, repr=False)
    qq_dashboard_url: str = Field(default='', max_length=2048)
    qq_dashboard_urls_approved: bool = False
    qq_images_enabled: bool = False
    qq_browser_render_enabled: bool = True
    qq_browser_render_dist_path: str = ''
    qq_browser_render_executable_path: str = ''
    qq_image_font_path: str = ''
    # Conservative cap pending controlled platform acceptance; not a platform limit claim.
    qq_image_max_bytes: int = Field(default=524288, ge=16384, le=1048576)
    # Explicit public-image DNS only; never an automatic fallback or arbitrary URL.
    qq_asset_dns_resolver: Literal['system', 'cloudflare'] = 'system'
    # Account mode is an explicit operator opt-in; missing keys never regenerate.
    cloud_accounts_enabled: bool = False
    cloud_credentials_key_path: str = ''
    cloud_data_root: str = 'data/cloud'
    cloud_private_poll_seconds: int = Field(default=900, ge=60, le=86400)
    # 终末地挑战（森空岛，每轮 1 次签名刷新 + 3 个接口）单独设置，便于限流时放宽。
    cloud_endfield_challenge_poll_seconds: int = Field(default=900, ge=300, le=86400)
    # 公共来源（B站动态、库街区/塔吉多公告、终末地官网、配队推荐）每 6 小时采集一次。
    cloud_public_poll_seconds: int = Field(default=21600, ge=60, le=86400)
    cloud_poll_concurrency: int = Field(default=4, ge=1, le=16)
    cloud_provider_concurrency: int = Field(default=1, ge=1, le=4)
    cloud_upstream_timeout_seconds: int = Field(default=120, ge=5, le=600)
    stamina_seconds: int = 300
    activity_seconds: int = 3600
    announcement_seconds: int = 3600
    news_seconds: int = 14400
    esports_seconds: int = 900
    esports_profiles_seconds: int = 86400
    bilibili_sources: dict[str, str] = {}
    bilibili_history_days: int = 60
    bilibili_poll_seconds: int = 600
    notify_provider: str = "serverchan"  # serverchan | pushplus
    notify_send_key: str = ""
    # 提醒规则：体力满推送 / 满阈值 / 活动临期天数 / 轮询失败告警阈值
    notify_stamina_full: bool = True
    stamina_threshold_percent: int = 90
    nte_city_stamina_threshold_percent: int = Field(default=0, ge=0, le=100)
    activity_remind_days: int = 3
    fail_notify_threshold: int = 3
    wuwa_enabled: bool = True
    # Operator-only HTTPS resolvers; credentials/query/fragment and arbitrary hosts are rejected.
    wuwa_login_public_ip_url: WuwaPublicIpUrl = 'https://api.ipify.org'
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
    # 终末地（官服）凭据由页面短信登录取得并加密保存；以下字段只在运行时由登录服务填写。
    endfield_enabled: bool = True
    endfield_hg_token: str = ""
    endfield_uid: str = ""
    endfield_role_id: str = ""
    endfield_server_id: str = ""
    endfield_channel: str = "official"
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

    def private_poll_seconds(self, game: str, capability) -> int:
        """Cloud per-account polling interval; also the basis of snapshot staleness."""
        if (game, getattr(capability, 'value', capability)) == ('endfield', 'combat'):
            return self.cloud_endfield_challenge_poll_seconds
        return self.cloud_private_poll_seconds

    @classmethod
    def load(cls, path: str = "config.toml") -> "Settings":
        p = Path(path)
        data = tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return cls(**data)
