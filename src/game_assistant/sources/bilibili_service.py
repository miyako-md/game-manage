import asyncio
import json
import logging
import math
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from game_assistant.auth.store import CredentialStore
from .bilibili import BilibiliClient, SourceError, collect_pages, RULE_VERSION
from .bilibili_store import BilibiliStore

logger = logging.getLogger(__name__)

class BilibiliSaveBusy(SourceError):
    pass

class BilibiliService:
    def __init__(self, settings, sources, client_factory=BilibiliClient):
        self.settings, self.sources, self.client_factory = settings, sources, client_factory
        self.store = BilibiliStore(settings.db_path)
        self.credentials = CredentialStore(Path(settings.db_path).with_suffix('.bilibili.credentials.json'))
        self.tasks = {}
        self.loop_task = None

    def login_state(self):
        return {'configured': bool(self.credentials.load().get('bilibili', {}).get('sessdata'))}

    def save_credentials(self, values):
        if any(not t.done() for t in self.tasks.values()):
            raise SourceError('采集进行中，请结束后保存登录信息')
        allowed = ('sessdata', 'bili_jct', 'buvid3', 'buvid4', 'dedeuserid', 'ac_time_value')
        self.credentials.save({'bilibili': {k: unquote(str(values[k]).strip()) for k in allowed if values.get(k)}})
        for game, uid in self.sources.items(): self.store.set_state(game, uid, next_retry=0)

    def commit_verified_account(self, account):
        from game_assistant.auth.bilibili_provider import VerifiedBilibiliAccount, LIMITS
        if not isinstance(account, VerifiedBilibiliAccount):
            raise TypeError('Verified account required')
        if any(not task.done() for task in self.tasks.values()):
            raise BilibiliSaveBusy()
        saved = self.credentials.load()
        saved['bilibili'] = {k: v for k, v in account.credentials.items() if k in LIMITS}
        saved['bilibili_meta'] = {'uid': account.uid, 'nickname': account.nickname, 'validated_at': account.validated_at}
        self.credentials.save(saved)
        warning = False
        for game, uid in self.sources.items():
            try:
                self.store.set_state(game, uid, next_retry=0)
            except Exception:
                warning = True
        return {'warning': '账号已保存，采集刷新可重试'} if warning else {}

    def statuses(self):
        from .public_content import visible_article
        result = []
        for game, uid in self.sources.items():
            rows = self.store.rows(game, uid, days=self.settings.bilibili_history_days, limit=10000)
            result.append({**self.store.state(game, uid), 'running': bool(self.tasks.get(game) and not self.tasks[game].done()),
                'total': len(rows), 'accepted': sum(r['decision'] == 'accepted' for r in rows),
                'article_count': sum(visible_article(r) for r in rows),
                'reasons': dict(Counter(r['reason_text'] for r in rows)), 'history_days': self.settings.bilibili_history_days})
        return result

    def news(self, game):
        uid = self.sources.get(game)
        if not uid: return []
        state = self.store.state(game, uid)
        from .public_content import visible_article
        return [{**r, 'content_status': r.get('content_status') or ('full' if r['decision'] == 'accepted' else 'unavailable'),
                 'content_error': r.get('content_error') or ('历史记录未验证正文完整性，下方为已读取内容，请查看原文。' if r['decision'] != 'accepted' and not r.get('content_status') else ''),
                 'source_stale': bool(r.get('last_observation_error')) or (state.get('status') == 'error' and r.get('fetched_at', '') < state.get('last_attempt', ''))} for r in
                self.store.rows(game, uid, days=self.settings.bilibili_history_days, limit=10000) if visible_article(r)][:1000]

    def calendar(self, game):
        from .public_content import calendar_from_posts
        return calendar_from_posts(self.news(game), game)

    def trigger(self, game, backfill=False):
        if game not in self.sources: raise SourceError('该游戏未配置B站来源')
        if game in self.tasks and not self.tasks[game].done(): return
        self.tasks[game] = asyncio.create_task(self.run(game, backfill))

    async def run(self, game, backfill=False):
        uid = self.sources[game]
        previous = self.store.state(game, uid)
        if time.time() < previous.get('next_retry', 0): return
        now = datetime.now(timezone.utc)
        # Re-read originals after rule changes; cached decisions may predate
        # the incremental window and do not retain raw completeness flags.
        full = backfill or not previous.get('history_complete') or previous.get('rule_version') != RULE_VERSION
        days = self.settings.bilibili_history_days
        if not full and previous.get('last_success'):
            days = min(days, max(2, math.ceil((now - datetime.fromisoformat(previous['last_success'])).total_seconds()/86400) + 1))
        window = f'{days}天' + ('历史回补' if full else '增量采集')
        diagnostic = None
        self.store.set_state(game, uid, status='running', message=f'正在进行{window}',
                             pages=0, last_attempt=now.isoformat(), diagnostic=None)
        def on_page(rows, page):
            self.store.save_rows(game, uid, rows)
            self.store.set_state(game, uid, pages=page)
        def on_diagnostic(values):
            nonlocal diagnostic
            # Values come from the collector's scalar allowlist, never raw SDK data.
            diagnostic = {'game_id': game if game in ('nte', 'wuthering_waves', 'endfield', 'league_of_legends') else 'other', **values}
            self.store.set_state(game, uid, diagnostic=diagnostic)
        try:
            client = self.client_factory(uid, self.credentials.load().get('bilibili', {}))
            result = await collect_pages(client.page, uid, now, days=days,
                mode='backfill' if full else 'incremental', on_page=on_page, on_diagnostic=on_diagnostic)
            values = dict(status='ok', message='历史回补完成' if full else '增量采集完成',
                          last_success=now.isoformat(), failures=0, next_retry=time.time()+30, rule_version=RULE_VERSION)
            if full: values.update(history_complete=True, coverage_since=result['cutoff'])
            self.store.set_state(game, uid, **values)
        except asyncio.CancelledError:
            self.store.set_state(game, uid, status='error', message=f'{window}中断，已保留已有记录和上次成功状态')
            raise
        except Exception as error:
            # Do not log exception text/types or arbitrary upstream values.
            logger.warning("B站采集失败 diagnostic=%s", json.dumps(diagnostic, ensure_ascii=False))
            failures = previous.get('failures', 0) + 1
            message = str(error) if isinstance(error, SourceError) else 'B站数据处理失败，已保留成功记录'
            self.store.set_state(game, uid, status='error', message=message, failures=failures,
                                 next_retry=time.time()+min(3600, 60*2**min(failures, 5)))

    async def _loop(self):
        while True:
            for game in self.sources: self.trigger(game)
            await asyncio.sleep(max(600, self.settings.bilibili_poll_seconds))

    def start(self):
        self.loop_task = asyncio.create_task(self._loop())

    async def close(self):
        tasks = [t for t in [self.loop_task, *self.tasks.values()] if t]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.store.close()
