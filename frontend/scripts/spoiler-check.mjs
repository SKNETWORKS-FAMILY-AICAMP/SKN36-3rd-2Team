// 빌드 결과(dist)와 소스(src)에 스포일러가 섞였는지 검사한다. 사용: npm run build && node scripts/spoiler-check.mjs
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, extname } from 'node:path'

const ROOTS = ['dist', 'src']
const TEXT_EXT = new Set(['.js', '.css', '.html', '.json', '.ts', '.tsx', '.md', '.txt', '.map'])

// 정규식 목록: [설명, 패턴]
const RULES = [
  ['정답/범인을 가리키는 키', /\b(culprit|true_?culprit|killer|answer_?(combo|set|key)|solution_?(set|key)|deep_eligible|score_threshold)\b/i],
  ['증거별 가중치/해금 그래프', /\b(unlock_?graph|evidence_?weights?|hidden_?relationship|relationship_edges_source|player_documents_source|qa_source)\b/i],
  ['관리자 문서 이름', /\b(MASTER_v7|technical_appendix|foundation\.md)\b/i],
  ['보조 기록 ID(REC-)', /REC-20(16|26)-[A-Z-]+/],
  ['E10 초과 증거 ID', /\bE(1[1-9]|[2-9]\d)\b/],
  ['범인/자백 단어', /(진범|범인은|자백했|살해했|죽인 사람)/],
  ['정답 판정 키', /\b(isCulprit|correctSuspect|correctEvidence|answerEvidence)\b/],
]
// 화면 문구로 쓰는 안내 문장은 허용 (필요하면 여기에 추가)
const ALLOW_LINES = [/범인 지목/, /범인을 지목/]

function* walk(dir) {
  let names
  try { names = readdirSync(dir) } catch { return }
  for (const n of names) {
    const p = join(dir, n)
    const st = statSync(p)
    if (st.isDirectory()) yield* walk(p)
    else if (TEXT_EXT.has(extname(p))) yield p
  }
}

let hits = 0
for (const root of ROOTS) {
  for (const f of walk(root)) {
    const lines = readFileSync(f, 'utf8').split('\n')
    lines.forEach((line, i) => {
      if (ALLOW_LINES.some((a) => a.test(line))) return
      for (const [why, re] of RULES) {
        const m = line.match(re)
        if (m) {
          hits++
          console.log(`✗ ${f}:${i + 1} [${why}] ${m[0]}`)
        }
      }
    })
  }
}
console.log(hits ? `\n${hits}건 발견` : '스포일러 의심 문자열 없음')
process.exit(hits ? 1 : 0)
