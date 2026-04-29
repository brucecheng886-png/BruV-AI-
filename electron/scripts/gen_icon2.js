const sharp = require('sharp')
const { default: pngToIco } = require('png-to-ico')
const fs = require('fs')
const path = require('path')

const svgPath = path.join(__dirname, '../../frontend/public/logo.svg')
const icoPath = path.join(__dirname, '../assets/icon.ico')

async function convert() {
  const sizes = [16, 32, 48, 64, 128, 256]
  const pngBuffers = await Promise.all(
    sizes.map(size =>
      sharp(svgPath).resize(size, size).png().toBuffer()
    )
  )
  const icoBuffer = await pngToIco(pngBuffers)
  fs.mkdirSync(path.dirname(icoPath), { recursive: true })
  fs.writeFileSync(icoPath, icoBuffer)
  console.log('icon.ico 建立成功：', icoPath)
}
convert().catch(err => {
  console.error('轉換失敗：', err.message)
  process.exit(1)
})
