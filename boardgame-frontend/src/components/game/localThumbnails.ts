/**
 * 이름으로 찾는 로컬 썸네일.
 *
 * 백엔드에 이미지 업로드/서빙 핸들러가 없어서(src/api/mappers.ts 의 resolveImageUrl 주석)
 * board_game.image_url 은 사실상 비어 있다. 서버가 이미지를 주기 전까지 데모용 게임만이라도
 * 그림이 보이도록 직접 그린 SVG 를 붙인다.
 *
 * 서버 imageUrl 이 있으면 그 값이 항상 우선한다 — 이 표는 폴백이다.
 * 저작권 문제가 없도록 실제 제품 아트가 아니라 게임 특징만 도형으로 그렸다.
 */
import dixit from '@/assets/games/dixit.svg'
import halligalli from '@/assets/games/halligalli.svg'
import rummikub from '@/assets/games/rummikub.svg'
import stella from '@/assets/games/stella.svg'

/** 공백·구두점을 지우고 소문자로. '할리 갈리' 와 'Halli-Galli' 를 같게 본다. */
function normalize(name: string): string {
  return name.toLowerCase().replace(/[^0-9a-z가-힣]/g, '')
}

/**
 * 부분 일치로 찾는다 — 서버 이름이 '스텔라(딕싯 유니버스)' 처럼 붙어 올 수 있다.
 * 그래서 순서가 중요하다: 'stella' 를 'dixit' 보다 먼저 봐야 딕싯 그림이 가로채지 않는다.
 */
const THUMBNAILS: { aliases: string[]; asset: string }[] = [
  { aliases: ['스텔라', 'stella'], asset: stella },
  { aliases: ['루미큐브', 'rummikub'], asset: rummikub },
  { aliases: ['할리갈리', 'halligalli'], asset: halligalli },
  { aliases: ['딕싯', 'dixit'], asset: dixit },
]

/** 맞는 그림이 없으면 null — GameThumbnail 이 이름 첫 글자를 그린다. */
export function localThumbnail(name: string): string | null {
  if (!name) return null

  const key = normalize(name)
  const match = THUMBNAILS.find(({ aliases }) =>
    aliases.some((alias) => key.includes(alias)),
  )

  return match?.asset ?? null
}
