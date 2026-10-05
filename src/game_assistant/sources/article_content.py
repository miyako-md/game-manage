"""Plain text and image normalization for existing official article sources.

No requests, credentials, storage or HTML rendering live here.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit


def _image_url(value):
    if not isinstance(value, str):
        return None
    value = 'https:' + value if value.startswith('//') else value
    try:
        parsed = urlsplit(value)
        if (parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username
                and not parsed.password and not any(c.isspace() or ord(c) < 32 for c in value)
                and '\\' not in value):
            return value
    except ValueError:
        pass
    return None


class _Text(HTMLParser):
    BLOCKED = {'script', 'style', 'iframe', 'object', 'template', 'noscript'}
    BREAKS = {'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr', 'br'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.images, self.blocked = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKED:
            self.blocked.append(tag)
        if self.blocked:
            return
        if tag in self.BREAKS:
            self.parts.append('\n')
        if tag == 'img':
            attrs = dict(attrs)
            url = _image_url(attrs.get('jason') or attrs.get('src') or attrs.get('data-src'))
            if url and url not in self.images:
                self.images.append(url)
        if tag in {'td', 'th'}:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
            return
        if tag in self.BREAKS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def article_content(raw):
    parser = _Text()
    parser.feed(raw if isinstance(raw, str) else '')
    body = '\n'.join(line for p in ''.join(parser.parts).splitlines()
                     if (line := re.sub(r'[\t \xa0]+', ' ', p).strip()))
    excerpt = re.sub(r'\s+', ' ', body)
    return {'body': body, 'images': parser.images,
            'summary': excerpt[:180] + ('…' if len(excerpt) > 180 else ''),
            'content_status': 'full' if body or parser.images else 'unavailable',
            'content_error': '' if body or parser.images else '来源未提供可读取的正文'}


def retain_article_bodies(rows, previous):
    """A per-article failure cannot erase a previously successful body."""
    old = {r.get('url') or r.get('id'): r for r in previous if isinstance(r, dict) and (r.get('url') or r.get('id'))}
    result = []
    for value in rows:
        row = value.model_dump(mode='json') if hasattr(value, 'model_dump') else dict(value)
        prior = old.get(row.get('url') or row.get('id'))
        if (row.get('content_status') in ('error', 'unavailable') and prior
                and (prior.get('body') or prior.get('images'))):
            row.update({k: prior.get(k, '' if k != 'images' else []) for k in ('body', 'images', 'summary')})
            row['content_status'] = 'stale'
            row['content_error'] = row.get('content_error') or '正文更新失败，保留上次成功内容'
        result.append(row)
    return result
