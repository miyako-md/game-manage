# Third-party notices

Game Assistant / 游戏管家 is distributed under **GPL-3.0-only**, as selected by the repository owner. See [LICENSE](LICENSE). Modified project files and original assets are licensed on the same terms; third-party packages retain their own licenses.

## Protocol references and acknowledgements

The community login and game adapters were implemented with reference to the following public protocol clients. This project does not redistribute their bot frameworks, rendering templates, texture packs, custom card designs, or portrait bundles. Protocol compatibility does not imply affiliation with the referenced projects or game publishers.

| Reference | Referenced revision | License / scope |
| --- | --- | --- |
| [NTEUID](https://github.com/tyql688/NTEUID) | `ba7790e13e39f9a825090853498848b51a06c3c9` | [GPL-3.0](https://github.com/tyql688/NTEUID/blob/ba7790e13e39f9a825090853498848b51a06c3c9/LICENSE); Laohu/Tajiduo login, request signing, endpoint and response-field references |
| [WutheringWavesUID](https://github.com/kvcfdd/WutheringWavesUID) | `1d693a2df0f940824cb34e102cec1cf3b381e70f` | [GPL-3.0](https://github.com/kvcfdd/WutheringWavesUID/blob/1d693a2df0f940824cb34e102cec1cf3b381e70f/LICENSE); Kuro login and roleBox session references |
| [Kuro-API-Collection](https://github.com/TomyJan/Kuro-API-Collection) | Endpoint documentation consulted during development | Historical protocol documentation; current behavior is validated by the adapters and tests. Documentation is linked, not bundled. |

Upstream contributors retain their rights to their work. See [community-login.md](docs/community-login.md) for the exact reference files and verification boundaries. Public SDK identifiers and request-signing constants are protocol parameters, not individual user credentials.

## Assets and game names

The bundled `frontend/public/game-icons/*-mark.svg` files are original geometric/text identifiers created for this project and covered by its GPL-3.0-only license. They are not publisher-supplied logos. The downloaded official app icons used during private development are not included in the public repository or its published history.

Game names and trademarks belong to their respective owners. This is an independent, unofficial tool. Images and game data obtained at runtime from official community APIs remain subject to the providers' terms; the project's license does not grant rights to those external assets. No external avatar/card pack is bundled.

## Package dependencies

Python and npm dependencies are installed separately. Their copyright notices and license files remain in the installed distributions. `pyproject.toml`, `uv.lock` and `frontend/package-lock.json` identify the dependencies; consult each package's included license for redistribution obligations. CI checks installation, tests and build; dependency availability or a passing check is not a publisher endorsement.
