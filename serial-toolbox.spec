# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# main.py 之外还有大量“方法内运行时导入”（protocol_plugin._register_*、
# script_engine、i2c_bus 的 ch347 等），静态分析无法发现，必须显式收集。
hiddenimports = (
    collect_submodules('src')
    + collect_submodules('pyqtgraph')
    + collect_submodules('ch347')
)

# ch347-py 按包内相对路径加载厂商 DLL（适配器显式传 dll_path），
# 因此要原样落到 ch347/lib/ 下，不能只当普通二进制丢到根目录。
ch347_data = collect_data_files('ch347', includes=['lib/*.DLL', 'include/*.H'])

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=ch347_data,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='serial-toolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
