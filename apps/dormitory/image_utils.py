import io
import os
from PIL import Image, ImageOps
from django.core.files.base import ContentFile


def compress_image(image_file, max_size_bytes=1024 * 1024, max_dimension=1920):
    """
    Compress and optimize an uploaded image:
    1. Fix EXIF orientation (crucial for smartphone camera captures).
    2. Convert RGBA/P/palette modes to RGB for clean JPEG compression.
    3. Resize if max(width, height) > max_dimension while preserving aspect ratio.
    4. Iteratively save with JPEG quality optimization ensuring final file size <= max_size_bytes (1MB).
    """
    if not image_file:
        return image_file

    try:
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        img = Image.open(image_file)

        # Transpose according to EXIF orientation (prevents upside down / rotated mobile photos)
        img = ImageOps.exif_transpose(img)

        # Convert to RGB mode if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize if image exceeds maximum allowed dimension
        orig_w, orig_h = img.size
        if max(orig_w, orig_h) > max_dimension:
            scale = max_dimension / max(orig_w, orig_h)
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Iteratively compress with quality until file size is under max_size_bytes (1MB)
        quality = 85
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)

        while buffer.tell() > max_size_bytes and quality > 25:
            quality -= 10
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)

        buffer.seek(0)
        orig_name = getattr(image_file, 'name', 'doc_image.jpg')
        base_name, _ = os.path.splitext(os.path.basename(orig_name))
        new_name = f"{base_name}.jpg"
        return ContentFile(buffer.getvalue(), name=new_name)

    except Exception:
        # Fallback to original file if Pillow processing fails
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        return image_file
