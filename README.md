# PDF 压缩助手

中文 Windows 桌面 PDF 压缩工具。目标 1024KB，保留全部页面、顺序、尺寸及方向，不覆盖原文件。处理在本机进行，无需 Ghostscript。

## 运行

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
