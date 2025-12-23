# compile
- 打包为exe
```shell
pyinstaller --onefile --windowed --clean --noupx --strip `
  --exclude-module=unittest `
  --icon=./icon/icon.ico `
  --add-data "icon;." `
  -n IPHOST同步器 `
  ./host-monitor.py
```

- 基于 icon/icon.ico 自动生成 icon/icon-*.ico 图标
``` shell
py generate_icon_variants.py
```