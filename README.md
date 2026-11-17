# PDF 压缩助手

中文 Windows 桌面 PDF 压缩工具。目标 1024KB，保留全部页面、顺序、尺寸及方向，不覆盖原文件。处理在本机进行，无需 Ghostscript。

## 手机本地版

[手机浏览器打开使用](https://mortal-ass.github.io/smart-pdf-compress/)

无需登录，选择 PDF 后在浏览器内存中逐页处理，不上传 PDF。首次打开需联网下载同源的 PDF.js / pdf-lib 组件，没有统计脚本。建议使用较新的 Safari / Chrome；首版限制 30MB、100 页，处理时保持页面前台。手机本地版采用整页图片转换，文字选择、链接、表单和签名功能不再保留；二维码需实际扫码验证。保留页面顺序、裁剪区域与旋转，生成后逐页重新打开并渲染检查；无法保证所有文件均达到 1024KB。

页面源码位于 `docs/`，静态托管于 GitHub Pages。浏览器会为获取网页和组件向 GitHub Pages 发起请求，PDF 字节不发送到网络。尚未覆盖所有 Android / iOS 真机，请先用副本验证。

手机网页开发：`npm ci` 安装锁定的依赖，`node scripts/vendor-mobile.cjs` 更新同源组件，`python -m http.server 8765 --directory docs` 本地预览。测试：`node tests/mobile-smoke.cjs 输入PDF绝对路径 输出PDF绝对路径`；此测试使用 Node 原生 canvas 检查同一份网页压缩代码，不替代手机浏览器真机测试。网页 PDF.js（Apache-2.0）、pdf-lib（MIT）及附属字体/解码器许可证保存在 `docs/vendor/`。

## Windows 一键下载

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

Windows v1.0.1 起，优先达标先从高画质尝试，再在同一 JPEG 质量下细调分辨率（最多 6 次），选择测试中达标且分辨率更高的结果，避免首次达标后留下大量未利用空间。文件更大不必然更清晰，仍需复核实际内容。手机网页使用独立的浏览器算法。

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
