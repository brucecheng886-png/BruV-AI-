# APP Icon 說明

electron-builder 打包需要以下圖示檔案：

| 檔案 | 用途 | 規格 |
|------|------|------|
| `icon.ico` | Windows 安裝程式與捷徑圖示 | 256x256 px，ICO 格式（建議含多尺寸：16/32/48/64/128/256） |
| `icon.icns` | macOS 應用程式圖示 | 1024x1024 px，ICNS 格式 |
| `icon.png` | 通用來源圖 | 1024x1024 px，PNG 格式 |

## 快速產生 icon.ico

若只有 PNG 來源圖，可使用以下工具轉換：
- [IcoConvert](https://icoconvert.com/)
- ImageMagick：`magick convert icon.png -resize 256x256 icon.ico`

## 若暫時不需要 icon

移除 `electron/package.json` 中 `"win"` 和 `"mac"` 區塊的 `"icon"` 欄位，
electron-builder 將使用預設圖示繼續打包。
