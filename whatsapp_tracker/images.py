from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError


ALLOWED_PHOTO_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class PhotoValidationError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class NormalizedPhoto:
    content: bytes
    digest: str
    width: int
    height: int


def normalize_photo(
    raw: bytes,
    *,
    max_pixels: int,
    max_dimension: int,
    max_output_bytes: int,
) -> NormalizedPhoto:
    if not raw:
        raise PhotoValidationError("invalid_photo", "ملف الصورة فارغ أو غير صالح.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            _verify_photo(raw, max_pixels)
            normalized = _decode_photo(raw, max_pixels, max_dimension)
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        raise PhotoValidationError(
            "invalid_photo",
            "تعذّر قراءة الصورة. استخدم صورة JPEG أو PNG أو WebP صالحة.",
        ) from error

    width, height = normalized.size
    try:
        output = io.BytesIO()
        normalized.save(output, format="PNG", optimize=True)
        content = output.getvalue()
    except (OSError, ValueError) as error:
        raise PhotoValidationError(
            "invalid_photo",
            "تعذّرت معالجة الصورة. اختر صورة أخرى.",
        ) from error
    finally:
        normalized.close()
    if len(content) > max_output_bytes:
        raise PhotoValidationError(
            "photo_output_too_large",
            "الصورة كبيرة جداً بعد المعالجة. اختر صورة أبسط أو أصغر.",
        )

    return NormalizedPhoto(
        content=content,
        digest=hashlib.sha256(content).hexdigest(),
        width=width,
        height=height,
    )


def _verify_photo(raw: bytes, max_pixels: int) -> None:
    with Image.open(io.BytesIO(raw), formats=tuple(ALLOWED_PHOTO_FORMATS)) as image:
        _validate_image_metadata(image, max_pixels)
        image.verify()


def _decode_photo(raw: bytes, max_pixels: int, max_dimension: int) -> Image.Image:
    with Image.open(io.BytesIO(raw), formats=tuple(ALLOWED_PHOTO_FORMATS)) as image:
        _validate_image_metadata(image, max_pixels)
        image.load()
        oriented = ImageOps.exif_transpose(image)
        oriented.thumbnail(
            (max_dimension, max_dimension),
            resample=Image.Resampling.LANCZOS,
            reducing_gap=3.0,
        )
        has_transparency = "A" in oriented.getbands() or "transparency" in oriented.info
        output_mode = "RGBA" if has_transparency else "RGB"
        return oriented.convert(output_mode)


def _validate_image_metadata(image: Image.Image, max_pixels: int) -> None:
    if image.format not in ALLOWED_PHOTO_FORMATS:
        raise PhotoValidationError(
            "invalid_photo_type",
            "يُسمح بصور JPEG أو PNG أو WebP فقط.",
        )
    if getattr(image, "is_animated", False):
        raise PhotoValidationError(
            "animated_photo",
            "الصور المتحركة غير مدعومة. اختر صورة ثابتة.",
        )
    if image.width < 1 or image.height < 1 or image.width * image.height > max_pixels:
        raise PhotoValidationError(
            "photo_dimensions_too_large",
            "أبعاد الصورة كبيرة جداً. الحد الأقصى هو 20 مليون بكسل.",
        )
