# PDF 压缩助手

中文 Windows 桌面 PDF 压缩工具。目标 1024KB，保留全部页面、顺序、尺寸及方向，不覆盖原文件。处理在本机进行，无需 Ghostscript。

## 懒人版：Windows 一键下载

[下载 Windows 64 位免安装版](https://github.com/Mortal-Ass/smart-pdf-compress/releases/latest/download/PDF_Compress_Windows_x64.zip)

下载后先解压，双击 `PDF_Compress.exe` → 选择 PDF → 开始压缩。无需安装 Python、依赖库或 Ghostscript。

普通模式无法达到大小目标时，可勾选“优先达标”重试；此模式可能降低小字和二维码清晰度，并失去文字复制、链接和交互功能。不保证任意 PDF 都能压到 1024KB。

仅支持 Windows 64 位；所有文件均在本机处理，不会上传 PDF。

## 源码运行

需要 Python 3.10+（桌面窗口需要 tkinter）。

```powershell
python -m pip install -r requirements.txt
python pdf_compress_desktop.py
```

## 两种模式

普通模式保留文字结构；优先达标模式允许整页图片重编码，会失去文字选择、链接和交互功能，小字、照片和二维码可能变糊。程序只尝试有限参数，无法保证任意文件都能达到目标。结果均重新打开并逐页渲染检查；二维码仍需实际扫码验证。数字签名文件不自动处理。

## 命令行

```powershell
python smart_pdf_compress.py input.pdf --output-dir output
python smart_pdf_compress.py input.pdf --size-first --output-dir output
```

## 打包 Windows EXE

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --hidden-import pymupdf --collect-binaries pymupdf --name PDF_Compress pdf_compress_desktop.py
```

公开版不包含私人测试材料或角色图标。

## 许可证

AGPL-3.0-or-later。PyMuPDF 使用其自身的 AGPL / 商业双重许可；Pillow 使用其自身许可证。
