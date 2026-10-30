"""Decode only bounded raster images and emit a fresh, metadata-free JPEG."""
import base64
import binascii
from io import BytesIO
import re

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_AVATAR_TEXT = 280_000
MAX_AVATAR_BYTES = 200_000
MAX_AVATAR_PIXELS = 4_194_304


class AvatarConflict(ValueError):
    pass


def avatar_state(row):
    return {
        'image': 'data:image/jpeg;base64,' + base64.b64encode(row.image).decode('ascii') if row and row.image else None,
        'revision': row.revision if row else None,
    }


def normalize_avatar(value: str) -> bytes:
    if len(value) > MAX_AVATAR_TEXT:
        raise ValueError('裁剪后的图片过大，请重新选择或缩小图片。')
    match = re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)', value)
    if not match:
        raise ValueError('请选择 JPG、PNG 或 WebP 图片。')
    try:
        raw = base64.b64decode(match[2], validate=True)
        if not raw or len(raw) > MAX_AVATAR_BYTES:
            raise ValueError('裁剪后的图片过大或内容为空，请重新选择。')
        expected = {'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP'}[match[1]]
        with Image.open(BytesIO(raw), formats=['JPEG', 'PNG', 'WEBP']) as check:
            width, height = check.size
            if check.format != expected:
                raise ValueError('图片内容与格式不一致，请重新选择图片。')
            if min(width, height) < 32 or max(width, height) > 4096 or width * height > MAX_AVATAR_PIXELS:
                raise ValueError('图片尺寸不合适，请在头像编辑器中重新裁剪。')
            if getattr(check, 'is_animated', False):
                raise ValueError('请使用静态图片作为头像。')
            check.verify()
        with Image.open(BytesIO(raw), formats=['JPEG', 'PNG', 'WEBP']) as source:
            oriented = ImageOps.exif_transpose(source)
            # Flatten transparency onto white, then create new pixels: no EXIF, GPS,
            # ICC profile, comments, filenames or original encoded bytes are retained.
            rgba = oriented.convert('RGBA')
            background = Image.new('RGB', rgba.size, 'white')
            background.paste(rgba, mask=rgba.getchannel('A'))
            square = ImageOps.fit(background, (256, 256), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            square.save(output, format='JPEG', quality=88, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, binascii.Error, Image.DecompressionBombError) as exc:
        raise ValueError('图片无法读取或已损坏，请换一张 JPG、PNG 或 WebP 图片。') from exc
