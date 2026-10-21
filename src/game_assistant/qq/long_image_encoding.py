"""Encode at original dimensions. Preserve text geometry and never rescale fonts."""
import io
from PIL import Image
MAX_BYTES=1048576
# The server's uplink to QQ can drop to tens of KB/s; larger renders take the
# palette/JPEG path at original dimensions so the upload fits its time limit.
LOSSLESS_BYTES=400*1024
def encode(png,prefer_palette=False,max_bytes=MAX_BYTES,*,optimize_transfer=False):
    data,metadata=_encode(png,prefer_palette,max_bytes)
    if optimize_transfer and metadata['format']=='png':
        # Repack the already-selected frame. Palette, dimensions and decoded
        # pixels remain unchanged; this cannot trade text clarity for bytes.
        with Image.open(io.BytesIO(data)) as image:
            buffer=io.BytesIO();image.save(buffer,'PNG',compress_level=9,optimize=True)
        candidate=buffer.getvalue()
        if len(candidate)<len(data):
            metadata={**metadata,'lossless_repacked':True,'saved_bytes':len(data)-len(candidate),
                      'method':metadata['method']+'; lossless PNG repack'}
            data=candidate
    return data,metadata


def _encode(png,prefer_palette=False,max_bytes=MAX_BYTES):
    max_bytes=max(1,min(int(max_bytes),MAX_BYTES))
    with Image.open(io.BytesIO(png)) as im:
        if len(png)<=min(LOSSLESS_BYTES,max_bytes):
            return png,{'format':'png','quality':None,'palette':None,'method':'lossless'}
        rgb=im.convert('RGB')
        palettes=[256,192,128,96,64]
        if prefer_palette:
            for colors in palettes:
                b=io.BytesIO();rgb.quantize(colors=colors,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE).save(b,'PNG',compress_level=6)
                candidate=b.getvalue()
                if len(candidate)<=max_bytes:
                    return candidate,{'format':'png','quality':None,'palette':colors,'method':'palette; original dimensions'}
        for q in [92,90,88,85,82,80]:
            b=io.BytesIO();rgb.save(b,'JPEG',quality=q,optimize=True,subsampling=0)
            if len(b.getvalue())<=max_bytes:
                return b.getvalue(),{'format':'jpeg','quality':q,'palette':None,'method':'JPEG 4:4:4; original dimensions'}
        for colors in palettes:
            b=io.BytesIO();rgb.quantize(colors=colors,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE).save(b,'PNG',compress_level=6)
            if len(b.getvalue())<=max_bytes:
                return b.getvalue(),{'format':'png','quality':None,'palette':colors,'method':'palette; original dimensions'}
        raise ValueError('Image cannot meet current transport bytes without reducing dimensions')
