#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号草稿发布工具
支持上传封面图片、创建草稿文章
"""

import os
import sys
import json
import time
import importlib.util
import requests
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# 凭证与平台/视角配置统一由项目根目录的 preferences.py 解析：
# openwrite.example.yaml 是占位模板，真实值写在被 Git 忽略的 openwrite.yaml 中。
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_preferences():
    """加载项目配置模块，保持与 openwrite.py 相同的解析规则"""
    path = PROJECT_ROOT / 'preferences.py'
    if not path.is_file():
        raise FileNotFoundError(f"找不到项目配置模块: {path}")
    spec = importlib.util.spec_from_file_location('openwrite_preferences', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WeChatPublisher:
    """微信公众号草稿发布器"""

    BASE_URL = "https://api.weixin.qq.com/cgi-bin"
    TOKEN_CACHE_DIR = os.path.expanduser("~/.wechat-publisher")

    # 微信API错误码映射
    ERROR_CODES = {
        40001: "AppSecret错误或者AppSecret不属于这个AppID",
        40002: "请确保grant_type字段值为client_credential",
        40013: "不合法的AppID，请检查AppID是否正确",
        40125: "无效的appsecret，请检查AppSecret是否正确",
        40164: "调用接口的IP地址不在白名单中",
        41001: "缺少access_token参数",
        42001: "access_token超时，请检查缓存是否正常",
        45009: "接口调用超过限制（每日API调用量已用完）",
        47003: "参数错误，请检查必填字段是否完整",
        48001: "api功能未授权，请确认公众号类型",
        50005: "用户未关注公众号",
        -1: "系统繁忙，请稍后重试"
    }

    def __init__(self, root=None, account=None):
        """初始化发布器；root 默认为项目根目录，account 指定公众号账号名"""
        self.root = Path(root).expanduser().resolve() if root else PROJECT_ROOT
        self.preferences = load_preferences()
        self.config_file = self.root / self.preferences.CONFIG_NAME
        self.account = account
        self.appid = None
        self.appsecret = None
        self.access_token = None
        self.author = None
        self.token_cache_file = None
        self.load_config()

    def load_config(self):
        """只从项目 openwrite.yaml 读取指定账号的凭证；模板仅是 setup 用的打样"""
        try:
            self.account = self.preferences.choose_account(self.root, 'wechat', self.account)
            credentials = self.preferences.require_wechat_credentials(self.root, self.account)
        except ValueError as exc:
            raise ValueError(f"微信凭证配置无效:\n{exc}")

        self.appid = credentials['appid']
        self.appsecret = credentials['appsecret']
        self.author = credentials['author']
        # 多账号各自缓存 token，避免不同公众号之间串用凭证
        self.token_cache_file = os.path.join(self.TOKEN_CACHE_DIR, f"token_cache.{self.appid}.json")

        # 验证格式
        if not self.appid.startswith('wx') or len(self.appid) != 18:
            print("⚠ 警告: AppID格式可能不正确（应为wx开头的18位字符）")

        source = self.config_file.name if self.config_file.is_file() else self.preferences.TEMPLATE_NAME
        print(f"✓ 配置加载成功 (账号: {self.account}，AppID: {self.appid[:6]}***，来源: {source})")

    def save_author(self, author: str):
        """将作者名回写到项目 openwrite.yaml 的当前账号，保留其余配置与注释"""
        self.preferences.set_account_author(self.root, self.account, author)
        self.author = author
        print(f"✓ 作者已保存到 {self.config_file}（账号 {self.account}）")

    def _handle_api_error(self, errcode: int, errmsg: str, context: str = "") -> str:
        """统一处理API错误，返回友好的中文提示"""
        chinese_msg = self.ERROR_CODES.get(errcode, errmsg)
        error_detail = f"{context}失败 (错误码{errcode}): {chinese_msg}"

        # 提供针对性的解决建议
        if errcode == 40164:
            error_detail += "\n\n💡 解决方法："
            error_detail += "\n  1. 登录微信公众平台 https://mp.weixin.qq.com"
            error_detail += "\n  2. 设置与开发 → 基本配置 → IP白名单"
            error_detail += "\n  3. 添加当前服务器IP"
            try:
                import socket
                ip = socket.gethostbyname(socket.gethostname())
                error_detail += f"\n  4. 当前IP可能是: {ip}"
            except:
                pass

        elif errcode in [40001, 40125, 40013]:
            error_detail += "\n\n💡 解决方法："
            error_detail += "\n  1. 检查 openwrite.yaml 中当前账号的 app_id 和 app_secret 是否正确"
            error_detail += f"\n  2. 配置文件位置: {self.config_file}"
            error_detail += "\n  3. AppID应该以wx开头，长度18位"

        elif errcode == 45009:
            error_detail += "\n\n💡 解决方法："
            error_detail += "\n  API调用次数已达上限，请明天再试"
            error_detail += "\n  或联系微信公众平台提升配额"

        return error_detail

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        获取access_token，优先使用缓存

        Args:
            force_refresh: 是否强制刷新token

        Returns:
            access_token字符串
        """
        # 尝试从缓存读取
        if not force_refresh and os.path.exists(self.token_cache_file):
            try:
                with open(self.token_cache_file, 'r') as f:
                    cache = json.load(f)

                # 检查token是否过期（提前5分钟刷新）
                if time.time() < cache.get('expires_at', 0) - 300:
                    print("✓ 使用缓存的access_token")
                    return cache['access_token']
            except Exception as e:
                print(f"⚠ 读取token缓存失败: {e}")

        # 请求新的token
        print("→ 正在获取新的access_token...")
        url = f"{self.BASE_URL}/token"
        params = {
            'grant_type': 'client_credential',
            'appid': self.appid,
            'secret': self.appsecret
        }

        response = requests.get(url, params=params)
        result = response.json()

        if 'errcode' in result:
            error_msg = self._handle_api_error(
                result['errcode'],
                result.get('errmsg', 'Unknown error'),
                context="获取access_token"
            )
            raise Exception(error_msg)

        access_token = result['access_token']
        expires_in = result.get('expires_in', 7200)

        # 缓存token
        os.makedirs(os.path.dirname(self.token_cache_file), exist_ok=True)
        cache_data = {
            'access_token': access_token,
            'expires_at': time.time() + expires_in,
            'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }

        with open(self.token_cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
        # access_token 等同于 API 凭证，缓存文件必须收紧权限（仅属主可读写）
        os.chmod(self.token_cache_file, 0o600)

        print(f"✓ 获取access_token成功 (有效期: {expires_in}秒)")
        return access_token

    def upload_image(self, image_path: str, return_url: bool = False):
        """
        上传图片到微信服务器

        Args:
            image_path: 图片文件路径
            return_url: 是否返回图片URL（用于内容图片）

        Returns:
            media_id 或 (media_id, url) 元组
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        print(f"→ 正在上传图片: {os.path.basename(image_path)}")

        token = self.get_access_token()
        url = f"{self.BASE_URL}/material/add_material"

        params = {
            'access_token': token,
            'type': 'image'
        }

        with open(image_path, 'rb') as f:
            files = {'media': (os.path.basename(image_path), f, 'image/jpeg')}
            response = requests.post(url, params=params, files=files)

        result = response.json()

        if 'errcode' in result and result['errcode'] != 0:
            error_msg = self._handle_api_error(
                result['errcode'],
                result.get('errmsg', 'Unknown error'),
                context="上传图片"
            )
            raise Exception(error_msg)

        media_id = result.get('media_id')
        image_url = result.get('url', '')
        print(f"✓ 图片上传成功 (media_id: {media_id})")

        if return_url:
            return media_id, image_url
        return media_id

    def _remove_cover_image(self, content: str) -> str:
        """
        移除HTML中的封面图片

        移除策略：
        1. 移除 <img src="cover.png"> 及其变体
        2. 移除第一个出现的 <img> 标签（通常是封面图）
        3. 保留注释中的封面图引用说明

        Args:
            content: HTML内容

        Returns:
            移除封面图后的HTML内容
        """
        import re

        # 策略1: 移除明确的封面图引用（cover.png, cover.jpg, 封面图等）
        cover_patterns = [
            r'<img[^>]*src=["\']cover\.(png|jpg|jpeg|gif)["\'][^>]*>',  # cover.png
            r'<img[^>]*alt=["\'][^"\']*封面[^"\']*["\'][^>]*>',  # alt包含"封面"
            r'<img[^>]*title=["\'][^"\']*封面[^"\']*["\'][^>]*>',  # title包含"封面"
        ]

        for pattern in cover_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)

        # 策略2: 移除注释后的第一张图片（通常是封面图位置）
        # 匹配：<!-- 注释 --> 后紧跟的 <img> 标签
        content = re.sub(
            r'(<!--[^>]*标题[^>]*-->)\s*<img[^>]*>',
            r'\1',
            content,
            count=1,
            flags=re.IGNORECASE
        )

        return content

    def _upload_content_images(self, content: str, base_dir: str = ".", uploader=None) -> str:
        """
        扫描HTML中的本地图片并上传到微信，替换为微信URL

        Args:
            content: HTML内容
            base_dir: 图片所在的基础目录

        Returns:
            替换后的HTML内容
        """
        import re
        from pathlib import Path

        # 正则匹配所有 <img src="本地路径"> 标签
        img_pattern = r'<img([^>]*?)src=["\']([^"\']+)["\']([^>]*?)>'

        uploaded_count = 0

        def replace_image(match):
            nonlocal uploaded_count
            before_src = match.group(1)
            src = match.group(2)
            after_src = match.group(3)

            # 跳过已经是HTTP/HTTPS的图片
            if src.startswith(('http://', 'https://')):
                return match.group(0)


            # 构建完整路径
            image_path = Path(base_dir) / src

            if not image_path.exists():
                raise FileNotFoundError(f"正文图片不存在，中止发布: {src}")

            try:
                # 上传图片并获取URL
                _, wechat_url = (uploader or self.upload_image)(str(image_path), return_url=True)

                if wechat_url:
                    uploaded_count += 1
                    # 替换为微信URL
                    return f'<img{before_src}src="{wechat_url}"{after_src}>'
                else:
                    raise ValueError(f"正文图片未返回 URL，中止发布: {src}")

            except Exception as e:
                raise ValueError(f"正文图片上传失败，中止发布: {src}") from e

        # 执行替换
        content = re.sub(img_pattern, replace_image, content, flags=re.IGNORECASE)

        if uploaded_count > 0:
            print(f"  ✓ 成功上传 {uploaded_count} 张内容图片")

        return content

    def _fix_wechat_editor_issues(self, content: str) -> str:
        """
        修复微信编辑器的样式破坏问题

        解决的问题：
        1. 编辑模式下莫名空行（HTML换行符被渲染）
        2. 样式错位（text-indent、margin被重置）
        3. 布局打乱（vertical-align失效）
        4. 字体变大（font-size被重置）
        5. 段落缩进（微信默认添加text-indent: 2em）

        Args:
            content: HTML内容

        Returns:
            修复后的HTML内容
        """
        import re

        # === 核心修复：将带背景色的 div/section 转换为 table（微信编辑器会保留 table 的背景色）===
        def add_important_to_style(style):
            """给style中的所有CSS属性添加 !important"""
            declarations = style.split(';')
            important_declarations = []

            for decl in declarations:
                decl = decl.strip()
                if not decl:
                    continue

                # 如果已经有 !important，保持不变
                if '!important' in decl:
                    important_declarations.append(decl)
                else:
                    # 否则添加 !important
                    important_declarations.append(decl + '!important')

            return ';'.join(important_declarations) + ';'

        # 转换计数器
        conversion_count = {'converted': 0, 'excluded': 0}

        def convert_bg_div_to_table(match):
            """将带背景色的 div/section 转换为 table 结构"""
            tag = match.group(1)  # div 或 section
            style = match.group(2)  # style 属性内容
            content = match.group(3)  # 内部内容

            # 排除不应该转换的情况：
            # 1. 排除最外层容器（background-color: #ffffff 且包含 font-family）
            if 'font-family' in style and 'ffffff' in style.lower():
                conversion_count['excluded'] += 1
                return match.group(0)

            # 2. 排除纯白色背景且没有边框的元素（可能是容器）
            # 去除空格后检查
            style_no_space = style.replace(' ', '')
            if ('background:#ffffff' in style_no_space or 'background-color:#ffffff' in style_no_space) and 'border' not in style:
                conversion_count['excluded'] += 1
                return match.group(0)

            # 只转换真正需要的背景色区块
            if 'background' not in style.lower():
                return match.group(0)

            # 给所有CSS属性添加 !important（关键：确保微信编辑器不会覆盖样式）
            style_important = add_important_to_style(style)

            # 提取 margin 值（如果有）
            margin_match = re.search(r'margin[^:]*:\s*([^;!]+)', style)
            margin = margin_match.group(1).strip() if margin_match else '0'

            # 构建 table 结构（添加圆角）
            # border-collapse:separate 才能让圆角生效，overflow:hidden 确保内容不会超出圆角
            table_html = f'<table style="width:100%!important;border-collapse:separate!important;border-spacing:0!important;border-radius:10px!important;overflow:hidden!important;margin:{margin}!important;"><tr><td style="{style_important}">{content}</td></tr></table>'
            conversion_count['converted'] += 1
            return table_html

        # 转换所有带 style 且包含 background 的 div/section（但排除 span 等行内元素）
        content = re.sub(
            r'<(div|section)\s+style="([^"]*background[^"]*)"[^>]*>(.*?)</\1>',
            convert_bg_div_to_table,
            content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # 打印转换统计
        print(f"  → 背景色区块转换: 成功转换 {conversion_count['converted']} 个, 排除 {conversion_count['excluded']} 个")

        # === 超级压缩：彻底删除所有空白（这是关键！）===
        # 1. 删除所有标签间的空白和换行符
        content = re.sub(r'>\s+<', '><', content)

        # 2. 删除标签后的空白（包括标签内的换行）
        content = re.sub(r'>\s+', '>', content)
        content = re.sub(r'\s+<', '<', content)

        # 3. 压缩多个连续空格为一个（保留正常文本中的空格）
        content = re.sub(r'  +', ' ', content)

        # === 微信编辑器兼容性修复：CSS属性处理 ===
        # 1. 保留 border-radius 但添加 !important（尝试保留圆角效果）
        content = re.sub(r'border-radius:\s*([^;!]+);', r'border-radius:\1!important;', content)

        # 2. 移除 box-shadow（阴影，微信编辑器确实不支持）
        content = re.sub(r'box-shadow:\s*[^;]+;\s*', '', content)

        # 3. 移除 text-shadow
        content = re.sub(r'text-shadow:\s*[^;]+;\s*', '', content)

        # 4. 处理背景样式（微信编辑器对背景的限制）
        # 4.1 移除渐变背景（微信不支持 linear-gradient）
        content = re.sub(r'background:\s*linear-gradient[^;]+;', '', content)

        # 4.2 统一 background 为 background-color 并添加 !important
        content = re.sub(r'\bbackground:\s*([#a-fA-F0-9]+);', r'background-color:\1!important;', content)

        # 4.3 确保所有 background-color 都有 !important
        content = re.sub(r'background-color:\s*([^;!]+);', r'background-color:\1!important;', content)

        # 5. 将所有 <section> 改为 <div>（避免额外空行）
        content = content.replace('<section', '<div')
        content = content.replace('</section>', '</div>')

        # 6. 优化 margin（保持舒适间距，避免过于紧凑）
        # 保留卡片间的间距（18px），只压缩过大的margin
        content = re.sub(r'margin-bottom:\s*([3-9]\d+|[1-9]\d{2,})px;', 'margin-bottom:18px;', content)  # 只压缩>=30px的
        content = re.sub(r'margin:\s*\d+px\s+0\s+\d+px\s+0;', 'margin:0 0 18px 0;', content)

        # === 核心修复2：在最外层容器强制禁用缩进和设置字体大小 ===
        # 修复微信编辑器默认添加的 text-indent: 2em
        content = re.sub(
            r'(<div[^>]*style="[^"]*)(">)',
            lambda m: m.group(1) + ' text-indent: 0 !important; font-size: 15px !important;' + m.group(2),
            content,
            count=1  # 只修改第一个div（外层容器）
        )

        # === 样式修复：确保所有关键样式不被微信编辑器破坏 ===

        # 1. text-indent 强制为 0 且使用 !important（彻底禁用缩进）
        content = re.sub(r'text-indent:\s*[^;!]+;', 'text-indent: 0 !important;', content)
        content = re.sub(r'text-indent:\s*0;', 'text-indent: 0 !important;', content)

        # 给所有没有 text-indent 的 style 属性添加
        content = re.sub(
            r'style="(?![^"]*text-indent)([^"]*)"',
            r'style="\1 text-indent: 0 !important;"',
            content
        )

        # 2. margin 统一处理（保持舒适的段落间距和呼吸感）
        # 段落的 margin 设置为舒适值
        content = re.sub(
            r'margin:\s*0\s+0\s+\d+px\s+0;',
            'margin: 0 0 18px 0 !important;',
            content
        )
        content = re.sub(
            r'margin-bottom:\s*\d+px;',
            'margin-bottom: 18px !important;',
            content
        )
        # section/卡片 之间的间距（调整为18px，更自然）
        content = re.sub(
            r'margin:\s*\d+px\s+0;',
            'margin: 0 0 18px 0 !important;',
            content
        )

        # 3. 添加 !important 到关键对齐属性
        # vertical-align（防止圆形序号错位）
        content = re.sub(
            r'vertical-align:\s*([^;!]+);',
            r'vertical-align: \1 !important;',
            content
        )

        # text-align（防止对齐错位）
        content = re.sub(
            r'text-align:\s*([^;!]+);',
            r'text-align: \1 !important;',
            content
        )

        # 4. display 属性加 !important（防止布局打乱）
        content = re.sub(
            r'display:\s*inline-block;',
            'display: inline-block !important;',
            content
        )

        # 5. line-height 加 !important（防止行高被重置）
        content = re.sub(
            r'line-height:\s*([^;!]+);',
            r'line-height: \1 !important;',
            content
        )

        # 6. font-size 加 !important（防止字体变大）
        content = re.sub(
            r'font-size:\s*([^;!]+);',
            r'font-size: \1 !important;',
            content
        )

        # 7. padding 加 !important（防止内边距变化）
        content = re.sub(
            r'padding:\s*([^;!]+);',
            r'padding: \1 !important;',
            content
        )

        # === 圆角优化：只给卡片表格（单行无<th>的表格）添加圆角 ===
        # 1. 将 border-collapse: collapse 改为 separate（允许圆角）- 只对卡片表格
        # 数据表格（含<th>）保持 collapse 不变

        def add_rounded_corners_to_card_tables(match):
            """只给卡片表格（不含<th>的表格）添加圆角"""
            table_html = match.group(0)
            # 如果表格包含 <th>（数据表格），不添加圆角
            if '<th' in table_html.lower():
                return table_html
            # 卡片表格：添加圆角
            table_html = table_html.replace(
                'border-collapse: collapse;',
                'border-collapse:separate;border-spacing:0;overflow:hidden!important;'
            ).replace(
                'border-collapse:collapse;',
                'border-collapse:separate;border-spacing:0;overflow:hidden!important;'
            )
            # 给table添加圆角
            table_html = re.sub(
                r'<table\s+style="',
                '<table style="border-radius:10px!important;',
                table_html
            )
            # 给td添加圆角
            table_html = re.sub(
                r'(<td\s+style="[^"]*)(">)',
                r'\1border-radius:10px!important;\2',
                table_html
            )
            return table_html

        # 匹配完整的表格并处理
        content = re.sub(
            r'<table[^>]*>.*?</table>',
            add_rounded_corners_to_card_tables,
            content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # 4. 去除相关资源部分的边框（让结尾更简洁）
        content = re.sub(
            r'border-top:\s*1px\s+dashed\s+#ccc;',
            '',
            content
        )

        # === 图片圆角优化：让所有图片都圆润 ===
        # 给所有 img 标签添加圆角（修复后的正则）
        content = re.sub(
            r'<img([^>]*style="[^"]*)"',
            r'<img\1;border-radius:8px!important;"',
            content
        )

        # 给没有 style 属性的 img 添加圆角
        content = re.sub(
            r'<img(?![^>]*style)([^>]*)>',
            r'<img\1 style="border-radius:8px!important;">',
            content
        )

        return content

    def create_draft(self,
                    title: str,
                    content: str,
                    author: str = "",
                    thumb_media_id: str = "",
                    digest: str = "",
                    show_cover_pic: int = 1,
                    content_base_dir: str = ".", prepare_only=False,
                    image_uploader=None) -> Dict[str, Any]:
        """
        创建草稿文章

        Args:
            title: 文章标题
            content: 文章内容（HTML格式）
            author: 作者
            thumb_media_id: 封面图片的media_id
            digest: 摘要
            show_cover_pic: 是否显示封面，1显示，0不显示
            content_base_dir: 内容图片所在目录（默认当前目录）

        Returns:
            创建结果
        """
        # 1. 自动移除封面图片（封面已通过API单独上传）
        content = self._remove_cover_image(content)

        # 2. 上传内容中的其他图片并替换为微信URL
        print("\n→ 正在处理内容中的图片...")
        content = self._upload_content_images(content, content_base_dir, image_uploader)

        # 3. 修复微信编辑器的样式破坏问题
        content = self._fix_wechat_editor_issues(content)
        print("✓ 已优化HTML格式（防止编辑模式样式错位）")

        # 微信字段长度限制
        MAX_AUTHOR_BYTES = 20      # 作者名20字节
        MAX_DIGEST_BYTES = 120     # 摘要120字节
        MAX_TITLE_CHARS = 64       # 标题64字符（微信官方限制）
        MAX_TITLE_BYTES = 192      # 标题最大字节数（64汉字×3字节）

        # 自动截断超长字段（按字节）
        def truncate_by_bytes(text, max_bytes):
            """按字节截断文本"""
            encoded = text.encode('utf-8')
            if len(encoded) <= max_bytes:
                return text
            # 逐字符截断直到字节数符合要求
            for i in range(len(text), 0, -1):
                truncated = text[:i]
                if len(truncated.encode('utf-8')) <= max_bytes:
                    return truncated
            return ""

        original_title = title
        title_chars = len(title)
        title_bytes = len(title.encode('utf-8'))

        # 优先按字符数检查（微信官方限制是64字符）
        if title_chars > MAX_TITLE_CHARS:
            print(f"\n⚠️  标题过长警告")
            print(f"原标题: {original_title}")
            print(f"长度: {title_chars} 字符（限制: {MAX_TITLE_CHARS} 字符）")

            # 按字符数截断
            title = title[:MAX_TITLE_CHARS]
            print(f"已截断为: {title}")
            print(f"\n提示: 您可以在微信编辑器中手动修改为完整标题\n")
        # 备用检查：如果字节数超过192（极端情况）
        elif title_bytes > MAX_TITLE_BYTES:
            print(f"\n⚠️  标题字节数过长")
            print(f"原标题: {original_title}")
            print(f"字节数: {title_bytes} 字节（限制: {MAX_TITLE_BYTES} 字节）")

            # 按字节截断
            title = truncate_by_bytes(title, MAX_TITLE_BYTES)
            print(f"已截断为: {title}")
            print(f"\n提示: 您可以在微信编辑器中手动修改为完整标题\n")

        print(f"→ 正在创建草稿: {title}")

        if author:
            original_author = author
            author = truncate_by_bytes(author, MAX_AUTHOR_BYTES)
            if author != original_author:
                print(f"⚠ 作者名超长，已自动截断：{original_author} → {author}")

        if not digest:
            digest = truncate_by_bytes(title, 54)  # 使用标题（最多54字节）作为摘要

        original_digest = digest
        digest = truncate_by_bytes(digest, MAX_DIGEST_BYTES)
        if digest != original_digest:
            print(f"⚠ 摘要超长，已自动截断")


        # 构建文章数据
        articles = {
            "articles": [{
                "title": title,
                "author": author,
                "digest": digest,
                "content": content,
                "content_source_url": "",
                "thumb_media_id": thumb_media_id,
                "show_cover_pic": show_cover_pic,
                "need_open_comment": 0,
                "only_fans_can_comment": 0
            }]
        }

        if prepare_only:
            return articles

        token = self.get_access_token()
        url = f"{self.BASE_URL}/draft/add?access_token={token}"
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        # 手动序列化JSON，确保中文不被转义
        data = json.dumps(articles, ensure_ascii=False).encode('utf-8')
        response = requests.post(url, data=data, headers=headers)
        result = response.json()

        if 'errcode' in result and result['errcode'] != 0:
            # 如果是token过期，尝试刷新token后重试
            if result['errcode'] in [40001, 42001]:
                print("⚠ access_token已过期，正在刷新...")
                self.access_token = self.get_access_token(force_refresh=True)
                token = self.access_token
                url = f"{self.BASE_URL}/draft/add?access_token={token}"
                data = json.dumps(articles, ensure_ascii=False).encode('utf-8')
                response = requests.post(url, data=data, headers=headers)
                result = response.json()

                if 'errcode' in result and result['errcode'] != 0:
                    error_msg = self._handle_api_error(
                        result['errcode'],
                        result.get('errmsg', 'Unknown error'),
                        context="创建草稿"
                    )
                    raise Exception(error_msg)
            else:
                error_msg = self._handle_api_error(
                    result['errcode'],
                    result.get('errmsg', 'Unknown error'),
                    context="创建草稿"
                )
                raise Exception(error_msg)

        print(f"✓ 草稿创建成功!")
        print(f"  media_id: {result.get('media_id')}")

        return result

    def prepare_draft_add(self):
        """Fetch before the journal becomes in_flight; consumed once by add."""
        self._draft_add_token = self.get_access_token()

    def draft_request(self, operation, payload):
        """Single bounded request; draft/add is NEVER replayed automatically."""
        if operation not in ('add', 'get', 'batchget'):
            raise ValueError('Unsupported draft operation')
        token = self.__dict__.pop('_draft_add_token', None) if operation == 'add' else None
        if token is None:
            token = self.get_access_token()
        response = requests.post(
            f'{self.BASE_URL}/draft/{operation}', params={'access_token': token},
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8'}, timeout=(10, 30))
        response.raise_for_status()
        result = response.json()
        if result.get('errcode', 0):
            # Only explicit token rejections prove no creation. Never replay add.
            if result['errcode'] in (40001, 42001):
                try:
                    self.get_access_token(force_refresh=True)
                except Exception:
                    pass  # cannot mask the already-certain rejection
                if operation == 'add':
                    from wechat_reliability import DraftRejected
                    raise DraftRejected(self._handle_api_error(result['errcode'], '', '草稿add'))
            raise ValueError(self._handle_api_error(result['errcode'], '', '草稿' + operation))
        return result


def _redact_secret(text) -> str:
    """脱敏：隐藏错误信息中可能携带的 access_token / secret 参数，避免泄露到终端日志"""
    import re
    text = re.sub(r'(access_token=)[^&\s\'"]+', r'\1***', str(text))
    text = re.sub(r'(secret=)[^&\s\'"]+', r'\1***', text)
    return text


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='微信公众号草稿发布工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s --title "文章标题" --content article.html
  %(prog)s --title "文章标题" --content article.html --cover cover.png --author "作者名"
  %(prog)s --interactive  # 交互式模式
        """
    )

    parser.add_argument('-t', '--title', help='文章标题')
    parser.add_argument('-c', '--content', help='文章内容文件路径（HTML格式）')
    parser.add_argument('-a', '--author', default=None, help='作者（默认: 从 openwrite.yaml 当前账号的 author 读取，无则询问）')
    parser.add_argument('--cover', default='cover.png', help='封面图片路径（默认: cover.png）')
    parser.add_argument('-d', '--digest', help='文章摘要')
    parser.add_argument('--account', help='公众号账号名（openwrite.yaml 中 wechat.accounts 下的键；缺省用唯一账号或 default_account）')
    parser.add_argument('--interactive', action='store_true', help='交互式模式')
    parser.add_argument('--state-dir', help='文章发布状态目录（默认 HTML 同目录的 workflow）')
    parser.add_argument('--bind-media-id', help='绑定未知请求的草稿 ID，仅精确回读，不创建')
    parser.add_argument('--resume-fingerprint', help='恢复指定历史请求，不使用当前文章内容')
    parser.add_argument('--list-draft-candidates', action='store_true', help='只查询最近 20 条候选，未找到不代表未创建')

    args = parser.parse_args()

    try:
        publisher = WeChatPublisher(account=args.account)

        # Historical reads must not prompt or depend on current deliverables.
        if args.list_draft_candidates or args.resume_fingerprint:
            if not args.state_dir:
                raise ValueError('恢复/候选查询必须提供 --state-dir')
            sys.path.insert(0, str(PROJECT_ROOT))
            from wechat_reliability import ReliableDraft
            result = ReliableDraft(publisher, args.state_dir).publish(
                bind_media_id=args.bind_media_id, resume_fingerprint=args.resume_fingerprint,
                list_candidates=args.list_draft_candidates)
            if args.list_draft_candidates:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                print('候选仅供人工定位；未找到不证明未创建，禁止据此重建。')
            else:
                print(f"✓ 草稿上传并精确核验成功 (verified)，media_id: {result['media_id']}")
            return

        # 交互式模式
        if args.interactive:
            print("=== 微信公众号草稿发布工具（交互式） ===\n")
            title = input("请输入文章标题: ").strip()
            content_file = input("请输入内容文件路径 (HTML): ").strip()
            author = input("请输入作者 (可选): ").strip()
            cover = input("请输入封面图片路径 (可选): ").strip()
            digest = input("请输入摘要 (可选): ").strip()
        else:
            if not args.title or not args.content:
                parser.print_help()
                print("\n错误: 必须提供 --title 和 --content 参数")
                sys.exit(1)

            title = args.title
            content_file = args.content
            author = args.author
            cover = args.cover
            digest = args.digest

        # 作者解析：命令行 > 项目 openwrite.yaml 当前账号 > 询问用户
        if not author:
            author = publisher.author
        if not author:
            author = input("请输入作者名: ").strip()
            if not author:
                print("错误: 作者名不能为空")
                sys.exit(1)
            # 回写到项目 openwrite.yaml 当前账号（已被 Git 忽略）
            save_author = input(f"是否将作者 '{author}' 保存到 openwrite.yaml 当前账号？(Y/n): ").strip().lower()
            if save_author in ['', 'y', 'yes']:
                publisher.save_author(author)

        # 读取内容文件
        if not os.path.exists(content_file):
            print(f"错误: 内容文件不存在: {content_file}")
            sys.exit(1)

        with open(content_file, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"\n{'='*50}")
        print(f"标题: {title}")
        print(f"作者: {author or '(未设置)'}")
        print(f"内容文件: {content_file} ({len(content)} 字符)")
        print(f"封面: {cover or '(无)'}")
        print(f"{'='*50}\n")

        sys.path.insert(0, str(PROJECT_ROOT))
        from wechat_reliability import ReliableDraft
        state_dir = args.state_dir or str(Path(content_file).resolve().parent / 'workflow')
        result = ReliableDraft(publisher, state_dir).publish(
            title, content, author, str(Path(cover).resolve()), digest,
            bind_media_id=args.bind_media_id, resume_fingerprint=args.resume_fingerprint,
            list_candidates=args.list_draft_candidates,
            content_base_dir=Path(content_file).resolve().parent)
        if args.list_draft_candidates:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print('候选仅供人工定位；未找到不证明未创建，禁止据此重建。')
            return

        print(f"\n{'='*50}")
        print(f"✓ 草稿上传并精确核验成功 (verified)，media_id: {result['media_id']}")
        print(f"{'='*50}")

    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ 错误: {_redact_secret(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
