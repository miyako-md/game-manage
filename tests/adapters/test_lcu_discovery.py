from pathlib import Path

from game_assistant.adapters.league_of_legends.lcu_discovery import (
    find_credentials_from, find_lockfile_credentials,
)


def test_find_from_process_cmdline():
    procs = [("chrome.exe", ["--x"]), (
        "LeagueClientUx.exe",
        ["--app-port=54321", "--remoting-auth-token=abcTOKEN", "--install-path=D:/x"],
    )]
    assert find_credentials_from(procs) == ("54321", "abcTOKEN")


def test_find_from_process_not_running():
    assert find_credentials_from([("chrome.exe", ["--x"])]) is None


def test_find_from_process_malformed():
    procs = [("LeagueClientUx.exe", ["--app-port=54321"])]  # 缺 token
    assert find_credentials_from(procs) is None


def test_lockfile(tmp_path, monkeypatch):
    lf = tmp_path / "lockfile"
    lf.write_text("1234:54321:abcTOKEN:https", encoding="utf-8")
    assert find_lockfile_credentials([lf]) == ("54321", "abcTOKEN")


def test_lockfile_empty_and_missing(tmp_path):
    empty = tmp_path / "empty.lock"
    empty.write_text("", encoding="utf-8")
    assert find_lockfile_credentials([empty, tmp_path / "nope"]) is None
