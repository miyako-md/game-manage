"""Bounded sanitized public PNGs across service restarts; no URLs or account data.

Entries expire 7 days after their last use; the least recently used go first.
"""
from io import BytesIO
import os
from pathlib import Path
import re
import stat
import time
import uuid

from PIL import Image

REF=re.compile(r'qqasset_[0-9a-f]{64}')
MAX_BYTES=1080*1080*4+4096


class PublicPngCache:
    def __init__(self,directory,*,entries=1024,bytes_limit=128*1024*1024,ttl=7*86400):
        self.directory=Path(directory).absolute()
        for path in [self.directory,*self.directory.parents]:
            if path.is_symlink():raise ValueError('qq_public_cache_link_rejected')
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        info=self.directory.stat();self.identity=(info.st_dev,info.st_ino)
        self.entries=max(1,min(entries,1024));self.bytes_limit=max(1,min(bytes_limit,128*1024*1024));self.ttl=min(ttl,7*86400)

    def available(self):
        try:
            info=self.directory.stat()
            return not self.directory.is_symlink() and stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino)==self.identity
        except OSError:return False

    def read(self,ref):
        if not self.available() or not isinstance(ref,str) or not REF.fullmatch(ref):return None
        path=self.directory/(ref+'.png')
        try:
            if not stat.S_ISREG(path.lstat().st_mode):return None
            fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=MAX_BYTES or time.time()-info.st_mtime>self.ttl:return None
                data=stream.read(MAX_BYTES+1)
            with Image.open(BytesIO(data),formats=('PNG',)) as image:
                if image.n_frames!=1 or not 0<image.width<=1080 or not 0<image.height<=1080:return None
                image.verify()
            # A use renews the entry: expiry and eviction count from the last read, not the download.
            try:os.utime(path)
            except OSError:pass
            return data
        except (OSError,ValueError,SyntaxError):return None

    def write(self,ref,png):
        if not self.available() or not isinstance(ref,str) or not REF.fullmatch(ref) or not 0<len(png)<=MAX_BYTES:return
        temporary=self.directory/('.'+uuid.uuid4().hex+'.tmp')
        try:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(png)
            os.replace(temporary,self.directory/(ref+'.png'))
            files=[]
            for path in self.directory.iterdir():
                if path.is_symlink() or not REF.fullmatch(path.stem) or path.suffix!='.png':continue
                info=path.stat()
                if stat.S_ISREG(info.st_mode):files.append((info.st_mtime,path,info.st_size))
            files.sort();total=sum(size for _,_,size in files)
            while len(files)>self.entries or total>self.bytes_limit:
                _,path,size=files.pop(0);path.unlink();total-=size
        except OSError:pass
        finally:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
