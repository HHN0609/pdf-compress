# PDF 压缩工具

基于 Python 的 PDF 压缩脚本，支持多档位压缩配置，可处理单个文件或批量文件夹。

## 功能特点

- 支持单文件和文件夹批量压缩
- 三档压缩级别（low/medium/high）
- 多引擎支持（pikepdf/pypdf/ghostscript）
- 自定义压缩配置
- 不覆盖源文件，输出文件名自动添加 `__compressed` 后缀

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

| 档位 | JPEG 质量 | 彩色 DPI | 灰度 DPI | 说明 |
|------|----------|----------|----------|------|
| `low` | 90 | 200 | 200 | 轻量压缩，保持最高画质 |
| `medium` | 65 | 150 | 150 | 平衡压缩，兼顾质量与体积 |
| `high` | 30 | 100 | 100 | 强力压缩，最小文件体积 |

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

测试数据（52 个 PDF 文件，总计 9.1 GB）：

| 文件类型 | 原始大小 | 压缩后大小 | 压缩率 |
|---------|---------|-----------|--------|
| 彩色漫画（AI全彩） | 222.2 MB | 19.5 MB | 91.2% |
| 彩色漫画（机翻） | 235.1 MB | 49.7 MB | 78.9% |
| 画集 | 492.8 MB | 147.3 MB | 70.1% |
| 单行本漫画（平均） | ~200 MB | ~170 MB | 10-15% |
| **总计** | **9.1 GB** | **7.6 GB** | **17.1%** |

**说明**：
- 彩色图片为主的 PDF 压缩效果最佳（可达 70-90%）
- 已高度压缩的 PDF 或纯文本 PDF 压缩效果有限
- `medium` 档位平衡质量与体积，适合大多数场景
- **注意**：对于纯文本 PDF 或已高度优化的文件，压缩后可能略微变大（如 556 KB → 677 KB），这是因为重新编码图片流会引入额外开销。对于这类文件，建议使用 `low` 档位或不压缩。

## 使用建议

| 场景 | 推荐档位 | 说明 |
|------|---------|------|
| 漫画/图片为主的 PDF | `medium` 或 `high` | 压缩效果显著，可大幅减小体积 |
| 学术论文/文档 | `low` | 以文字为主，压缩效果有限，保持较高画质 |
| 扫描件 | `medium` | 平衡压缩率和可读性 |
| 已高度压缩的 PDF | 不压缩或 `low` | 避免压缩后体积反而增大 |

## 常见问题

**Q: 为什么有些文件压缩后反而变大了？**  
A: 对于纯文本 PDF 或已高度优化的文件，重新编码图片流会引入额外开销。这类文件建议使用 `low` 档位或不压缩。

**Q: 如何选择压缩档位？**  
A: 
- `low`: 适合需要保持高画质的场景（如学术论文、印刷品）
- `medium`: 适合大多数场景，平衡质量和体积（默认推荐）
- `high`: 适合对画质要求不高，只追求最小体积的场景

**Q: 压缩后的 PDF 画质会受影响吗？**  
A: 会有一定影响，但 `low` 和 `medium` 档位的影响通常很小。`high` 档位会明显降低图片质量。

**Q: 支持哪些压缩引擎？**  
A: 
- `pikepdf`: 基于 qpdf，压缩效果好，推荐（默认）
- `pypdf`: 纯 Python 实现，兼容性最好
- `ghostscript`: 需要单独安装，压缩效果最强

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
