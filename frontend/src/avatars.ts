import { accountRequest } from './accountAccess'

export type AvatarState = { image: string | null; revision: string | null }
export const defaultAvatar = (): AvatarState => ({ image: null, revision: null })
export const readAvatar = (base: string, token: string) => accountRequest<AvatarState>(base, token, '/accounts/avatar')
export const writeAvatar = (base: string, token: string, image: string | null, revision: string | null) =>
  accountRequest<AvatarState>(base, token, '/accounts/avatar', { image, expected_revision: revision }, 'PUT')

export function cropRectangle(width: number, height: number, zoom: number, x: number, y: number) {
  const side = Math.min(width, height) / Math.max(1, Math.min(3, zoom))
  return { x: (width - side) * Math.max(0, Math.min(100, x)) / 100,
    y: (height - side) * Math.max(0, Math.min(100, y)) / 100, side }
}

export function loadAvatarFile(file: File): Promise<HTMLImageElement> {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
    return Promise.reject(new Error('请选择 JPG、PNG 或 WebP 图片；HEIC 照片请先转换为 JPG。'))
  if (!file.size || file.size > 5 * 1024 * 1024)
    return Promise.reject(new Error('请选择不超过 5 MB 的图片。'))
  return new Promise((resolve, reject) => {
    const reader = new FileReader(), image = new Image()
    const cleanup = () => { clearTimeout(timer); reader.onload = reader.onerror = reader.onabort = null; image.onload = image.onerror = null }
    const fail = (message: string) => { cleanup(); reader.abort(); image.src = ''; reject(new Error(message)) }
    const timer = setTimeout(() => fail('图片读取超时，请换一张较小的图片。'), 15000)
    reader.onerror = reader.onabort = () => fail('无法读取这张图片，请重新选择。')
    image.onerror = () => fail('图片已损坏或格式不受支持，请换一张图片。')
    reader.onload = () => { image.src = String(reader.result) }
    image.onload = () => {
      if (Math.min(image.naturalWidth, image.naturalHeight) < 64) { fail('图片过小，请选择宽高至少 64 像素的图片。'); return }
      if (image.naturalWidth * image.naturalHeight > 25_000_000 || Math.max(image.naturalWidth, image.naturalHeight) > 10000) { fail('图片分辨率过大，请缩小后重试。'); return }
      cleanup(); resolve(image)
    }
    reader.readAsDataURL(file)
  })
}
