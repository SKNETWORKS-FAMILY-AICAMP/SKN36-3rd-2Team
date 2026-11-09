import { useEffect, useState } from 'react'
import { npcPortrait, npcTile } from '../data/characters'

interface Props {
  id: string
  alt: string
  className?: string
  /** true면 입상 이미지를 시도하고, 없으면 앨범 타일로 대체 */
  standing?: boolean
}

export default function CharacterPortrait({ id, alt, className, standing }: Props) {
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
