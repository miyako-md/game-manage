"""Offline synthetic Vue render check; never reads accounts or sends QQ messages."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import time

from PIL import Image

from game_assistant.accounts.models import AccountScope, QueryResult
from game_assistant.qq.rendering import RenderingUnavailable, SummaryRenderer


def samples():
    now = datetime(2026, 10, 15, 12, tzinfo=timezone(timedelta(hours=8)))
    def snapshot(payload):
        return dict(payload=payload, fetched_at=now.isoformat(), state='ok', complete=None)
    account = dict(account_id='synthetic', game='nte', provider='tajiduo', state='active', is_default=True,
        roles=[dict(role_id='synthetic-role', is_default=True)], capabilities=['account','stamina','roles','gacha'])
    basic = {'account':snapshot(dict(schema_version=1, nickname='合成预览账号', level=70, tycoon_level=30,
        character_count=8, achievement_count=0, achievement_total=300)),
        'stamina':snapshot(dict(schema_version=1, current=120, maximum=240, city_current=40,
            city_maximum=100, daily_activity=80)),
        'roles':snapshot(dict(schema_version=1, entries=[dict(id=str(i),name='合成角色 '+str(i),level=70,
            weapon=dict(name='合成弧盘',level=60)) for i in range(1,9)])),
        'gacha':snapshot(dict(schema_version=1, total_draws=120, s_count=3, pools=[
            dict(name=name, total_draws=40, s_count=1, guarantee=80,
                details=[dict(name='合成出货 '+str(i),pity=40,lucky_type=i)])
            for i,name in enumerate(('角色池','弧盘池','常驻池'),1)]))}
    events = [dict(name='合成跨月活动',start_at=(now-timedelta(days=2)).isoformat(),
        end_at=(now+timedelta(days=20)).isoformat(),source_name='合成公告',category='活动'),
        dict(name='版本更新后开放',start_precision='relative',start_text='版本更新后',
            end_at=(now+timedelta(days=5)).isoformat(),source_name='合成公告')]
    for command in ('summary','roles','gacha','calendar'):
        yield dict(version=1, command=command, game='nte', roleName=None, now=int(now.timestamp()*1000),
            entries=[dict(account=account,role='synthetic-role',snapshots=basic)],
            publicSnapshots={'nte':{'events':snapshot(events),'news':snapshot([])}}, responses={})


async def verify(args):
    output = Path(args.output).absolute() if args.output else None
    if output:
        output.mkdir(parents=True, exist_ok=False)
    renderer = SummaryRenderer(frontend_dist=args.frontend_dist, font_path=args.font, budget_seconds=10)
    reports = []
    try:
        for web in samples():
            started = time.monotonic()
            raw = await renderer.render_summary(AccountScope('synthetic','synthetic','synthetic-role'),
                QueryResult({'web':web},None,'ok',None))
            with Image.open(BytesIO(raw)) as image:
                width,height,format_name = image.width,image.height,image.format
            if output:
                path = output / (web['command'] + ('.png' if format_name == 'PNG' else '.jpg'))
                path.write_bytes(raw)
            reports.append(dict(command=web['command'], width=width, height=height, bytes=len(raw),
                format=format_name, seconds=round(time.monotonic()-started,3)))
        print(json.dumps({'synthetic_only':True,'views':reports},ensure_ascii=True))
        return 0
    finally:
        await renderer.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-dist',required=True)
    parser.add_argument('--font',required=True)
    parser.add_argument('--output',help='New directory for synthetic previews; existing directories are rejected')
    args = parser.parse_args()
    try:
        return asyncio.run(verify(args))
    except (RenderingUnavailable,OSError,ValueError) as error:
        code = str(error) if isinstance(error,RenderingUnavailable) else 'qq_render_check_failed'
        print(json.dumps({'synthetic_only':True,'error':code}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
