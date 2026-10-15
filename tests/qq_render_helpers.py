from io import BytesIO

from PIL import Image

from game_assistant.accounts.models import QueryResult
from game_assistant.qq.rendering import SummaryRenderer


def web_document(name='测试', command='summary'):
    return dict(version=1, command=command, game='nte', roleName=None, now=1792022400000,
        entries=[dict(account=dict(account_id='a', game='nte', provider='tajiduo', state='active',
            capabilities=['account'], roles=[dict(role_id='r', is_default=True)], is_default=True),
            role='r', snapshots={'account':dict(payload={'schema_version':1, 'nickname':name, 'level':0},
                fetched_at='2026-10-15T00:00:00Z', state='ok', complete=None)})],
        publicSnapshots={}, responses={})


def result(text='测试', timestamp='2026-10-12T12:00:00Z'):
    return QueryResult({'web':web_document(text)}, timestamp, 'ok', None)


def png_bytes():
    output = BytesIO()
    Image.new('RGB', (1080, 160), '#14171c').save(output, 'PNG')
    return output.getvalue()


class StubRenderer(SummaryRenderer):
    """Keep the real cache/queue, replacing only Chromium for fast unit tests."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.captures = []

    def _load_static(self):
        self._build_digest = 'fixture-build'

    async def _capture(self, web, assets, deadline):
        self.captures.append(web)
        return png_bytes()
