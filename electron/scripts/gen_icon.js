const svg2ico = require('svg2ico')
const fs = require('fs')
const path = require('path')

const svgPath = path.join(__dirname, '../../frontend/public/logo.svg')
const icoPath = path.join(__dirname, '../assets/icon.ico')

const svgBuffer = fs.readFileSync(svgPath)
svg2ico(svgBuffer, { sizes: [16, 32, 48, 64, 128, 256] }).then(icoBuffer => {
  fs.mkdirSync(path.dirname(icoPath), { recursive: true })
  fs.writeFileSync(icoPath, icoBuffer)
  console.log('icon.ico 建立成功：', icoPath)
}).catch(err => {
  console.error('轉換失敗：', err.message)
  process.exit(1)
})
