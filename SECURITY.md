# Security and supported use

This is a **single-user local application**. The supported launcher binds to `127.0.0.1:8010`. It is not a public multi-user service: do not expose it through a public listener, port-forward or unauthenticated reverse proxy. Origin/Host checks protect local requests; they are not account authorization for a shared server.

Credentials, databases and runtime logs belong in the ignored `data/` directory. Windows encrypts community credentials with the current user's DPAPI. Back up local data privately; do not attach configuration files, cookies, login responses or database copies to public issues. Use synthetic identifiers in tests and screenshots.

Please report suspected vulnerabilities using GitHub's private vulnerability reporting for this repository when available. If it is unavailable, open a minimal issue requesting a private contact method, without exploit details, credentials or personal data. Never post tokens or SMS codes.

Refreshes query external community services whose data can be delayed or inaccurate. A successful HTTP response or recent local read does not prove that the game state is current. In particular, NTE stamina/city activity may lag behind the game.
