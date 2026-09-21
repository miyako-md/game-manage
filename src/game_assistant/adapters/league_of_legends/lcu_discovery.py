"""LCU 凭据发现。校准来源：C:\\GPT\\LOLhelper pigeon/lcu.py（国服 WeGame 已验证）。

国服 WeGame 的 lockfile 常为 0 字节，主路径是从 LeagueClientUx 进程
命令行提取 --app-port / --remoting-auth-token（psutil）。
"""
import logging
from collections.abc import Iterable
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

LOCKFILE_CANDIDATES = [
    Path(r"C:\WeGameApps\英雄联盟\LeagueClient\lockfile"),
    Path(r"C:\Riot Games\英雄联盟\lockfile"),
    Path(r"C:\Riot Games\League of Legends\lockfile"),
    Path(r"D:\WeGameApps\英雄联盟\LeagueClient\lockfile"),
    Path(r"D:\Riot Games\英雄联盟\lockfile"),
    Path(r"D:\Riot Games\League of Legends\lockfile"),
]


def find_credentials_from(
    processes: Iterable[tuple[str, list[str] | None]],
) -> tuple[str, str] | None:
    port = token = None
    for name, cmd in processes:
        if "LeagueClientUx" not in (name or "") or not cmd:
            continue
        for arg in cmd:
            if arg.startswith("--app-port="):
                port = arg.split("=", 1)[1]
            elif arg.startswith("--remoting-auth-token="):
                token = arg.split("=", 1)[1]
        if port and token:
            return port, token
    return None


def find_lockfile_credentials(
    candidates: list[Path] = LOCKFILE_CANDIDATES,
) -> tuple[str, str] | None:
    # 标准 Riot lockfile 格式 PID:Port:Password:Protocol。
    # 差异记录：LOLhelper lcu.py 取 parts[2],parts[3] 当 (port,token)，与标准格式
    # 不符（其国服主路径是进程发现，此分支极少执行）；本实现按标准格式。
    for p in candidates:
        try:
            if p.exists() and p.stat().st_size > 0:
                parts = p.read_text(encoding="utf-8", errors="replace").strip().split(":")
                if len(parts) >= 4:
                    if not parts[1] or not parts[2]:
                        continue  # port/password 为空串：残缺 lockfile，跳过
                    return parts[1], parts[2]
        except OSError:
            continue
    return None


def discover_lcu_credentials() -> tuple[str, str] | None:
    procs = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            procs.append((proc.info.get("name") or "", proc.info.get("cmdline")))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    creds = find_credentials_from(procs)
    if creds:
        return creds
    return find_lockfile_credentials()
