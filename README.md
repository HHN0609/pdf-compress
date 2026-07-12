# PDF 压缩工具

基于 Python 的 PDF 压缩脚本，支持多档位压缩配置，可处理单个文件或批量文件夹。

## 安装

```bash
pip install -r requirements.txt
```

如需最佳压缩效果，可额外安装 [Ghostscript](https://ghostscript.com/releases/gsdnld.html) 并添加到系统 PATH。

## 快速开始

```bash
# 单文件压缩
python pdf_compress.py report.pdf -l medium

# 文件夹批量压缩
python pdf_compress.py my_pdfs -l high
```

## 命令参数

```
python pdf_compress.py <输入> [选项]

参数:
  input                 输入 PDF 文件或文件夹路径

选项:
  -o, --output          输出路径（单文件模式下不指定则输出到 <原名>__compressed.pdf）
  -l, --level           压缩档位: low / medium / high（默认 medium）
  -e, --engine          压缩引擎: auto / pikepdf / pypdf / ghostscript（默认 auto）
  -c, --config          自定义 JSON 配置文件路径
  --list-presets        列出所有内置压缩档位详情
```

## 压缩档位

| 档位 | JPEG 质量 | 彩色 DPI | 灰度 DPI | 说明 |
|------|----------|----------|----------|------|
| `low` | 90 | 200 | 200 | 轻量压缩，保持最高画质 |
| `medium` | 65 | 150 | 150 | 平衡压缩，兼顾质量与体积 |
| `high` | 30 | 100 | 100 | 强力压缩，最小文件体积 |

## 使用示例

```bash
# 单文件压缩，输出到同目录
python pdf_compress.py report.pdf -l medium
# 结果: report__compressed.pdf

# 单文件压缩，指定输出路径
python pdf_compress.py report.pdf -o result.pdf -l high

# 压缩文件夹内所有 PDF
python pdf_compress.py pdfs/ -l high
# 结果: pdfs__compressed/xxx__compressed.pdf

# 使用 Ghostscript 引擎
python pdf_compress.py report.pdf -l high -e ghostscript

# 使用自定义配置
python pdf_compress.py report.pdf -c my_config.json

# 查看档位详情
python pdf_compress.py --list-presets
```

## 自定义配置

参考模板文件 `compress_config_template.json`，可调整以下参数：

| 字段 | 类型 | 说明 |
|------|------|------|
| `jpeg_quality` | 0-100 | JPEG 图片质量，越低文件越小 |
| `color_dpi_target` | int | 彩色图降采样目标 DPI |
| `gray_dpi_target` | int | 灰度图降采样目标 DPI |
| `mono_dpi_target` | int | 单色图降采样目标 DPI |
| `recompress_flate` | bool | 对内部流再压缩 |
| `remove_unused_objects` | bool | 移除未引用资源 |

## 工作目录示例

```
输入:
  my_pdfs/
  ├── a.pdf
  └── b.pdf

运行:
  python pdf_compress.py my_pdfs -l medium

输出:
  my_pdfs/              # 原文件夹不变
  ├── a.pdf
  └── b.pdf
  my_pdfs__compressed/  # 压缩结果
  ├── a__compressed.pdf
  └── b__compressed.pdf
```
