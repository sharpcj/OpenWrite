"""Small file-backed WeChat draft journal. No credentials or tokens are persisted here."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import io
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')).encode('utf-8')).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != 'nt':
            directory = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def article_lock(directory):
    """OS-owned lock: crashes release it; never unlink the lock inode."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'wechat-publish.lock').open('a+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0)
                if not stream.read(1):
                    stream.write(b'0')
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('文章正在另一进程发布，请等待；不要删除锁文件') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def image_url_identity(value):
    """Only normalize known WeChat CDN protocol/size variants, never arbitrary hosts."""
    parts = urlsplit(value)
    if (parts.scheme in ('http', 'https') and parts.hostname in (
            'mmbiz.qpic.cn', 'mmbiz.qlogo.cn') and not parts.username
            and not parts.password and parts.port is None and not parts.fragment):
        path = parts.path
        if path.endswith('/0') or path.endswith('/640'):
            path = path.rsplit('/', 1)[0] + '/0'
        return ('wechat-cdn', parts.hostname, path, parts.query)
    return ('exact', value)


class Body(HTMLParser):
    """Compare ordered markup/text; only attribute order/entities/void syntax vary."""
    VOID = {'img', 'br', 'hr', 'meta', 'link', 'input', 'wbr', 'source', 'area', 'base', 'embed', 'param', 'track', 'col'}

    def __init__(self, content, normalize_images=False):
        super().__init__(convert_charrefs=True)
        self.events = []
        self.images = []
        self.normalize_images = normalize_images
        self.feed(content)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            attributes = dict(attrs)
            src = (attributes.get('data-src') or attributes.get('src')) if self.normalize_images else attributes.get('src')
            if not src:
                raise ValueError('正文图片缺少 src/data-src')
            self.images.append(image_url_identity(src) if self.normalize_images else src)
            if self.normalize_images:
                attrs = [(key, value) for key, value in attrs if key not in ('src', 'data-src')]
                attrs.append(('src', json.dumps(image_url_identity(src))))
        self.events.append(('start', tag, sorted(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            self.events.append(('end', tag))

    def handle_data(self, data):
        # Preserve whitespace and text order (including preformatted content).
        if self.events and self.events[-1][0] == 'text':
            self.events[-1] = ('text', self.events[-1][1] + data)
        else:
            self.events.append(('text', data))


def verify(expected, result):
    items = result.get('news_item')
    if not isinstance(items, list) or len(items) != 1:
        raise ValueError('草稿回读文章数量不匹配')
    actual = items[0]
    for field in ('title', 'author', 'digest', 'thumb_media_id'):
        if actual.get(field) != expected[field]:
            raise ValueError('草稿回读字段不匹配: ' + field)
    left = Body(expected['content'], normalize_images=True)
    right = Body(actual.get('content', ''), normalize_images=True)
    if left.images != right.images or left.events != right.events:
        raise ValueError('草稿回读正文/图片身份或顺序不匹配')


class DraftRejected(ValueError):
    """An explicit allowlisted API rejection proves draft/add did not create."""


class ReliableDraft:
    def __init__(self, publisher, directory):
        self.publisher = publisher
        self.directory = Path(directory)
        self.path = self.directory / 'wechat-publish.json'

    def save(self, entry=None):
        if entry is not None:
            entry.setdefault('history', []).append({
                'at': datetime.now(timezone.utc).isoformat(),
                'status': entry['status'], 'media_id': entry.get('media_id')})
        atomic_json(self.path, self.state)

    def load(self):
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {
            'version': 1, 'assets': {}, 'versions': {}}
        if self.state.get('version') != 1:
            raise ValueError('不支持的发布状态版本')
        for entry in self.state['versions'].values():
            if entry['status'] == 'in_flight':
                entry['status'] = 'unknown'
                self.save(entry)

    def upload(self, path, return_url=False):
        path = Path(path)
        digest = sha256(path.read_bytes()).hexdigest()
        key = fingerprint([self.publisher.appid, digest])
        asset = self.state['assets'].get(key)
        if asset is None:
            media_id, url = self.publisher.upload_image(str(path), return_url=True)
            if not media_id or not url or urlsplit(url).scheme not in ('http', 'https'):
                raise ValueError('素材上传未返回有效 ID 和 URL；中止发布')
            asset = {'appid': self.publisher.appid, 'sha256': digest,
                     'media_id': media_id, 'url': url}
            self.state['assets'][key] = asset
            self.save()  # persist EACH success before the next upload
        return (asset['media_id'], asset['url']) if return_url else asset['media_id']

    def read_verify(self, entry):
        # Reads only: no upload or draft/add on any verification failure.
        entry['status'] = 'unverified'
        self.save(entry)
        last = None
        for attempt in range(3):
            try:
                result = self.publisher.draft_request('get', {'media_id': entry['media_id']})
                verify(entry['article'], result)
                entry['status'] = 'verified'
                entry['id_confirmed'] = True
                self.save(entry)
                return entry
            except Exception as exc:
                last = exc
                if attempt < 2:
                    time.sleep(0.1)
        raise ValueError('已保存 media_id，核验未通过；重跑只回读，不重建: ' + str(last))

    def publish(self, title=None, content=None, author=None, cover=None, digest=None,
                bind_media_id=None, resume_fingerprint=None, list_candidates=False,
                content_base_dir=None):
        with article_lock(self.directory):
            self.load()
            if list_candidates:
                # Candidate listing is discovery, NEVER proof of absence or a success record.
                return self.publisher.draft_request('batchget', {
                    'offset': 0, 'count': 20, 'no_content': 0})
            if resume_fingerprint:
                entry = self.state['versions'].get(resume_fingerprint)
                if not entry or entry['appid'] != self.publisher.appid:
                    raise ValueError('恢复指纹不存在或不属于当前账号')
                if bind_media_id:
                    self.bind(entry, bind_media_id)
                if not entry.get('media_id'):
                    raise ValueError('未知请求没有 media_id；请显式绑定后精确核验')
                return self.finish(self.read_verify(entry))
            # A changed title, HTML, image or account cannot evade an unknown request.
            if content is None or cover is None or title is None:
                raise ValueError('新创建必须提供标题、正文和封面')
            blockers = [e for e in self.state['versions'].values()
                        if e['status'] in ('unknown', 'unverified')]
            base = Path(content_base_dir).resolve() if content_base_dir else Path(cover).resolve().parent
            clean = self.publisher._remove_cover_image(content)
            images = []
            for src in Body(clean).images:
                if urlsplit(src).scheme in ('http', 'https'):
                    images.append({'src': src})
                else:
                    path = (base / src).resolve()
                    images.append({'src': src, 'sha256': sha256(path.read_bytes()).hexdigest()})
            def image_identity(path, return_url=False):
                value = sha256(Path(path).read_bytes()).hexdigest()
                return (value, 'https://openwrite.invalid/sha256/' + value)
            cover_hash = sha256(Path(cover).read_bytes()).hexdigest()
            # Run the SAME existing preparation (including truncation) without I/O
            # before lookup. Asset markers bind bytes, independent of uploaded IDs.
            with redirect_stdout(io.StringIO()):
                prepared = self.publisher.create_draft(
                    title, content, author=author, digest=digest,
                    thumb_media_id=cover_hash, content_base_dir=str(base),
                    prepare_only=True, image_uploader=image_identity)
            identity = {'appid': self.publisher.appid, 'article': prepared['articles'][0],
                        'images': [image.get('sha256', image['src']) for image in images],
                        'cover': cover_hash}
            key = fingerprint(identity)
            entry = self.state['versions'].get(key)
            if blockers and (entry not in blockers or len(blockers) != 1):
                raise ValueError('未知请求与当前内容不一致；请用旧 --resume-fingerprint 绑定核验')
            if entry and (entry.get('media_id') or bind_media_id):
                if bind_media_id:
                    self.bind(entry, bind_media_id)
                return self.finish(self.read_verify(entry))
            if entry and entry['status'] == 'unknown':
                raise ValueError('unknown 请求禁止自动创建；使用 --bind-media-id 精确核验')
            if bind_media_id:
                raise ValueError('没有可绑定的已保存请求')
            if entry is None:
                entry = {'fingerprint': key, 'appid': self.publisher.appid,
                         'identity': identity, 'status': 'preparing'}
                self.state['versions'][key] = entry
                self.save(entry)
            thumb = self.upload(cover)
            payload = self.publisher.create_draft(
                title, content, author=author, digest=digest,
                thumb_media_id=thumb, content_base_dir=str(base),
                prepare_only=True, image_uploader=self.upload)
            entry['article'] = payload['articles'][0]
            if any(urlsplit(src).scheme not in ('http', 'https')
                   for src in Body(entry['article']['content']).images):
                raise ValueError('正文仍包含本地图片，禁止创建草稿')
            for image in images:
                if 'sha256' in image and sha256((base / image['src']).read_bytes()).hexdigest() != image['sha256']:
                    raise ValueError('上传过程中正文图片发生变化，中止创建')
            if sha256(Path(cover).read_bytes()).hexdigest() != identity['cover']:
                raise ValueError('上传过程中封面发生变化，中止创建')
            # Final metadata + rewritten HTML + image bytes and account are all bound.
            entry['payload_fingerprint'] = fingerprint([identity, payload])
            # Fetch tokens before in_flight; keep two-argument request mocks.
            prepare_add = getattr(self.publisher, 'prepare_draft_add', None)
            if prepare_add is not None:
                prepare_add()
            entry['status'] = 'in_flight'
            self.save(entry)
            try:
                result = self.publisher.draft_request('add', payload)
                if not result.get('media_id'):
                    raise ValueError('创建未返回 media_id')
                entry['media_id'] = result['media_id']
                entry['status'] = 'unverified'
                self.save(entry)  # save ID BEFORE any readback
            except DraftRejected:
                entry['status'] = 'rejected'
                self.save(entry)
                raise
            except BaseException:
                entry['status'] = 'unknown'
                self.save(entry)
                raise
            return self.finish(self.read_verify(entry))

    def bind(self, entry, media_id):
        if not entry.get('article'):
            raise ValueError('此请求尚未准备完成，不能绑定草稿')
        if entry.get('media_id') and entry['media_id'] != media_id and not (
                entry.get('bound_candidate') and not entry.get('id_confirmed')):
            raise ValueError('禁止替换已保存的 media_id')
        entry.setdefault('bound_candidate', not bool(entry.get('media_id')))
        entry['media_id'] = media_id
        entry['status'] = 'unverified'
        self.save(entry)

    def finish(self, entry):
        if entry['status'] != 'verified':
            raise ValueError('只有 verified 可以记录发布成功')
        atomic_json(self.directory / 'publish-record.json', {
            'version': 1, 'platform': 'wechat', 'title': entry['article']['title'],
            'visibility': 'draft', 'published_at': datetime.now(timezone.utc).isoformat(),
            'media_id': entry['media_id'], 'fingerprint': entry['fingerprint'],
            'payload_fingerprint': entry['payload_fingerprint'], 'status': 'verified',
            'appid': entry['appid']})
        return deepcopy(entry)
