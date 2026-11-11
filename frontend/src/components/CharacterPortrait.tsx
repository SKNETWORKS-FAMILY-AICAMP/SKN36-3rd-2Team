import { useEffect, useState } from 'react'
import { npcPortrait, npcTile } from '../data/characters'

interface Props {
  id: string
  alt: string
  className?: string
  /** 기본 true: 2026 입상 사용, 없으면 앨범 타일로 대체. false면 2016 앨범 타일 */
  standing?: boolean
}

export default function CharacterPortrait({ id, alt, className, standing = true }: Props) {
  const primary = standing ? npcPortrait(id) : npcTile(id)
  const [src, setSrc] = useState(primary)
  useEffect(() => setSrc(primary), [primary])
  return (
    <img
      className={className}
      src={src}
      alt={alt}
      draggable={false}
      onError={() => {
        const tile = npcTile(id)
        if (src !== tile) setSrc(tile)
      }}
    />
  )
}
