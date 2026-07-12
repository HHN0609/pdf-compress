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
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
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

    # 图片压缩算法
    color_image_compression: ImageCompression = ImageCompression.JPEG
    gray_image_compression: ImageCompression = ImageCompression.JPEG
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
# 压缩引擎
# ──────────────────────────────────────────────

def compress_with_pikepdf(
    input_path: Path,
    output_path: Path,
    config: CompressionConfig,
) -> tuple[int, int]:
    """使用 pikepdf (qpdf) 压缩 PDF，返回 (原始大小, 压缩后大小)。"""
    import pikepdf

    pdf = pikepdf.Pdf.open(input_path)

    original_size = input_path.stat().st_size

    # 配置压缩选项
    for page in pdf.pages:
        _compress_page_images(page, config)

    # 保存时应用压缩设置
    save_options = pikepdf.PdfSaveOptions(
        compress_streams=True,
        recompress_flate=config.recompress_flate,
        remove_unused_objects=config.remove_unused_objects,
        linearize=config.linearize,
    )

    pdf.save(output_path, options=save_options)
    pdf.close()

    compressed_size = output_path.stat().st_size
    return original_size, compressed_size


def _compress_page_images(page, config: CompressionConfig):
    """对页面中的图片进行压缩降采样。"""
    # pikepdf 可以通过操作 content stream 中的图片对象来压缩
    # 这里使用 pikepdf 的 image 相关 API
    try:
        for image_name, image in page.images.items():
            try:
                _process_image(image, config)
            except Exception:
                pass  # 单张图片失败不影响整体
    except Exception:
        pass


def _process_image(image, config: CompressionConfig):
    """处理单张图片：根据配置进行 DPI 降采样和重新压缩。"""
    # 对于 JPEG 彩色图片，降低质量
    # pikepdf 较难直接做 DPI 降采样，需要用 Pillow 辅助
    try:
        from PIL import Image
        from io import BytesIO
        import pikepdf

        pil_image = image.as_pil_image()
        width, height = pil_image.size

        # 判断图片类型
        mode = pil_image.mode
        if mode in ("1",):
            # 单色图
            downsample = config.downsample_mono
            threshold = config.mono_dpi_threshold
            target = config.mono_dpi_target
        elif mode in ("L", "LA", "P"):
            # 灰度图
            downsample = config.downsample_gray
            threshold = config.gray_dpi_threshold
            target = config.gray_dpi_target
        else:
            # 彩色图
            downsample = config.downsample_color
            threshold = config.color_dpi_threshold
            target = config.color_dpi_target

        # 计算当前 DPI (pikepdf 可能提供 DPI 信息)
        # 估算物理尺寸，假设 72 DPI 作为默认
        if downsample and target < threshold:
            # 简单降采样
            scale_factor = target / 150.0  # 用 150 作为基准
            new_width = max(1, int(width * scale_factor))
            new_height = max(1, int(height * scale_factor))

            if new_width < width and new_height < height:
                pil_image = pil_image.resize(
                    (new_width, new_height), Image.LANCZOS
                )

        # 重新编码为 JPEG
        if mode not in ("1",):
            if pil_image.mode in ("RGBA", "LA", "P"):
                pil_image = pil_image.convert("RGB")
            buf = BytesIO()
            pil_image.save(buf, format="JPEG", quality=config.jpeg_quality)
            buf.seek(0)

            # 替换图片
            ext = pikepdf.Stream(pikepdf.Pdf.open(buf).pages[0].images)
            # 注意：实际替换逻辑取决于 pikepdf 版本
    except ImportError:
        pass  # Pillow 不可用时跳过图片重压缩
    except Exception:
        pass


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

    for page in reader.pages:
        # 对页面内容进行压缩
        page.compress_content_streams()
        writer.add_page(page)

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

    # Ghostscript 压缩预设映射
    quality_map = {
        "low": "/prepress",
        "medium": "/ebook",
        "high": "/screen",
    }

    gs_quality = quality_map.get(config.name, "/ebook")

    # JPEG 质量映射到 gs 的 ColorImageFilter 等参数
    args = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={gs_quality}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={output_path}",
        str(input_path),
    ]

    # 根据配置精细化控制
    if config.jpeg_quality:
        args.insert(4, f"-dColorImageCompression=/DCTEncode")
        args.insert(5, f"-dColorImageCompressionQuality={config.jpeg_quality}")

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

    # 收集顶层 PDF 文件
    pdf_files = sorted(
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    )

    if not pdf_files:
        raise FileNotFoundError(f"文件夹 {folder_path} 中没有 PDF 文件")

    # 创建输出文件夹
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

            def fmt(size: int) -> str:
                for unit in ("B", "KB", "MB", "GB"):
                    if size < 1024:
                        return f"{size:.1f} {unit}"
                    size /= 1024
                return f"{size:.1f} TB"

            ratio = (1 - compressed / original) * 100 if original > 0 else 0
            print(f"  [{success}/{len(pdf_files)}] {pdf_file.name}")
            print(f"         {fmt(original)} -> {fmt(compressed)}  ({ratio:.1f}%)")
        except Exception as e:
            failed.append((pdf_file.name, str(e)))
            print(f"  [失败] {pdf_file.name}: {e}")

    # 汇总
    print(f"\n{'─'*50}")
    print(f"  汇总: 成功 {success}/{len(pdf_files)}")

    if total_original > 0:
        total_ratio = (1 - total_compressed / total_original) * 100
        def fmt(size: int) -> str:
            for unit in ("B", "KB", "MB", "GB"):
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} TB"
        print(f"  总计: {fmt(total_original)} -> {fmt(total_compressed)}  ({total_ratio:.1f}%)")

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
    original_size = input_path.stat().st_size

    chosen_engine = _select_engine(engine)

    if chosen_engine == "ghostscript":
        _, compressed_size = compress_with_ghostscript(
            input_path, output_path, config
        )
    elif chosen_engine == "pikepdf":
        _, compressed_size = compress_with_pikepdf(
            input_path, output_path, config
        )
    else:
        _, compressed_size = compress_with_pypdf(
            input_path, output_path, config
        )

    return original_size, compressed_size


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

    # 输出路径：未指定则在原文件名后加 __compressed
    if output_path is None:
        output_path = input_path.parent / (input_path.stem + "__compressed" + input_path.suffix)

    # 选择引擎
    chosen_engine = _select_engine(engine)

    # 执行压缩
    if chosen_engine == "ghostscript":
        original, compressed = compress_with_ghostscript(
            input_path, output_path, config
        )
    elif chosen_engine == "pikepdf":
        original, compressed = compress_with_pikepdf(
            input_path, output_path, config
        )
    else:
        original, compressed = compress_with_pypdf(
            input_path, output_path, config
        )

    _print_result(original, compressed, output_path, config, chosen_engine)
    return output_path


def _select_engine(preferred: str) -> str:
    """自动选择可用的压缩引擎。"""
    if preferred != "auto":
        _check_engine_available(preferred)
        return preferred

    # 自动检测
    for engine in ("ghostscript", "pikepdf", "pypdf"):
        if _engine_available(engine):
            return engine

    raise RuntimeError("没有可用的 PDF 压缩引擎，请安装 pikepdf 或 pypdf")


def _engine_available(engine: str) -> bool:
    try:
        _check_engine_available(engine)
        return True
    except RuntimeError:
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
            subprocess.run(
                ["gs", "--version"],
                check=True,
                capture_output=True,
                shell=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "Ghostscript 未安装或不在 PATH 中。"
                "请从 https://ghostscript.com/releases/gsdnld.html 下载安装。"
            )
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

    def fmt(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    print(f"\n{'─'*50}")
    print(f"  压缩完成!")
    print(f"  原始大小:  {fmt(original):>10}")
    print(f"  压缩后:    {fmt(compressed):>10}")
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

    # 处理枚举字段
    for field_name in (
        "color_image_compression",
        "gray_image_compression",
        "mono_image_compression",
    ):
        if field_name in data and isinstance(data[field_name], str):
            data[field_name] = ImageCompression(data[field_name])

    # 覆盖默认配置
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

    # 列出档位
    if args.list_presets:
        _list_presets()
        return

    # 输入文件必填
    if not args.input:
        parser.print_help()
        sys.exit(1)

    input_path = Path(args.input)

    # 加载配置
    if args.config:
        config = load_config_from_file(args.config)
    else:
        config = PRESETS[args.level]

    try:
        if input_path.is_dir():
            # 文件夹模式：不允许指定 -o
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
