# 第三方组件与许可

本仓库自身以 MIT 许可发布（见 `LICENSE`）。以下第三方作品被依赖或移植进本仓库，
其原始许可与版权声明随附于此。

## ch347-py

- 来源：https://github.com/pengwon/ch347-py
- 版本：锁定 commit `352384216832f8ae358e84859612480990c394ff`
- 许可：MIT，Copyright (c) 2023 Peter
- 使用方式：作为运行时依赖（`pyproject.toml` 中的 git 直接引用）。包内自带沁恒
  （WCH）发布的 `CH347DLL.DLL` / `CH347DLLA64.DLL`，这两个二进制文件按 WCH 的发布
  条款随 `ch347-py` 分发，本仓库不单独再分发。

## I2CTool

- 来源：https://github.com/pengwon/I2CTool
- 许可：MIT，Copyright (c) 2025 Peter
- 使用方式：`src/core/eeprom.py` 的 EEPROM 型号描述与读写流程（随机/顺序读、按页写、
  写周期等待、校验、整片擦除）移植自该项目的 `i2ctool_core/`；`I2CAdapter` 接口形状
  参考其 `interfaces.py`。本项目为 PyQt6 应用，未使用其 PySide6/Tauri 前端。

两个上游项目的 MIT 许可全文如下：

```
MIT License

Copyright (c) 2023 Peter            (ch347-py)
Copyright (c) 2025 Peter            (I2CTool)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
