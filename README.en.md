# PDF Compression Tool

A Python-based PDF compression script with multi-level compression presets, supporting both single-file and batch folder processing.

## Features

- Single-file and batch folder compression
- Three compression levels (low/medium/high)
- Multi-engine support (pikepdf/pypdf/ghostscript)
- Custom compression configurations
- Non-destructive: source files are never overwritten, output filenames get a `__compressed` suffix
- Smart downsampling based on actual display DPI (derived from the page mediabox)
- Mode-aware image handling: color / grayscale / monochrome images use separate strategies
- AUTO algorithm: tries both JPEG and Flate for color/grayscale images and picks the smaller one, preventing charts from being bloated by JPEG
- Multi-page shared image deduplication, avoiding repeated compression of the same object
- Safety guard: if re-encoding produces a larger stream than the original, the original image is kept, preventing size regressions on line art or already-optimized images
- JPEG encoding uses progressive + optimize to further reduce size

## Installation

```bash
# Create a virtual environment (recommended to avoid dependency conflicts)
python -m venv venv

# Activate the virtual environment
venv\Scripts\activate.bat    # Windows PowerShell (use .bat if blocked)
source venv/bin/activate     # Mac / Linux

# Install dependencies
pip install -r requirements.txt
```

You can also run `pip install -r requirements.txt` directly without a virtual environment.

For best compression results, additionally install [Ghostscript](https://ghostscript.com/releases/gsdnld.html) and add it to your system PATH.

## Quick Start

```bash
# Compress a single file
python pdf_compress.py report.pdf -l medium

# Batch compress a folder
python pdf_compress.py my_pdfs -l high
```

## Command-line Options

```
python pdf_compress.py <input> [options]

Arguments:
  input                 Input PDF file or folder path

Options:
  -o, --output          Output path (in single-file mode, defaults to <name>__compressed.pdf)
  -l, --level           Compression level: low / medium / high (default: medium)
  -e, --engine          Compression engine: auto / pikepdf / pypdf / ghostscript (default: auto)
  -c, --config          Path to a custom JSON configuration file
  --list-presets        List details of all built-in compression presets
```

## Compression Presets

| Level | JPEG Quality | Color DPI | Grayscale DPI | Mono DPI | Description |
|-------|--------------|-----------|---------------|----------|-------------|
| `low` | 90 | 200 | 200 | 400 | Light compression, preserves maximum quality |
| `medium` | 65 | 150 | 150 | 300 | Balanced compression, trade-off between quality and size |
| `high` | 30 | 100 | 100 | 200 | Aggressive compression, smallest file size |

> The default image compression algorithm is `AUTO`: for color/grayscale images it tries both JPEG and Flate and picks the smaller one; monochrome images always use Flate.

## Usage Examples

### Single File

```bash
# Compress a single file, output to the same directory
python pdf_compress.py report.pdf -l medium
# Result: report__compressed.pdf

# Compress a single file with a custom output path
python pdf_compress.py report.pdf -o result.pdf -l high
```

### Batch Folder

```bash
# Compress all PDFs in a folder (top-level only, non-recursive)
python pdf_compress.py pdfs/ -l high
# Result: pdfs__compressed/xxx__compressed.pdf
```

### Advanced

```bash
# Use the Ghostscript engine (requires Ghostscript installed separately)
python pdf_compress.py report.pdf -l high -e ghostscript

# Use a custom configuration
python pdf_compress.py report.pdf -c my_config.json

# Show preset details
python pdf_compress.py --list-presets
```

## Actual Compression Results

Measured on built-in test PDFs (pikepdf engine):

| File | Level | Original | Compressed | Ratio |
|------|-------|----------|------------|-------|
| 20th Anniversary.pdf | medium | 12.5 MB | 5.4 MB | 57.0% |
| 20th Anniversary.pdf | high | 12.5 MB | 3.3 MB | 73.6% |
| NIPS-2017 Paper.pdf | medium | 556.1 KB | 524.7 KB | 5.6% |
| NIPS-2017 Paper.pdf | high | 556.1 KB | 457.2 KB | 17.8% |

**Notes**:
- Image-heavy PDFs compress best (up to 70-90%)
- Already highly compressed PDFs or plain-text PDFs have limited compression potential
- The `medium` level balances quality and size, suitable for most scenarios
- The new version has a built-in guard that keeps the original image if re-encoding produces a larger stream, so files never grow after compression

## Usage Recommendations

| Scenario | Recommended Level | Notes |
|----------|-------------------|-------|
| Comics / image-heavy PDFs | `medium` or `high` | Significant compression, dramatic size reduction |
| Academic papers / documents | `low` or `medium` | Mostly text and charts; the new version auto-skips images unsuitable for JPEG |
| Scanned documents | `medium` | Balances compression ratio and readability |
| Already highly compressed PDFs | `low` or skip | The new version auto-keeps the original, but `low` is still recommended to save processing time |

## FAQ

**Q: How do I choose a compression level?**  
A:
- `low`: for scenarios requiring high quality (academic papers, print materials)
- `medium`: for most scenarios, balances quality and size (default, recommended)
- `high`: for scenarios where image quality is not important and minimal size is the goal

**Q: Will compression affect PDF image quality?**  
A: There is some impact, but `low` and `medium` have minimal effect. The `high` level noticeably degrades image quality. Monochrome images always use lossless Flate compression, so their quality is unaffected by the JPEG quality setting.

**Q: Which compression engines are supported?**  
A:
- `pikepdf`: based on qpdf, supports full image re-encoding, downsampling, and deduplication; recommended (default)
- `pypdf`: pure Python, only compresses content streams and merges duplicate objects; does not re-encode images
- `ghostscript`: requires separate installation, supports full JPEG quality + DPI downsampling control; strongest compression

**Q: Are images repeated across multiple pages compressed multiple times?**  
A: No. The pikepdf engine deduplicates by image object `objgen`, so each image is processed only once.

**Q: Can already highly optimized PDFs still be compressed?**  
A: Yes, feel free to try. The new version compares the re-encoded data size with the original stream and keeps the original if re-encoding is larger, so files never grow after compression.

## Custom Configuration

Refer to the template file `compress_config_template.json`. The following parameters can be tuned:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `jpeg_quality` | 0-100 | 85 | JPEG image quality; lower means smaller files |
| `downsample_color` | bool | true | Whether to downsample color images |
| `color_dpi_threshold` | int | 225 | Color image downsampling trigger threshold (only downsamples when actual DPI exceeds this) |
| `color_dpi_target` | int | 150 | Color image target DPI after downsampling |
| `downsample_gray` | bool | true | Whether to downsample grayscale images |
| `gray_dpi_threshold` | int | 225 | Grayscale image downsampling trigger threshold |
| `gray_dpi_target` | int | 150 | Grayscale image target DPI after downsampling |
| `downsample_mono` | bool | true | Whether to downsample monochrome images |
| `mono_dpi_threshold` | int | 600 | Monochrome image downsampling trigger threshold |
| `mono_dpi_target` | int | 300 | Monochrome image target DPI after downsampling |
| `color_image_compression` | string | `"auto"` | Color image compression algorithm: `jpeg` / `flate` / `lossless` / `auto` |
| `gray_image_compression` | string | `"auto"` | Grayscale image compression algorithm |
| `mono_image_compression` | string | `"flate"` | Monochrome image compression algorithm (recommend keeping `flate`) |
| `remove_unused_objects` | bool | true | Remove unreferenced resources (enables object streams) |
| `linearize` | bool | false | Linearize output (optimizes progressive web loading) |
| `recompress_flate` | bool | true | Re-compress internal Flate streams |
| `clean_metadata` | bool | true | Clean document metadata |

> `auto` algorithm: tries both JPEG and Flate encoding for color/grayscale images, writes back the smaller one, and compares against the original stream size to decide whether to replace it.

## Working Directory Example

```
Input:
  my_pdfs/
  ├── a.pdf
  └── b.pdf

Run:
  python pdf_compress.py my_pdfs -l medium

Output:
  my_pdfs/              # Original folder unchanged
  ├── a.pdf
  └── b.pdf
  my_pdfs__compressed/  # Compression results
  ├── a__compressed.pdf
  └── b__compressed.pdf
```
