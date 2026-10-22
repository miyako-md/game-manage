# QQ shared Vue image runtime

Official protocol checks, repaired upload fields and platform-side conditions
are recorded in [the 2026-10-17 documentation review](qq-official-compliance.md).
The dimensions and typography below are project reading constraints, not
pixel limits specified by QQ.

QQ images retain the website's authorized Vue display data, game colors and
rounded surfaces. The selected A layout uses 960–1080-pixel single long images.
Calendar images reuse the dashboard's illustrated timeline, showing exactly 14
Beijing dates starting two days before today. Activities continuing beyond the
window retain boundary arrows; dates before the window are omitted. Role, gacha and game reports adapt the shared
content components. Body text uses 26–30 pixels and secondary text at least 22
pixels, with no menus, scrolling rails or decorative motion. Long descriptions
continue without text loss; table records retain their local context. Build both
entries with `npm ci && npm run
build` in `frontend`. The selected screenshot entry is `dist/render-a.html`;
`dist/render.html` remains an internal pagination compatibility entry. Rendering needs no
public screenshot service and does not grant anonymous API access. Existing
cloud static validation accepts its HTML/JS/CSS files. Source maps, credentials,
account profiles and private database files must never be placed in `dist`.

Install the explicitly optional Python extra (`uv sync --extra qq-render`) during
deployment preparation. The locked runtime is Playwright 1.58.0. Install its
matching Chromium and OS libraries in that preparation step, never at service
runtime. Set `qq_browser_render_executable_path` only to the service's dedicated
installed Chromium, or leave empty to use that Playwright installation's default
browser. No user's Chrome/Edge profile or bundled Codex runtime is selected.

`qq_browser_render_enabled` defaults true; `qq_browser_render_dist_path` defaults
to the repository's `frontend/dist`. Configure `qq_image_font_path` to a
service-readable Noto Simplified Chinese font, obtained under its own license.
No Windows font is bundled. Both modes reuse `--font-sans` and the application's
theme tokens; image mode loads those explicit font bytes and validates real CJK
glyphs. Keep the website's Noto family installed/available when comparing modes.
Missing build, font or browser produces the existing text fallback. Game panels
and notices use the same runtime; no Pillow card renderer remains.

The A renderer retains a bounded browser context with no storage state or account
token, timezone Asia/Shanghai, reduced motion and blocked service workers. Each
job unmounts the prior Vue application, clears its model configuration, and
mounts only the current authorized snapshot. It disposes that DOM immediately
after capture. Only the fixed render entry, its built assets,
configured font and pre-sanitized public asset cache can resolve. API requests,
external navigation and unexpected resources abort; attempts at active requests
invalidate rendering. Optional missing images show placeholders; required font
or unstable/omitted content fails readiness. The job/fingerprint marker must
match before a selected complete page is captured.

Public role guides use the project's existing 46 Wuwa and 23 NTE guide entries
and their reviewed role/equipment/skill icons. `攻略`, `鸣潮 攻略`,
`异环 角色攻略 角色名` and the other game prefixes are public reads; they do not
resolve bindings or collect private account data. Missing Endfield guide content
remains explicitly unavailable while retaining its public role context; the reply
names 猫冬MT「终末地攻略合集」 on Bilibili as a search hint, without a link.

On the cloud (cloud accounts enabled) the static catalog stays the base and the QQ
reply reads the website's guide caches synchronously on every request (no upstream
request, nothing cached in the process): `GuideUpdates.cached_by_id` for WuWa and
`GuideService.status`/`cached` for the two NTE posts. A WuWa entry shows the
catalog content unless the stored extraction has all five sections reviewed (the
website rule), plus 「库街区有新攻略帖，待核查（检查于 …）」 when the preferred new post
is not among the shown sources. A WuWa role without a catalog entry, resolved by
name through `guide_jobs.guide_roster()`, shows its stored extraction with the
header mark 「自动提炼·待校对」. NTE adds 「原帖有更新，摘要待复核」 when the post
fingerprint changed. Pages show 「攻略检查于 …」 when the time is known and the
source image count with a pointer to the website; original images are never sent.
These lines travel in the whitelisted `guide.freshness` field (`mark`, at most four
`lines` of 120 characters). Without the services (cloud accounts disabled) the
reply is exactly the static catalog reply.

The existing public asset cache has a bounded disk tier at `qq-public-assets`
beside the cloud data directory: at most 512 sanitized PNGs, 128 MiB and seven
days. It stores opaque URL/mode hashes and PNG bytes, with no URLs, account data,
credentials or uploaded file_info. Prewarming reviewed current assets during
release preparation keeps a service restart from downloading 153 medal icons in
the first reply's five-second asset budget. Memory remains capped at 256 images
and 32 MiB; network allowlists, DNS validation and source limits are unchanged.

The existing queue admits at most ten requests and runs one worker. The total
caller budget remains at most ten seconds. Cancelling an HTTP await does not free
the worker until the browser job finishes/closes its context. Shutdown drains the
queue and closes Chromium/Playwright. Cache entries include user/account/role,
all grants/snapshot fingerprints, payload/page/theme, font contents and built
component contents. Invalidation prevents results from being inserted again.
Final link/grant checks still occur after render; this alone is not an atomic
guarantee across QQ upload/send or concurrent revocation on the remote platform.

The outbound protocol remains one image with `msg_seq=1`. A retains the original
text size and image dimensions: at most 1080 pixels wide, 16000 pixels tall,
16 million pixels and 1 MiB. Fast capture is encoded as lossless or palette PNG,
with readable JPEG as a bounded fallback. Content exceeding those limits returns
the existing text explanation; it is never cropped or silently omitted. A has
one page; later pages report its available range. Calendar and Endfield medal
images additionally repack the selected PNG losslessly, accepting only a smaller
result with the same dimensions, palette and decoded pixels. Other A images keep
their existing encoding path. Upload receives up to 40 seconds
while reserving 5 seconds for the reply and remains bounded by the passive reply
deadline. Uncertain uploads are not retried and file_info is not cached.
The request passes its timeout explicitly to the QQ SDK: the SDK's default
30-second argument otherwise overrides the HTTPX client's configured timeout.
Connect/pool waits are capped at five seconds and the outer upload deadline still
covers the entire call. Files-only timing logs record numeric wire bytes,
connection, TLS, body-send and response-header wait durations. Trace metadata,
URLs, account identifiers, request bodies, credentials and file_info are never
logged. Measure upload separately from sample downloads: these share the host's
outbound bandwidth and can materially delay the request body.

The internal compatibility `pages` renderer retains the earlier behavior: blocks
paginate into at most 100 pages, each at most 1440 pixels tall including its
header and footer. Content keeps its readable size rather than shrinking the
whole document. Every page geometry and the complete content-block count must
validate before any selected page can be captured; omitted or oversized blocks
fail rendering rather than returning a clipped page. `render_snapshot.page` is
one-based, and only that page is captured. The response exposes `page` and
`total_pages`; page numbers and next commands are visible in the image and
response fallback text. The bot still sends just the selected image, with no
automatic multi-image burst. Continuation commands preserve the original query,
game and selected role. Read-only help, stamina and calabash queries can also
paginate; action replies such as refresh fall back to text if they would require
multiple pages, so a next-page command never repeats an action. Each page retains the existing hard pixel/byte
limits and PNG/JPEG encoding checks. Out-of-range requests report the available range.
Calendar receives the complete authorized public activity snapshot before legacy
text-card truncation. Wuwa gacha currently reads the existing ledger window of
at most 500 items/gold rows; its full aggregate is preserved, with an explicit
visible window notice when rows exceed that window. NTE imported ledger content
is currently a summary, separately from community S-record details. Neither
mode invents missing history or claims complete official calendar coverage.

Before deployment, measure this exact Linux Chromium/font build under the
existing systemd memory/task/CPU limits, verify its sandbox works without adding
`--no-sandbox`, and check shutdown. Windows isolated PNG evidence is not proof of
Linux resource limits, production installation or real QQ receipt.

For local browser acceptance, set `QQ_RENDER_TEST_EXECUTABLE` and
`QQ_RENDER_TEST_FONT`, build frontend, then run
`pytest -q tests/test_qq_browser_rendering.py`. Without these explicit paths,
real-browser tests skip and must not be reported as browser acceptance.


Calendar and event images enrich the complete event projection from the existing
public `news` cache only. Pictures belong to an event through an exact source
URL/post ID, or an explicitly matching version's declared `start_source`; titles
and dates never establish ownership. NTE API post links and public forum links
share their exact post ID, including the exact official
`www.tajiduo.com/bbs/index.html#/post?postId=<digits>` route; other fragments
remain rejected. Calendar/event/news titles never trigger character-catalog art. News timestamps/state/content participate in snapshot
fingerprints. News `cover_url` and `image_urls` become sanitized `images` candidates
for the shared announcement component. No live article collection runs on a QQ
query, and absent artwork leaves the original event text intact.

Public artwork is a separate cache mode, bounded to a 1080-pixel longest edge;
ordinary icons retain 192 pixels and reviewed Endfield loadout portraits retain
512. References and fingerprints include the mode, so a cached thumbnail cannot
replace a cover. All modes keep the same anonymous URL allowlist, pinned public
DNS/TLS connection and redirect refusal. Icons and portraits retain a 2 MiB /
4-million-pixel source limit. Artwork alone allows at most 6 MiB and 12 million
source pixels, including bounded Content-Length, chunked and unframed reads;
this admits official 3840×2160 JPEG covers while retaining bounded output.
Artwork downloads may use up to five seconds (`artwork_request_timeout`,
independently configurable); icons and portraits retain the three-second
`request_timeout` default. Every fetch is shortened to the remaining shared
prefetch deadline, still at most five seconds within the ten-second reply budget.
No retry extends that deadline. The renderer serves only already sanitized
in-memory PNGs. Mounted image
URLs and exact public character/weapon/skill catalog matches are prefetched;
NTE roster images omit hidden equipment/skills, and full Endfield portraits are
reserved for loadouts. Missing and newly available image fingerprints produce
different screenshot cache keys.

Calendar pages reuse a shared version cover once in each continued game header,
while independently illustrated activities keep their own compact image. Dates
with minute precision do not inherit an uncertain-day label, and equivalent
source date strings are not repeated. Character, weapon, equipment and gacha
record art remain visible where supplied or identified by the reviewed catalog.
Image failures preserve the record and its original text; readiness waits for
the component's image fallback before measuring and paginating.
