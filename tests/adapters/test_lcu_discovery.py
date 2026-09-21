from game_assistant.adapters.league_of_legends.lcu_discovery import (
    discover_lcu_credentials, find_credentials_from, find_lockfile_credentials,
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


def test_lockfile_empty_fields_skipped(tmp_path):
    # lockfile 格式 PID:Port:Password:Protocol，port/password 为空串时须跳过，
    # 不得返回残缺凭据（如 ("", "pass")）
    lf = tmp_path / "lockfile"
    lf.write_text("1234::pass:https", encoding="utf-8")
    assert find_lockfile_credentials([lf]) is None


class _FakeProc:
    def __init__(self, info):
        self.info = info


class _FakePsutil:

    class NoSuchProcess(Exception):
        pass

    class AccessDenied(Exception):
        pass

    @staticmethod
    def process_iter(attrs):
        return [
            _FakeProc({"name": "chrome.exe", "cmdline": ["--x"]}),
            _FakeProc({"name": "LeagueClientUx.exe", "cmdline": [
                "--app-port=54321", "--remoting-auth-token=abcTOKEN",
                "--install-path=D:/x"]}),
        ]


def test_discover_uses_psutil_process_scan(monkeypatch):
    import game_assistant.adapters.league_of_legends.lcu_discovery as discovery
    monkeypatch.setattr(discovery, "psutil", _FakePsutil())
    assert discover_lcu_credentials() == ("54321", "abcTOKEN")
