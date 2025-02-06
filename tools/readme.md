# 编译

```shell
pyinstaller --onefile --windowed --clean --noupx --strip  --exclude-module=unittest --icon=icon.ico ./host-updater.py
```