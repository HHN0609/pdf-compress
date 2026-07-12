# PDF 压缩工具

基于 Python 的 PDF 压缩脚本，支持多档位压缩配置，可处理单个文件或批量文件夹。

## 功能特点

- 支持单文件和文件夹批量压缩
- 三档压缩级别（low/medium/high）
- 多引擎支持（pikepdf/pypdf/ghostscript）
- 自定义压缩配置
- 不覆盖源文件，输出文件名自动添加 `__compressed` 后缀
- 基于实际显示 DPI 的智能降采样（按页面 mediabox 推算图片有效 DPI）
- 按图片模式分流处理：彩色/灰度/黑白图分别走对应压缩策略
- AUTO 算法：对彩色/灰度图同时尝试 JPEG 与 Flate，取较小者，避免图表被 JPEG 反向放大
- 多页共享图片自动去重，避免重复压缩同一对象
- 安全保护：若重编码后比原始流更大则保留原图，避免对线稿/已优化图造成反效果
- JPEG 编码使用 progressive + optimize，进一步减小体积

## 安装

```bash
# 创建虚拟环境（推荐，避免依赖冲突）
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate.bat    # Windows PowerShell（如被拦截用 .bat）
source venv/bin/activate     # Mac / Linux

# 安装依赖
pip install -r requirements.txt
```

如果不想用虚拟环境，也可以直接执行 `pip install -r requirements.txt`。

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

| 档位 | JPEG 质量 | 彩色 DPI | 灰度 DPI | 黑白 DPI | 说明 |
|------|----------|----------|----------|----------|------|
| `low` | 90 | 200 | 200 | 400 | 轻量压缩，保持最高画质 |
| `medium` | 65 | 150 | 150 | 300 | 平衡压缩，兼顾质量与体积 |
| `high` | 30 | 100 | 100 | 200 | 强力压缩，最小文件体积 |

> 默认图片压缩算法为 `AUTO`：对彩色/灰度图同时尝试 JPEG 与 Flate 取较小者，黑白图固定使用 Flate。

## 使用示例

### 单文件压缩

```bash
# 单文件压缩，输出到同目录
python pdf_compress.py report.pdf -l medium
# 结果: report__compressed.pdf

# 单文件压缩，指定输出路径
python pdf_compress.py report.pdf -o result.pdf -l high
```

### 文件夹批量压缩

```bash
# 压缩文件夹内所有 PDF（仅顶层，不递归子文件夹）
python pdf_compress.py pdfs/ -l high
# 结果: pdfs__compressed/xxx__compressed.pdf
```

### 高级用法

```bash
# 使用 Ghostscript 引擎（需要单独安装 Ghostscript）
python pdf_compress.py report.pdf -l high -e ghostscript

# 使用自定义配置
python pdf_compress.py report.pdf -c my_config.json

# 查看档位详情
python pdf_compress.py --list-presets
```

## 实际压缩效果

内置测试 PDF 实测（pikepdf 引擎）：

| 文件 | 档位 | 原始大小 | 压缩后 | 压缩率 |
|------|------|----------|--------|--------|
| 20th 周年纪念.pdf | medium | 12.5 MB | 5.4 MB | 57.0% |
| 20th 周年纪念.pdf | high | 12.5 MB | 3.3 MB | 73.6% |
| NIPS-2017 论文.pdf | medium | 556.1 KB | 524.7 KB | 5.6% |
| NIPS-2017 论文.pdf | high | 556.1 KB | 457.2 KB | 17.8% |

**说明**：
- 彩色图片为主的 PDF 压缩效果最佳（可达 70-90%）
- 已高度压缩的 PDF 或纯文本 PDF 压缩效果有限
- `medium` 档位平衡质量与体积，适合大多数场景
- 新版本已内置"重编码后比原图大就保留原图"的保护逻辑，不会出现压缩后文件反而变大的情况

## 使用建议

| 场景 | 推荐档位 | 说明 |
|------|---------|------|
| 漫画/图片为主的 PDF | `medium` 或 `high` | 压缩效果显著，可大幅减小体积 |
| 学术论文/文档 | `low` 或 `medium` | 以文字和图表为主，新版本会自动跳过不适合 JPEG 的图 |
| 扫描件 | `medium` | 平衡压缩率和可读性 |
| 已高度压缩的 PDF | `low` 或不压缩 | 新版本会自动保留原图，但仍建议用 `low` 减少处理时间 |

## 常见问题

**Q: 如何选择压缩档位？**  
A: 
- `low`: 适合需要保持高画质的场景（如学术论文、印刷品）
- `medium`: 适合大多数场景，平衡质量和体积（默认推荐）
- `high`: 适合对画质要求不高，只追求最小体积的场景

**Q: 压缩后的 PDF 画质会受影响吗？**  
A: 会有一定影响，但 `low` 和 `medium` 档位的影响通常很小。`high` 档位会明显降低图片质量。黑白图固定使用无损 Flate 压缩，画质不受 JPEG 质量影响。

**Q: 支持哪些压缩引擎？**  
A: 
- `pikepdf`: 基于 qpdf，支持完整的图片重编码、降采样、去重等功能，推荐（默认）
- `pypdf`: 纯 Python 实现，仅压缩内容流和合并重复对象，不重编码图片
- `ghostscript`: 需要单独安装，支持完整的 JPEG 质量 + DPI 降采样控制，压缩效果最强

**Q: 多页 PDF 中重复出现的图片会被多次压缩吗？**  
A: 不会。pikepdf 引擎会按图片对象的 `objgen` 去重，同一张图片只处理一次。

**Q: 已经高度优化的 PDF 还能压缩吗？**  
A: 可以放心尝试。新版本会对比重编码后的数据与原始流大小，若重编码后反而变大则保留原图，不会出现压缩后文件变大的情况。

## 自定义配置

参考模板文件 `compress_config_template.json`，可调整以下参数：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `jpeg_quality` | 0-100 | 85 | JPEG 图片质量，越低文件越小 |
| `downsample_color` | bool | true | 是否对彩色图降采样 |
| `color_dpi_threshold` | int | 225 | 彩色图降采样触发阈值（实际 DPI 高于此值才降采样） |
| `color_dpi_target` | int | 150 | 彩色图降采样目标 DPI |
| `downsample_gray` | bool | true | 是否对灰度图降采样 |
| `gray_dpi_threshold` | int | 225 | 灰度图降采样触发阈值 |
| `gray_dpi_target` | int | 150 | 灰度图降采样目标 DPI |
| `downsample_mono` | bool | true | 是否对黑白图降采样 |
| `mono_dpi_threshold` | int | 600 | 黑白图降采样触发阈值 |
| `mono_dpi_target` | int | 300 | 黑白图降采样目标 DPI |
| `color_image_compression` | string | `"auto"` | 彩色图压缩算法：`jpeg` / `flate` / `lossless` / `auto` |
| `gray_image_compression` | string | `"auto"` | 灰度图压缩算法 |
| `mono_image_compression` | string | `"flate"` | 黑白图压缩算法（建议保持 `flate`） |
| `remove_unused_objects` | bool | true | 移除未引用资源（启用 object stream） |
| `linearize` | bool | false | 线性化输出（优化网页渐进加载） |
| `recompress_flate` | bool | true | 对内部 Flate 流再次压缩 |
| `clean_metadata` | bool | true | 清理文档元数据 |

> `auto` 算法说明：对彩色/灰度图同时尝试 JPEG 与 Flate 编码，取字节数较小者写回，并对比原始流大小决定是否替换。

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
