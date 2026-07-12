#!/usr/bin/env python3
"""
PDF 压缩脚本，支持多档位压缩配置。

用法:
    python pdf_compress.py input.pdf -o output.pdf -l medium
    python pdf_compress.py input.pdf -l high               # 不指定 -o，输出到 input__compressed.pdf
    python pdf_compress.py pdf_folder -l medium             # 压缩文件夹中所有 PDF
    python pdf_compress.py input.pdf -c custom.json         # 使用自定义配置
    python pdf_compress.py --list-presets                   # 列出所有档位

压缩档位:
    low    - 轻量压缩，保持最高质量
    medium - 平衡压缩 (默认)
    high   - 强力压缩，文件最小
"""

import argparse
import json
import sys
import zlib
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# 压缩配置定义
# ──────────────────────────────────────────────

class ImageCompression(Enum):
    """图片压缩算法"""
    JPEG = "jpeg"
    FLATE = "flate"       # 无损
    LOSSLESS = "lossless"
    AUTO = "auto"


@dataclass
class CompressionConfig:
    """单个压缩档位的配置"""
    name: str
    description: str

    # JPEG 图片质量 (0-100)，越低压缩越狠
    jpeg_quality: int = 85

    # 彩色/灰度图片 DPI 降采样阈值与目标
    downsample_color: bool = True
    color_dpi_threshold: int = 225       # 超过此 DPI 才降采样
    color_dpi_target: int = 150          # 降采样目标 DPI

    # 灰度图降采样
    downsample_gray: bool = True
    gray_dpi_threshold: int = 225
    gray_dpi_target: int = 150

    # 单色(黑白)图降采样
    downsample_mono: bool = True
    mono_dpi_threshold: int = 600
    mono_dpi_target: int = 300

    # 图片压缩算法 (默认 AUTO: 对每张图同时尝试 JPEG 与 Flate，取较小者)
    color_image_compression: ImageCompression = ImageCompression.AUTO
    gray_image_compression: ImageCompression = ImageCompression.AUTO
    mono_image_compression: ImageCompression = ImageCompression.FLATE

    # 移除对象中的未引用资源
    remove_unused_objects: bool = True

    # 线性化(优化网页浏览)
    linearize: bool = False

    # 使用 pikepdf 的 recompress_flate (对内部流再压缩)
    recompress_flate: bool = True

    # 移除元数据中冗余项
    clean_metadata: bool = True


# ──────────────────────────────────────────────
# 内置压缩档位
# ──────────────────────────────────────────────

PRESETS: dict[str, CompressionConfig] = {
    "low": CompressionConfig(
        name="low",
        description="轻量压缩，保持最高画质",
        jpeg_quality=90,
        downsample_color=True,
        color_dpi_threshold=300,
        color_dpi_target=200,
        downsample_gray=True,
        gray_dpi_threshold=300,
        gray_dpi_target=200,
        downsample_mono=True,
        mono_dpi_threshold=600,
        mono_dpi_target=400,
        recompress_flate=True,
    ),
    "medium": CompressionConfig(
        name="medium",
        description="平衡压缩 (默认)",
        jpeg_quality=65,
        downsample_color=True,
        color_dpi_threshold=225,
        color_dpi_target=150,
        downsample_gray=True,
        gray_dpi_threshold=225,
        gray_dpi_target=150,
        downsample_mono=True,
        mono_dpi_threshold=450,
        mono_dpi_target=300,
        recompress_flate=True,
    ),
    "high": CompressionConfig(
        name="high",
        description="强力压缩，最小文件体积",
        jpeg_quality=30,
        downsample_color=True,
        color_dpi_threshold=150,
        color_dpi_target=100,
        downsample_gray=True,
        gray_dpi_threshold=150,
        gray_dpi_target=100,
        downsample_mono=True,
        mono_dpi_threshold=300,
        mono_dpi_target=200,
        recompress_flate=True,
    ),
}


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _fmt_size(size: int) -> str:
    """把字节数格式化为易读字符串。"""
    size = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _page_dpi(page, img_w: int, img_h: int) -> Optional[float]:
    """估算图片在页面上的有效 DPI（假设图片填满页面，保守取较小值）。

    PDF 单位为点 (1/72 英寸)，用 mediabox 尺寸推算图片显示尺寸。
    无法获取时返回 None。
    """
    try:
        mb = page.mediabox
        page_w = float(mb[2]) - float(mb[0])
        page_h = float(mb[3]) - float(mb[1])
    except Exception:
        return None
    if page_w <= 0 or page_h <= 0:
        return None
    dpi_w = img_w * 72.0 / page_w
    dpi_h = img_h * 72.0 / page_h
    return min(dpi_w, dpi_h)


# ──────────────────────────────────────────────
# 压缩引擎
# ──────────────────────────────────────────────

def compress_with_pikepdf(
    input_path: Path,
    output_path: Path,
    config: CompressionConfig,
) -> tuple[int, int]:
    """使用 pikepdf (qpdf) 压缩 PDF，返回 (原始大小, 压缩后大小)。"""
    import pikepdf
    from PIL import Image

    original_size = input_path.stat().st_size

    with pikepdf.Pdf.open(input_path) as pdf:
        # 同一图片对象可能被多页引用，按 objgen 去重避免重复压缩
        processed: set[tuple[int, int]] = set()
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            _recompress_page_images(page, config, processed, i + 1, page_count)

        # 清理元数据
        if config.clean_metadata:
            try:
                pdf.docinfo = pikepdf.Dictionary()
            except Exception:
                pass

        # 组装 save 参数
        save_kwargs: dict = {"compress_streams": True}
        if config.recompress_flate:
            save_kwargs["recompress_flate"] = True
        if config.linearize:
            save_kwargs["linearize"] = True
        if config.remove_unused_objects:
            save_kwargs["object_stream_mode"] = pikepdf.ObjectStreamMode.generate

        pdf.save(output_path, **save_kwargs)

    compressed_size = output_path.stat().st_size
    return original_size, compressed_size


def _recompress_page_images(
    page,
    config: CompressionConfig,
    processed: set[tuple[int, int]],
    page_num: int,
    total: int,
):
    """重新压缩页面中的所有图片。"""
    import pikepdf
    from PIL import Image
    from pikepdf import PdfImage

    try:
        image_names = page.get_images()
    except Exception:
        return
    if not image_names:
        return

    try:
        xobjects = page.Resources.XObject
    except Exception:
        return

    for name in image_names:
        try:
            raw_image = xobjects[name]
            # 多页共享图片去重
            objgen = raw_image.objgen
            if objgen in processed:
                continue
            processed.add(objgen)

            # 记录原始流字节长度，用于"压缩后变大就保留原图"
            try:
                original_stream_len = len(raw_image.read_raw_bytes())
            except Exception:
                original_stream_len = 0

            pdf_image = PdfImage(raw_image)
            pil_image = pdf_image.as_pil_image()
            original_mode = pil_image.mode

            # 按原图模式分类，决定走彩色/灰度/单色配置
            category = _classify_mode(original_mode)

            # 计算实际 DPI，决定是否降采样
            cur_dpi = _page_dpi(page, pil_image.width, pil_image.height)
            pil_image = _maybe_downsample(pil_image, category, cur_dpi, config)

            # 编码并写回
            data, filt, bpc, colorspace = _encode_image(pil_image, category, config)

            # 若新数据比原始流还大，保留原图（避免对线稿/已优化图造成反效果）
            if original_stream_len > 0 and len(data) >= original_stream_len:
                continue

            raw_image.write(data)
            raw_image.Filter = pikepdf.Array(filt)
            raw_image.Width = pikepdf.Integer(pil_image.width)
            raw_image.Height = pikepdf.Integer(pil_image.height)
            raw_image.BitsPerComponent = pikepdf.Integer(bpc)
            raw_image.ColorSpace = colorspace
            # 重编码后丢失软掩膜，移除引用避免不一致
            if "SMask" in raw_image:
                del raw_image.SMask
        except Exception as e:
            print(f"    [警告] 第 {page_num}/{total} 页 图片 {name} 压缩失败: {e}",
                  file=sys.stderr)


def _classify_mode(mode: str) -> str:
    """把 PIL 模式归类为 color / gray / mono。"""
    if mode == "1":
        return "mono"
    if mode in ("L", "LA", "I;16"):
        return "gray"
    return "color"


def _maybe_downsample(pil_image, category: str, cur_dpi, config: CompressionConfig):
    """按配置对图片降采样，返回 (可能 resize 后的) PIL Image。"""
    from PIL import Image

    if cur_dpi is None:
        return pil_image

    if category == "color" and config.downsample_color:
        threshold, target = config.color_dpi_threshold, config.color_dpi_target
    elif category == "gray" and config.downsample_gray:
        threshold, target = config.gray_dpi_threshold, config.gray_dpi_target
    elif category == "mono" and config.downsample_mono:
        threshold, target = config.mono_dpi_threshold, config.mono_dpi_target
    else:
        return pil_image

    if cur_dpi <= threshold or target <= 0:
        return pil_image

    scale = target / cur_dpi
    if scale >= 1.0:
        return pil_image
    new_w = max(1, int(round(pil_image.width * scale)))
    new_h = max(1, int(round(pil_image.height * scale)))
    return pil_image.resize((new_w, new_h), Image.LANCZOS)


def _encode_image(pil_image, category: str, config: CompressionConfig):
    """根据类别和配置压缩图片。

    返回 (data, filter_list, bits_per_component, colorspace)。

    对于彩色/灰度图，若配置为 AUTO 会同时尝试 JPEG 与 Flate 取较小者，
    避免对图表/线稿这类不适合 JPEG 的图强行重编码导致体积反增。
    """
    import pikepdf
    from PIL import Image

    def _jpeg(img, quality: int) -> bytes:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality,
                 optimize=True, progressive=True)
        return buf.getvalue()

    def _flate(img) -> bytes:
        return zlib.compress(img.tobytes())

    def _alg(cat: str) -> ImageCompression:
        return {
            "color": config.color_image_compression,
            "gray": config.gray_image_compression,
            "mono": config.mono_image_compression,
        }[cat]

    if category == "mono":
        # 黑白: 用 Flate (zlib) 压缩 1-bit 像素数据
        if pil_image.mode != "1":
            pil_image = pil_image.convert("1")
        return _flate(pil_image), [pikepdf.Name.FlateDecode], 1, pikepdf.Name.DeviceGray

    if category == "gray":
        if pil_image.mode != "L":
            pil_image = pil_image.convert("L")
        alg = _alg("gray")
        candidates = []
        if alg in (ImageCompression.JPEG, ImageCompression.AUTO):
            candidates.append((_jpeg(pil_image, config.jpeg_quality),
                               [pikepdf.Name.DCTDecode], 8, pikepdf.Name.DeviceGray))
        if alg in (ImageCompression.FLATE, ImageCompression.LOSSLESS, ImageCompression.AUTO):
            candidates.append((_flate(pil_image),
                               [pikepdf.Name.FlateDecode], 8, pikepdf.Name.DeviceGray))
        if not candidates:
            candidates.append((_flate(pil_image),
                               [pikepdf.Name.FlateDecode], 8, pikepdf.Name.DeviceGray))
        return min(candidates, key=lambda c: len(c[0]))

    # color
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    alg = _alg("color")
    candidates = []
    if alg in (ImageCompression.JPEG, ImageCompression.AUTO):
        candidates.append((_jpeg(pil_image, config.jpeg_quality),
                           [pikepdf.Name.DCTDecode], 8, pikepdf.Name.DeviceRGB))
    if alg in (ImageCompression.FLATE, ImageCompression.LOSSLESS, ImageCompression.AUTO):
        candidates.append((_flate(pil_image),
                           [pikepdf.Name.FlateDecode], 8, pikepdf.Name.DeviceRGB))
    if not candidates:
        candidates.append((_flate(pil_image),
                           [pikepdf.Name.FlateDecode], 8, pikepdf.Name.DeviceRGB))
    return min(candidates, key=lambda c: len(c[0]))


def compress_with_pypdf(
    input_path: Path,
    output_path: Path,
    config: CompressionConfig,
) -> tuple[int, int]:
    """使用 pypdf 压缩 PDF (纯 Python，功能有限)。"""
    from pypdf import PdfReader, PdfWriter

    original_size = input_path.stat().st_size

    reader = PdfReader(input_path)
    writer = PdfWriter()
    # pypdf 6.x: page.compress_content_streams 要求 page 已属于 writer，
    # 因此用 append 把所有页加入 writer 后再操作 writer.pages
    writer.append(reader)

    for page in writer.pages:
        try:
            page.compress_content_streams()
        except Exception:
            pass

    # 合并重复对象（字体/图片），能进一步减小体积
    # pypdf 7.0 将重命名参数，这里同时兼容新旧版本
    try:
        try:
            writer.compress_identical_objects(
                remove_duplicates=True, remove_unreferenced=True
            )
        except TypeError:
            writer.compress_identical_objects(
                remove_identicals=True, remove_orphans=True
            )
    except Exception:
        pass

    if config.clean_metadata:
        try:
            writer.add_metadata({})
        except Exception:
            pass

    with open(output_path, "wb") as f:
        writer.write(f)

    compressed_size = output_path.stat().st_size
    return original_size, compressed_size


def compress_with_ghostscript(
    input_path: Path,
    output_path: Path,
    config: CompressionConfig,
) -> tuple[int, int]:
    """使用 Ghostscript 压缩 PDF (外部依赖，效果最好)。"""
    import subprocess

    original_size = input_path.stat().st_size

    quality_map = {
        "low": "/prepress",
        "medium": "/ebook",
        "high": "/screen",
    }
    gs_quality = quality_map.get(config.name, "/ebook")

    # Ghostscript 的 DownsampleThreshold 是比例值（>1.0 才会触发降采样）
    def _threshold_ratio(threshold: int, target: int) -> str:
        if target <= 0:
            return "1.5"
        return f"{threshold / target:.2f}"

    args = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={gs_quality}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-dJPEGQ={config.jpeg_quality}",
        # 彩色图
        "-dDownsampleColorImages=true",
        "-dAutoFilterColorImages=false",
        "-dColorImageFilter=/DCTEncode",
        f"-dColorImageResolution={config.color_dpi_target}",
        f"-dColorImageDownsampleThreshold={_threshold_ratio(config.color_dpi_threshold, config.color_dpi_target)}",
        "-dColorImageDownsampleType=/Bicubic",
        # 灰度图
        "-dDownsampleGrayImages=true",
        "-dAutoFilterGrayImages=false",
        "-dGrayImageFilter=/DCTEncode",
        f"-dGrayImageResolution={config.gray_dpi_target}",
        f"-dGrayImageDownsampleThreshold={_threshold_ratio(config.gray_dpi_threshold, config.gray_dpi_target)}",
        "-dGrayImageDownsampleType=/Bicubic",
        # 单色图
        "-dDownsampleMonoImages=true",
        f"-dMonoImageResolution={config.mono_dpi_target}",
        f"-dMonoImageDownsampleThreshold={_threshold_ratio(config.mono_dpi_threshold, config.mono_dpi_target)}",
        "-dMonoImageDownsampleType=/Bicubic",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=true",
        f"-sOutputFile={output_path}",
        str(input_path),
    ]

    subprocess.run(args, check=True, capture_output=True)

    compressed_size = output_path.stat().st_size
    return original_size, compressed_size


# ──────────────────────────────────────────────
# 批量文件夹压缩
# ──────────────────────────────────────────────

def compress_folder(
    folder_path: Path,
    config: CompressionConfig,
    *,
    engine: str = "auto",
) -> Path:
    """
    压缩文件夹中所有顶层 PDF 文件。

    Args:
        folder_path: 输入文件夹路径
        config:      压缩配置
        engine:      引擎选择

    Returns:
        输出文件夹路径
    """
    if not folder_path.is_dir():
        raise NotADirectoryError(f"不是文件夹: {folder_path}")

    pdf_files = sorted(
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    )

    if not pdf_files:
        raise FileNotFoundError(f"文件夹 {folder_path} 中没有 PDF 文件")

    output_dir = folder_path.parent / (folder_path.name + "__compressed")
    output_dir.mkdir(exist_ok=True)

    print(f"\n文件夹压缩模式:")
    print(f"  源文件夹:   {folder_path}")
    print(f"  输出文件夹: {output_dir}")
    print(f"  找到 {len(pdf_files)} 个 PDF 文件")
    print(f"  压缩档位:   {config.name} ({config.description})")
    print(f"{'─'*50}")

    total_original = 0
    total_compressed = 0
    success = 0
    failed = []

    for pdf_file in pdf_files:
        output_path = output_dir / (pdf_file.stem + "__compressed" + pdf_file.suffix)
        try:
            original, compressed = _compress_single_file(
                pdf_file, output_path, config, engine
            )
            total_original += original
            total_compressed += compressed
            success += 1

            ratio = (1 - compressed / original) * 100 if original > 0 else 0
            print(f"  [{success}/{len(pdf_files)}] {pdf_file.name}")
            print(f"         {_fmt_size(original)} -> {_fmt_size(compressed)}  ({ratio:.1f}%)")
        except Exception as e:
            failed.append((pdf_file.name, str(e)))
            print(f"  [失败] {pdf_file.name}: {e}")

    print(f"\n{'─'*50}")
    print(f"  汇总: 成功 {success}/{len(pdf_files)}")

    if total_original > 0:
        total_ratio = (1 - total_compressed / total_original) * 100
        print(f"  总计: {_fmt_size(total_original)} -> {_fmt_size(total_compressed)}  ({total_ratio:.1f}%)")

    if failed:
        print(f"  失败文件:")
        for name, err in failed:
            print(f"    - {name}: {err}")

    print(f"  输出文件夹: {output_dir}")
    print(f"{'─'*50}\n")

    return output_dir


def _compress_single_file(
    input_path: Path,
    output_path: Path,
    config: CompressionConfig,
    engine: str,
) -> tuple[int, int]:
    """压缩单个 PDF 文件，返回 (原始大小, 压缩后大小)。"""
    return _dispatch_engine(input_path, output_path, config, engine)


def _dispatch_engine(
    input_path: Path,
    output_path: Path,
    config: CompressionConfig,
    engine: str,
) -> tuple[int, int]:
    """根据 engine 选择并调用具体压缩实现。"""
    chosen_engine = _select_engine(engine)

    if chosen_engine == "ghostscript":
        return compress_with_ghostscript(input_path, output_path, config)
    if chosen_engine == "pikepdf":
        return compress_with_pikepdf(input_path, output_path, config)
    return compress_with_pypdf(input_path, output_path, config)


# ──────────────────────────────────────────────
# 主压缩入口
# ──────────────────────────────────────────────

def compress_pdf(
    input_path: Path,
    output_path: Optional[Path],
    config: CompressionConfig,
    *,
    engine: str = "auto",
) -> Path:
    """
    压缩 PDF 文件。

    Args:
        input_path:  输入 PDF 路径
        output_path: 输出路径，None 则在原文件名后加 __compressed
        config:      压缩配置
        engine:      引擎选择: "pikepdf", "pypdf", "ghostscript", "auto"

    Returns:
        输出文件路径
    """
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    if input_path.suffix.lower() != ".pdf":
        raise ValueError(f"不是 PDF 文件: {input_path}")

    if output_path is None:
        output_path = input_path.parent / (input_path.stem + "__compressed" + input_path.suffix)

    chosen_engine = _select_engine(engine)
    original, compressed = _dispatch_engine(input_path, output_path, config, engine)

    _print_result(original, compressed, output_path, config, chosen_engine)
    return output_path


def _select_engine(preferred: str) -> str:
    """自动选择可用的压缩引擎。"""
    if preferred != "auto":
        _check_engine_available(preferred)
        return preferred

    for engine in ("ghostscript", "pikepdf", "pypdf"):
        if _engine_available(engine):
            return engine

    raise RuntimeError("没有可用的 PDF 压缩引擎，请安装 pikepdf 或 pypdf")


def _engine_available(engine: str) -> bool:
    try:
        _check_engine_available(engine)
        return True
    except (RuntimeError, ValueError):
        return False


def _check_engine_available(engine: str):
    if engine == "pikepdf":
        try:
            import pikepdf  # noqa: F401
        except ImportError:
            raise RuntimeError("pikepdf 未安装，请执行: pip install pikepdf Pillow")
    elif engine == "pypdf":
        try:
            import pypdf  # noqa: F401
        except ImportError:
            raise RuntimeError("pypdf 未安装，请执行: pip install pypdf")
    elif engine == "ghostscript":
        import subprocess
        try:
            # 注意: 传 list 时不应使用 shell=True，否则在 Linux 上行为不可预期
            subprocess.run(["gs", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
            raise RuntimeError(
                "Ghostscript 未安装或不在 PATH 中。"
                "请从 https://ghostscript.com/releases/gsdnld.html 下载安装。"
            ) from e
    else:
        raise ValueError(f"未知引擎: {engine}")


def _print_result(
    original: int,
    compressed: int,
    output_path: Path,
    config: CompressionConfig,
    engine: str,
):
    """打印压缩结果。"""
    ratio = (1 - compressed / original) * 100 if original > 0 else 0

    print(f"\n{'─'*50}")
    print(f"  压缩完成!")
    print(f"  原始大小:  {_fmt_size(original):>10}")
    print(f"  压缩后:    {_fmt_size(compressed):>10}")
    print(f"  压缩率:    {ratio:>9.1f}%")
    print(f"  使用引擎:  {engine}")
    print(f"  压缩档位:  {config.name} ({config.description})")
    print(f"  输出文件:  {output_path}")
    print(f"{'─'*50}\n")


# ──────────────────────────────────────────────
# 自定义配置加载
# ──────────────────────────────────────────────

def load_config_from_file(config_path: Path) -> CompressionConfig:
    """从 JSON 文件加载自定义压缩配置。

    JSON 示例:
    {
        "name": "custom",
        "description": "自定义配置",
        "jpeg_quality": 50,
        "color_dpi_target": 120,
        "gray_dpi_target": 120,
        "mono_dpi_target": 250
    }
    """
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for field_name in (
        "color_image_compression",
        "gray_image_compression",
        "mono_image_compression",
    ):
        if field_name in data and isinstance(data[field_name], str):
            data[field_name] = ImageCompression(data[field_name])

    config = CompressionConfig(
        name="custom",
        description="自定义配置",
    )
    for key, value in data.items():
        if hasattr(config, key):
            setattr(config, key, value)

    return config


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PDF 压缩工具 - 支持多档位压缩配置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
内置压缩档位:
  low      轻量压缩，保持最高画质
  medium   平衡压缩 (默认)
  high     强力压缩，最小文件体积

使用示例:
  python pdf_compress.py input.pdf -l medium
  python pdf_compress.py input.pdf -o output.pdf -l high
  python pdf_compress.py input.pdf -l low -e ghostscript
  python pdf_compress.py input.pdf -c my_config.json
  python pdf_compress.py pdf_folder -l medium        # 压缩文件夹中所有 PDF
  python pdf_compress.py --list-presets
        """,
    )

    parser.add_argument(
        "input", nargs="?", help="输入 PDF 文件或文件夹路径"
    )
    parser.add_argument(
        "-o", "--output", default=None, help="输出 PDF 文件路径 (默认在原文件名后加 __compressed)"
    )
    parser.add_argument(
        "-l", "--level",
        choices=["low", "medium", "high"],
        default="medium",
        help="压缩档位 (默认: medium)",
    )
    parser.add_argument(
        "-e", "--engine",
        choices=["auto", "pikepdf", "pypdf", "ghostscript"],
        default="auto",
        help="压缩引擎 (默认: auto，自动选择可用引擎)",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=None,
        help="自定义 JSON 配置文件路径",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="列出所有内置压缩档位详情",
    )

    args = parser.parse_args()

    if args.list_presets:
        _list_presets()
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    input_path = Path(args.input)

    if args.config:
        config = load_config_from_file(args.config)
    else:
        config = PRESETS[args.level]

    try:
        if input_path.is_dir():
            if args.output:
                print("[错误] 文件夹模式下不能使用 -o/--output 参数", file=sys.stderr)
                sys.exit(1)
            compress_folder(input_path, config, engine=args.engine)
        else:
            output_path = Path(args.output) if args.output else None
            compress_pdf(input_path, output_path, config, engine=args.engine)
    except Exception as e:
        print(f"\n[错误] {e}", file=sys.stderr)
        sys.exit(1)


def _list_presets():
    """打印所有压缩档位详情。"""
    print("\n内置压缩档位:\n")
    for key, cfg in PRESETS.items():
        print(f"  [{key}]  {cfg.description}")
        print(f"      JPEG 质量:        {cfg.jpeg_quality}")
        print(f"      彩色图目标 DPI:    {cfg.color_dpi_target}")
        print(f"      灰度图目标 DPI:    {cfg.gray_dpi_target}")
        print(f"      单色图目标 DPI:    {cfg.mono_dpi_target}")
        print(f"      Flate 再压缩:      {cfg.recompress_flate}")
        print()


if __name__ == "__main__":
    main()
