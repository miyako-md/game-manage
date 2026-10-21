from io import BytesIO
from pathlib import Path
import os
import time

from PIL import Image
import pytest

from game_assistant.qq.assets import PublicAssetCache
from game_assistant.qq.public_png_cache import PublicPngCache


def png():
    out=BytesIO();Image.new('RGB',(80,60),'white').save(out,'PNG');return out.getvalue()


async def test_restart_uses_sanitized_public_images_without_network(tmp_path,monkeypatch):
    from game_assistant.qq import assets
    async def forbidden(*args,**kwargs):raise AssertionError('unexpected download')
    monkeypatch.setattr(assets,'_download',forbidden)
    cache=PublicAssetCache(disk_directory=tmp_path/'cache')
    url='https://bbs.hycdn.cn/public.png';ref=cache.register_url(url);cache._store(ref,png());await cache.aclose()
    restarted=PublicAssetCache(disk_directory=tmp_path/'cache');assert restarted.register_url(url)==ref
    await restarted.prefetch([ref],budget_seconds=1)
    assert restarted.get_png(ref)==png()
    assert all(path.suffix=='.png' and url not in path.name for path in (tmp_path/'cache').iterdir())
    await restarted.aclose()


def test_disk_cache_bounds_and_invalid_content_do_not_touch_other_files(tmp_path):
    cache=PublicPngCache(tmp_path/'cache',entries=2)
    other=cache.directory/'keep.txt';other.write_text('unrelated')
    for i in range(3):cache.write('qqasset_'+str(i)*64,png())
    assert len(list(cache.directory.glob('qqasset_*.png')))==2 and other.read_text()=='unrelated'
    assert cache.read('../keep') is None
    bad=cache.directory/('qqasset_'+'f'*64+'.png');bad.write_bytes(b'not a PNG')
    assert cache.read(bad.stem) is None
    cache.write('qqasset_'+'e'*64,png());old=cache.directory/('qqasset_'+'e'*64+'.png');os.utime(old,(0,0))
    assert cache.read(old.stem) is None


def test_disk_cache_rejects_linked_directories(tmp_path):
    target=tmp_path/'target';target.mkdir();link=tmp_path/'link'
    try:link.symlink_to(target,target_is_directory=True)
    except OSError:pytest.skip('symlink creation unavailable')
    with pytest.raises(ValueError,match='link_rejected'):PublicPngCache(link)


def test_disk_cache_reads_renew_expiry_and_eviction_order(tmp_path):
    assert PublicPngCache(tmp_path/'default').entries==1024
    cache=PublicPngCache(tmp_path/'cache',entries=2,ttl=100)
    first,second,third=('qqasset_'+str(i)*64 for i in range(3))
    cache.write(first,png());cache.write(second,png())
    old=cache.directory/(first+'.png');os.utime(old,(0,0));os.utime(cache.directory/(second+'.png'),(1,1))
    assert cache.read(first) is None, 'expired by the last use'
    os.utime(old,(old.stat().st_atime,time.time()-50))
    assert cache.read(first)==png() and old.stat().st_mtime>time.time()-5
    cache.write(third,png())
    # The entry just read stays; the one not used since it was written is evicted.
    assert {path.stem for path in cache.directory.glob('qqasset_*.png')}=={first,third}
