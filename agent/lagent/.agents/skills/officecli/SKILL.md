---
name: officecli
description: "用本机命令行驱动 Microsoft Office（Word / Excel / PowerPoint）完成文档生成、批量格式转换与内容抽取。适用于：把 Markdown、CSV、文本大纲变成 .docx/.xlsx/.pptx；把 Office 文档转成 PDF 或逐页 PNG；从 docx/xlsx/pptx 中提取正文、表格、工作表与幻灯片文字；对整个文件夹做批量转换。技能自带 scripts/office.py 命令行工具，优先走 win32com COM 自动化（保真度最高，可导出 PDF/PNG、刷新公式、处理 Office 能打开的任何格式），缺少 Office 时退回 python-docx 纯 Python 路线；含环境探测、格式转换矩阵、COM 卡死与弹窗排查，以及「不覆盖源文件、只报告真实产物」的交付约定。"
---

# OfficeCLI — 本机 Office 命令行工作流

**你最终会拿到什么。** 一定是磁盘上真实存在的产物，并附路径与字节大小：

- **文档** —— `.docx` / `.xlsx` / `.pptx`
- **转换结果** —— `.pdf`，或逐页 `.png`，或每表一份 `.csv`
- **抽取结果** —— 文本（stdout 或 `.txt` 文件）

拿不到产物时，如实报告失败发生在哪一层（文件被占用、COM 弹窗、格式不支持），不要用「应该已经生成」搪塞。

## 第一步：探测环境

除非本轮已经探测过，否则先跑：

```bash
python scripts/office.py probe
```

它只读注册表、不启动应用，输出 JSON：Office 各组件是否注册、COM ProgID、可用 Python 库（`docx`/`openpyxl`/`pptx`/`pandas`）、外部工具（`soffice`/`pandoc`）。**据此选路线，不要假设环境。**

需要确认某组件真的能启动（注册表有但不一定能跑，例如激活失败），加 `--launch`，它会真正 Dispatch 再 Quit 一次，较慢但确定。

## 路线选择

| 路线 | 什么时候用 | 局限 |
| --- | --- | --- |
| **COM（win32com）** 首选 | 需要保真输出：PDF、PNG、公式重算、图表、任意 Office 可打开格式 | 依赖 Office；可能弹窗/卡死，必须遵守「COM 铁律」 |
| **python-docx** 退路 | 只需要生成/读取结构简单的 `.docx`；无 Office 环境 | 不支持 `.doc`、PDF、公式渲染 |
| **LibreOffice `soffice`** | probe 报告存在时，可做无 GUI 批量转换 | 本机未安装则不可用，不要试 |
| **纯文本** | 只想给出内容、不需要真文档 | 用户要文件时不算交付 |

本机实测：Office 16 已装，三条 COM 通道（Word/Excel/PowerPoint）可用；`python-docx` 可用；`openpyxl`、`python-pptx` 未安装——所以生成 `.xlsx`/`.pptx` 走 COM，不要去 pip 装库，除非用户同意。

## 自带命令

```bash
python scripts/office.py probe                                  # 环境探测（只读，秒级）
python scripts/office.py docx-from-md  in.md   out.docx         # Markdown → docx（#/##/### 标题，- 列表）
python scripts/office.py xlsx-from-csv in.csv  out.xlsx         # CSV → xlsx（首行表头、自动识别数字）
python scripts/office.py pptx-from-outline in.txt out.pptx      # 大纲 → pptx（'# ' 开新页，'## '/'- ' 要点）
python scripts/office.py to-pdf        in.anything out.pdf      # 任意 Office 文件 → PDF（自动识别类型）
python scripts/office.py extract-text  in.docx                  # 抽正文；-o out.txt 写文件
python scripts/office.py excel-to-csv  in.xlsx   outdir/        # 每个工作表一份 CSV
python scripts/office.py pptx-to-png   in.pptx   outdir/        # 每页 PNG（1920×1080）
```

`to-pdf` 自动按扩展名分派：Word 类（`.doc` `.docx` `.rtf` `.odt` `.txt`）、Excel 类（`.xls` `.xlsx` `.csv`）、PowerPoint 类（`.ppt` `.pptx` `.odp`）。可用 `--app word|excel|ppt` 强制指定。

`extract-text` / `excel-to-csv` 也接受 `.xlsx`、`.pptx`；需要 `.doc`（旧格式）或精确版式时，用 COM 路线。

批量处理：对本目录下每个文件循环调用上面命令，一次一条，不要写超长内联脚本。失败的文件记下来单独报，不要让一个坏文件中断整批。

## COM 铁律

1. **一律绝对路径。** 相对路径会在 Office 的当前目录里解析错，中文路径必须保持原样、不要转码。
2. **`app.Visible = False`**（PowerPoint 例外，它常常不接受此设置），**`app.DisplayAlerts = 0`**，否则「是否保存」对话框会让进程永久挂住。
3. **`finally` 里必须 Quit。** 异常中途退出也要退出应用，否则残留的 `WINWORD.EXE` 会锁住文件，下一次转换报「文件正在使用」。
4. **打开即只读。** `Documents.Open(path, ReadOnly=True)`、`Workbooks.Open(path, ReadOnly=True)` —— 源文件绝不能被改动。
5. **`SaveAs` 前先确保目标目录存在**，并让扩展名与目标格式一致（导出 PDF 时文件名必须以 `.pdf` 结尾，否则 Office 会追加后缀或报错）。
6. **单次操作给足超时。** 转 PDF 常常 20–60 秒，首次启动更慢；`RunCLI` 的 `timeout` 设 300，不要用默认 60。
7. **超时后先查残留进程**，再重试：`tasklist | findstr /I "WINWORD EXCEL POWERPNT"`。确认卡死再用 `taskkill /F /IM`。
8. **不要并发。** 多个脚本同时驱动同一个 Office 应用（尤其 Excel）会互相抢「当前工作簿」，结果错乱。串行跑。
9. **`Dispatch` 而非 `EnsureDispatch`**（后者会生成早期绑定缓存，环境变动后易失效），除非你确实需要常量枚举。
10. **导出 PDF 用 `ExportAsFixedFormat`**，比 `SaveAs` 更能避开格式对话框；PowerPoint 用 `Presentation.SaveAs(path, 32)`。

## 各应用要点

- **Word**：`Documents.Open` → `ExportAsFixedFormat(out, 17)`（17 = wdFormatPDF）→ `doc.Close(0)`。批注、修订会按当前显示状态导出。详见 `references/word.md`。
- **Excel**：PDF 用 `Workbook.ExportAsFixedFormat(0, out)`（0 = xlTypePDF）；读值走 `Worksheet.UsedRange.Value`（二维元组，日期会变成浮点序列号，需要自己判断）；CSV 由脚本自己写，**不要**用 `SaveAs(..., 6)`——那是本地化分隔符，中文环境会变逗号/分号不一致。详见 `references/excel.md`。
- **PowerPoint**：PDF 用 `SaveAs(out, 32)`；图片用 `Presentation.Export(outdir, "PNG", 1920, 1080)`，中文环境下生成的文件名可能是 `幻灯片1.PNG`——**导出后必须列目录取真实文件名**，不要预测。详见 `references/powerpoint.md`。

格式细节、参数对照与更多配方见 `references/conversion-matrix.md`。

## 交付约定

- **不覆盖源文件。** 输出默认落到用户指定路径；没指定就落在源文件旁的 `<源文件名>.out/` 目录里，并在回复中说明位置。
- **只报告真实产物。** 路径、字节大小来自实际 `stat`；页数、幻灯片数、行数能取到就报，取不到就不提。
- **失败要说清层级**，例如「Excel COM 已启动但 `Workbooks.Open` 报文件占用」比「转换失败」有用得多。
- 交付时先给产物，再补一句用了哪条路线（COM / python-docx），以及任何格式损耗（如字体替换、图片压缩）。

## 排查速查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 命令卡住不返回 | 弹出了对话框（保存/激活/只读提示） | 查残留进程并结束，加 `DisplayAlerts=0` 重跑 |
| `Open` 报「文件正在使用」 | 上一个 COM 进程没退出 | `tasklist` 找进程 → `taskkill /F /IM EXCEL.EXE` |
| PDF 页码/版式与屏幕不同 | 打印区域、分页符、纸张设置差异 | 先设 `PageSetup`，或用 `ExportAsFixedFormat` 而非 `PrintOut` |
| Excel 日期变成 45000 这类数字 | COM 传的是 OLE 序列号 | 用 `datetime(1899,12,30) + timedelta(days=v)` 换算 |
| PowerPoint 导出文件名对不上 | 本地化命名 | 导出后 `list_dir` 取实际文件名 |
| 中文乱码 | 用系统默认编码读写文本 | 所有文本文件按 UTF-8 读写，CSV 写 `utf-8-sig` 便于 Excel 打开 |

更完整的 COM 陷阱清单见 `references/com-pitfalls.md`。

## 参考文件

- `references/conversion-matrix.md` —— 格式常量、目标格式对照、批量转换骨架
- `references/word.md` —— Word 配方：转换、抽取、页眉页脚、目录、替换
- `references/excel.md` —— Excel 配方：读写值、公式重算、多表导出、CSV 编码
- `references/powerpoint.md` —— PowerPoint 配方：生成、导出 PDF/PNG、备注与文字抽取
- `references/com-pitfalls.md` —— 卡死、弹窗、占用、时序与并发陷阱
