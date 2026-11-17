#!/usr/bin/env python3
"""Online image sources: paid generation APIs and free stock libraries.

Backends:
- fal      : fal.ai queue API (FLUX / Recraft), key FAL_KEY or FAL_AI_API_KEY.
- hunyuan  : Tencent Hunyuan via TokenHub (Bearer), key TENCENT_TOKENHUB_API_KEY.
- pexels / pixabay / unsplash : free stock search + download, keys in .env.

All addresses and keys come from image_config (.env / environment); model
choices come from config.json. Functions return a local file plus provenance
metadata; produce.py performs the final decode and dimension checks.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import time

import requests


def _load_sibling(name: str):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(os.path.abspath(__file__)), f'{name}.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


image_config = _load_sibling('image_config')

HUNYUAN_V35_URL = 'https://tokenhub.tencentmaas.com/v1/wand/hunyuan-image/v35-generation'
HUNYUAN_V3_URL = 'https://tokenhub.tencentmaas.com/v1/wand/hunyuan-image/v3-generation'
FAL_QUEUE_URL = 'https://queue.fal.run'
POLL_INTERVAL = 2


def _require_key(backend: str) -> str:
    key = image_config.backend_key(backend)
    if not key:
        keys = ' 或 '.join(image_config.BACKEND_KEYS[backend])
        raise ValueError(f'{backend} 未配置密钥；请在项目 .env 填写 {keys}')
    return key


def _download(url: str, output: Path, timeout: int = 120) -> Path:
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with open(output, 'wb') as handle:
            for chunk in response.iter_content(chunk_size=65536):
                handle.write(chunk)
    if not output.is_file() or output.stat().st_size == 0:
        raise ValueError(f'下载的图片为空：{url}')
    return output


def _round_multiple(value: int, base: int) -> int:
    return max(base, int(round(value / base)) * base)


def generate_fal(prompt: str, output: Path, width: int, height: int, timeout: int) -> dict:
    """fal.ai queue API: submit, poll status, fetch the result image."""
    key = _require_key('fal')
    model = image_config.online_model('fal')
    headers = {'Authorization': f'Key {key}', 'Content-Type': 'application/json'}
    payload = {'prompt': prompt, 'num_images': 1,
               'image_size': {'width': _round_multiple(width, 32),
                              'height': _round_multiple(height, 32)}}
    if 'recraft' in model:
        payload['style'] = 'realistic_image'
    response = requests.post(f'{FAL_QUEUE_URL}/{model}', json=payload,
                             headers=headers, timeout=60)
    if response.status_code >= 400:
        raise ValueError(f'fal.ai 提交失败（HTTP {response.status_code}）：{response.text[:300]}')
    task = response.json()
    status_url, response_url = task.get('status_url'), task.get('response_url')
    if not status_url or not response_url:
        raise ValueError(f'fal.ai 未返回任务地址：{json.dumps(task)[:300]}')
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = requests.get(status_url, headers=headers, timeout=30).json()
        state = status.get('status')
        if state == 'COMPLETED':
            break
        if state in ('FAILED', 'ERROR'):
            raise ValueError(f'fal.ai 任务失败：{json.dumps(status, ensure_ascii=False)[:300]}')
        time.sleep(POLL_INTERVAL)
    else:
        raise ValueError(f'fal.ai 任务超时（{timeout}s），可稍后凭 request_id 查询：{task.get("request_id")}')
    result = requests.get(response_url, headers=headers, timeout=60).json()
    images = result.get('images') or []
    if not images or not images[0].get('url'):
        raise ValueError(f'fal.ai 未返回图片：{json.dumps(result, ensure_ascii=False)[:300]}')
    url = images[0]['url']
    _download(url, output)
    return {'source_url': url, 'model': model}


def _hunyuan_size(width: int, height: int, model: str) -> str:
    """Scale the requested size into the model's legal range, keeping ratio."""
    if model == 'hy-image-v3':
        low, high, max_area = 512, 2048, 1024 * 1024
    else:
        low, high, max_area = 256, 8192, 16777216
    scale = max(low / width, low / height, 1.0)
    if width * height * scale * scale > max_area:
        scale = (max_area / (width * height)) ** 0.5
    w = min(high, max(low, int(round(width * scale))))
    h = min(high, max(low, int(round(height * scale))))
    return f'{w}x{h}'


def generate_hunyuan(prompt: str, output: Path, width: int, height: int, timeout: int) -> dict:
    """Tencent Hunyuan via TokenHub; synchronous, returns a temporary URL."""
    key = _require_key('hunyuan')
    model = image_config.online_model('hunyuan')
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    size = _hunyuan_size(width, height, model)
    if model == 'hy-image-v3':
        url, payload = HUNYUAN_V3_URL, {'model': model, 'prompt': prompt, 'size': size}
    else:
        url = HUNYUAN_V35_URL
        payload = {'model': model, 'size': size,
                   'messages': [{'role': 'user',
                                 'content': [{'type': 'text', 'text': prompt}]}]}
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if response.status_code >= 400:
        raise ValueError(f'混元 TokenHub 调用失败（HTTP {response.status_code}）：{response.text[:300]}')
    result = response.json()
    if result.get('error'):
        raise ValueError(f'混元 TokenHub 返回错误：{json.dumps(result["error"], ensure_ascii=False)[:300]}')
    if model == 'hy-image-v3':
        data = result.get('data') or []
        image_url = data[0].get('url') if data else None
    else:
        choices = result.get('choices') or []
        image = (choices[0].get('delta') or {}).get('image') if choices else None
        image_url = (image or {}).get('url')
    if not image_url:
        raise ValueError(f'混元 TokenHub 未返回图片：{json.dumps(result, ensure_ascii=False)[:300]}')
    _download(image_url, output)
    return {'source_url': image_url, 'model': model}


def generate_online(backend: str, prompt: str, output: Path,
                    width: int, height: int, timeout: int) -> dict:
    if backend == 'fal':
        return generate_fal(prompt, output, width, height, timeout)
    if backend == 'hunyuan':
        return generate_hunyuan(prompt, output, width, height, timeout)
    raise ValueError(f'未知在线生图后端：{backend}')


def _orientation(width: int, height: int) -> str:
    if width > height * 1.15:
        return 'landscape'
    if height > width * 1.15:
        return 'portrait'
    return 'squarish'


def _search_pexels(query: str, key: str, width: int, height: int) -> list:
    orientation = _orientation(width, height)
    params = {'query': query, 'per_page': 20}
    if orientation != 'squarish':
        params['orientation'] = orientation
    response = requests.get('https://api.pexels.com/v1/search', params=params,
                            headers={'Authorization': key}, timeout=30)
    if response.status_code >= 400:
        raise ValueError(f'Pexels 搜索失败（HTTP {response.status_code}）：{response.text[:200]}')
    candidates = []
    for photo in response.json().get('photos', []):
        src = photo.get('src') or {}
        candidates.append({
            'download': src.get('large2x') or src.get('original'),
            'width': photo.get('width', 0), 'height': photo.get('height', 0),
            'page': photo.get('url', ''),
            'attribution': f'Photo by {photo.get("photographer", "unknown")} on Pexels',
        })
    return candidates


def _search_pixabay(query: str, key: str, width: int, height: int) -> list:
    orientation = _orientation(width, height)
    params = {'key': key, 'q': query, 'image_type': 'photo', 'per_page': 20}
    if orientation == 'landscape':
        params['orientation'] = 'horizontal'
    elif orientation == 'portrait':
        params['orientation'] = 'vertical'
    response = requests.get('https://pixabay.com/api/', params=params, timeout=30)
    if response.status_code >= 400:
        raise ValueError(f'Pixabay 搜索失败（HTTP {response.status_code}）：{response.text[:200]}')
    candidates = []
    for hit in response.json().get('hits', []):
        candidates.append({
            'download': hit.get('fullHDURL') or hit.get('largeImageURL') or hit.get('webformatURL'),
            'width': hit.get('imageWidth', 0), 'height': hit.get('imageHeight', 0),
            'page': hit.get('pageURL', ''),
            'attribution': f'Image by {hit.get("user", "unknown")} on Pixabay',
        })
    return candidates


def _search_unsplash(query: str, key: str, width: int, height: int) -> list:
    orientation = _orientation(width, height)
    params = {'query': query, 'per_page': 20}
    if orientation != 'squarish':
        params['orientation'] = orientation
    headers = {'Authorization': f'Client-ID {key}'}
    response = requests.get('https://api.unsplash.com/search/photos',
                            params=params, headers=headers, timeout=30)
    if response.status_code >= 400:
        raise ValueError(f'Unsplash 搜索失败（HTTP {response.status_code}）：{response.text[:200]}')
    candidates = []
    for photo in response.json().get('results', []):
        urls, user = photo.get('urls') or {}, photo.get('user') or {}
        candidates.append({
            'download': urls.get('regular') or urls.get('full'),
            'download_tracking': (photo.get('links') or {}).get('download_location'),
            'width': photo.get('width', 0), 'height': photo.get('height', 0),
            'page': (photo.get('links') or {}).get('html', ''),
            'attribution': f'Photo by {user.get("name", "unknown")} on Unsplash',
        })
    return candidates


_STOCK_SEARCH = {'pexels': _search_pexels, 'pixabay': _search_pixabay, 'unsplash': _search_unsplash}


def _pick_candidate(candidates: list, width: int, height: int) -> dict:
    """Prefer enough resolution, then the closest aspect ratio."""
    usable = [c for c in candidates if c.get('download')]
    if not usable:
        raise ValueError('图库搜索没有返回可用图片；可更换 keywords 重试')
    target_ratio = width / height

    def score(candidate):
        w, h = candidate.get('width') or 0, candidate.get('height') or 0
        ratio = w / h if w and h else target_ratio
        big_enough = 0 if (w >= width and h >= height) else 1
        return (big_enough, abs(ratio - target_ratio))

    return sorted(usable, key=score)[0]


def fetch_stock(backend: str, keywords: list, output: Path,
                width: int, height: int, timeout: int) -> dict:
    """Search a free stock library and download the best-matching photo."""
    if backend not in _STOCK_SEARCH:
        raise ValueError(f'未知图库后端：{backend}')
    key = _require_key(backend)
    query = ' '.join(keywords).strip()
    if not query:
        raise ValueError('图库搜索需要 keywords')
    candidates = _STOCK_SEARCH[backend](query, key, width, height)
    chosen = _pick_candidate(candidates, width, height)
    # Unsplash API guidelines: trigger the download endpoint when fetching.
    tracking = chosen.get('download_tracking')
    if tracking:
        try:
            requests.get(tracking, params={'client_id': key}, timeout=15)
        except requests.RequestException:
            pass
    _download(chosen['download'], output)
    return {'source_url': chosen.get('page') or chosen['download'],
            'attribution': chosen.get('attribution', ''),
            'query': query}
