
import { useEffect, useRef, useState } from 'react'
import {
  BookOpen,
  MessageCircle,
  FileSearch,
  Network,
  Target,
  CircleHelp,
  Lightbulb,
  X,
  type LucideIcon,
} from 'lucide-react'

import styles from './GameHelp.module.css'

interface Props {
  open: boolean
  onClose: () => void
}

type GuideId =
  | 'start'
  | 'chat'
  | 'evidence'
  | 'tools'
  | 'accuse'
  | 'help'

interface GuideStep {
  title: string
  description: string
  example?: string
}

interface GuideSection {
  id: GuideId
  title: string
  subtitle: string
  icon: LucideIcon
  steps: GuideStep[]
  tips: string[]
}

const GUIDES: GuideSection[] = [
  {
    id: 'start',
    title: '게임 시작하기',
    subtitle: '사건을 조사하는 기본적인 진행 순서입니다.',
    icon: BookOpen,
    steps: [
      {
        title: '사건의 배경을 확인하세요.',
        description:
          '게임을 시작하면 과거의 사건과 현재 발생한 사건을 보여주는 스토리가 진행됩니다. 등장인물과 사건이 일어난 장소를 기억해 두면 이후 조사에 도움이 됩니다.',
      },
      {
        title: '사건 현장을 둘러보세요.',
        description:
          '스토리가 끝나면 로비, 내부 계단, 기록실, 사무실 등을 선택할 수 있습니다. 각 장소를 클릭하면 현장에서 관찰한 내용을 확인할 수 있습니다.',
      },
      {
        title: '첫 번째 관계자와 대화하세요.',
        description:
          '「관계자에게 이야기를 듣는다」 버튼을 누르면 인물 대화로 이동합니다. 인물에게 직접 질문을 작성해 사건에 관한 진술을 확보하세요.',
      },
      {
        title: '단서를 수집하고 조사를 확장하세요.',
        description:
          '대화 중 발견한 증거를 확보하고 다른 인물에게 제시하면 새로운 진술이나 조사 가능한 인물이 열릴 수 있습니다.',
      },
      {
        title: '충분히 조사한 뒤 범인을 지목하세요.',
        description:
          '증거와 진술을 비교하고 추리 노트에 정리한 뒤, 범인 지목 화면에서 최종 판단을 내립니다.',
      },
    ],
    tips: [
      '모든 인물을 처음부터 만날 수 있는 것은 아닙니다.',
      '증거와 인물은 조사가 진행되면서 단계적으로 공개됩니다.',
      '스토리를 건너뛰어도 현장 탐색과 실제 조사는 계속할 수 있습니다.',
    ],
  },
  {
    id: 'chat',
    title: '인물과 대화하기',
    subtitle: 'AI 인물에게 직접 질문하며 사건을 조사합니다.',
    icon: MessageCircle,
    steps: [
      {
        title: '대화할 인물을 선택하세요.',
        description:
          '인물 대화 화면 상단에는 조사 대상자의 사진이 있습니다. 현재 대화 가능한 인물은 선택할 수 있고, 잠긴 인물은 추가 조사를 통해 해금해야 합니다.',
      },
      {
        title: '질문을 직접 작성하세요.',
        description:
          '일반적인 선택지 게임과 달리 질문을 자유롭게 입력할 수 있습니다. 사건 발생 시간, 피해자와의 관계, 마지막으로 목격한 장소 등을 구체적으로 물어보세요.',
        example:
          '예시 질문\n"사건이 발생한 밤에는 어디에 계셨나요?"\n"신기범 씨와 마지막으로 대화한 건 언제였나요?"',
      },
      {
        title: '답변에서 중요한 사실을 찾으세요.',
        description:
          '인물이 알려주는 시간, 장소, 행동, 다른 사람에 대한 언급을 확인하세요. 모든 인물이 사건 전체를 알고 있는 것은 아니므로 여러 사람의 진술을 비교하는 것이 중요합니다.',
      },
      {
        title: '추가 질문으로 진술을 구체화하세요.',
        description:
          '답변이 모호하다면 관련 내용을 조금 더 구체적으로 질문해 보세요. 동일한 질문을 반복하기보다 대상, 장소, 시간을 분명하게 지정하는 편이 좋습니다.',
        example:
          '첫 질문: "그날 무슨 일이 있었나요?"\n추가 질문: "그날 밤 9시 이후 기록실에 간 적이 있나요?"',
      },
      {
        title: '증거를 확보한 뒤 다시 질문하세요.',
        description:
          '처음에는 답변하지 않던 내용도 관련 증거를 수집하거나 제시한 이후에는 새로운 진술이 나올 수 있습니다. 이전에 대화했던 인물도 다시 조사해 보세요.',
      },
    ],
    tips: [
      'Enter는 메시지 전송, Shift+Enter는 줄바꿈입니다.',
      'AI 인물의 답변은 게임 진행 상태와 접근 가능한 정보에 따라 달라집니다.',
      '답변을 거절할 때는 다른 단서를 먼저 확보하거나 질문을 구체화해 보세요.',
    ],
  },
  {
    id: 'evidence',
    title: '증거 수집과 제시',
    subtitle: '새로운 단서를 확보하고 진술의 변화를 확인합니다.',
    icon: FileSearch,
    steps: [
      {
        title: '대화 중 증거를 발견하세요.',
        description:
          '인물과 대화하면서 특정 사건 기록이나 자료에 접근하면 새로운 증거를 확보할 수 있는 상태가 됩니다. 단순히 관련 이야기를 들었다고 모든 증거가 자동 수집되지는 않습니다.',
      },
      {
        title: '「확보」 버튼을 누르세요.',
        description:
          '대화 화면에 「새로운 단서가 확인됐습니다」 안내와 확보 버튼이 나타나면 이를 클릭하세요. 확보한 증거는 증거 보관함에 등록됩니다.',
      },
      {
        title: '증거 보관함에서 내용을 확인하세요.',
        description:
          '상단 「증거 보관함」 메뉴를 열면 확보한 자료의 제목과 본문을 볼 수 있습니다. 아직 수집하지 못한 증거는 잠금 상태로 표시됩니다.',
      },
      {
        title: '관련 인물에게 증거를 제시하세요.',
        description:
          '인물 대화 화면 아래쪽의 「증거 제시」 버튼을 누른 뒤, 이미 확보한 증거를 선택합니다. 인물의 반응을 통해 추가 정보를 확인할 수 있습니다.',
        example:
          '플레이 예시\n1. A 인물에게 질문하여 자료를 발견\n2. 「확보」 버튼으로 증거 수집\n3. B 인물에게 이동\n4. 「증거 제시」로 자료 선택\n5. 새로운 반응을 확인하고 추가 질문',
      },
      {
        title: '새로운 조사 기회를 확인하세요.',
        description:
          '증거를 수집하고 제시하는 과정에서 새로운 인물이 해금되거나 추가 증거를 수집할 수 있습니다. 확보 후에는 인물 목록과 수집 가능 증거를 다시 확인하세요.',
      },
    ],
    tips: [
      '증거는 먼저 확보한 뒤 제시할 수 있습니다.',
      '모든 증거를 모든 인물에게 제시할 수 있는 것은 아닙니다.',
      '증거 제시만으로 수집이 완료되지 않을 수 있으니 「확보」 버튼을 확인하세요.',
      '수집한 증거는 서버 게임 상태에 반영됩니다.',
    ],
  },
  {
    id: 'tools',
    title: '추리 도구 사용하기',
    subtitle: '수집한 정보를 비교하고 자신의 추리를 정리합니다.',
    icon: Network,
    steps: [
      {
        title: '인물 관계도를 확인하세요.',
        description:
          '상단 「인물 관계도」 메뉴에서는 현재 확인된 인물과 관계를 살펴볼 수 있습니다. 새로운 관계 정보는 조사 진행에 따라 추가될 수 있습니다.',
      },
      {
        title: '시간 순서로 사건을 정리하세요.',
        description:
          '각 인물의 진술에서 사건 발생 전후의 시간과 장소를 찾아보세요. 같은 시간대에 서로 다른 장소를 언급하거나 다른 사람의 진술과 맞지 않는 부분이 있다면 추가로 확인할 가치가 있습니다.',
        example:
          '정리 예시\n20:30 — A 인물의 진술\n21:00 — B 인물의 목격 내용\n21:30 — 확인되지 않은 시간대',
      },
      {
        title: '추리 노트를 작성하세요.',
        description:
          '상단 「추리 노트」 또는 대화 화면의 노트 버튼을 통해 의심스러운 점, 사건의 흐름, 인물별 진술을 직접 기록할 수 있습니다.',
      },
      {
        title: '사실과 추측을 구분하세요.',
        description:
          '확보한 증거에서 확인된 내용과 아직 검증하지 못한 추측을 구분하여 적어 두면 최종 지목할 때 도움이 됩니다.',
        example:
          '확인된 사실: 확보한 문서에 기록된 시간\n추측: 그 시간에 특정 인물이 현장에 있었을 가능성',
      },
    ],
    tips: [
      '추리 노트에 작성한 문장은 자동으로 정답 판정에 반영되지 않습니다.',
      '관계도에는 게임 진행 상태에 따라 공개된 정보만 표시됩니다.',
      '증거 보관함, 관계도, 대화 기록을 번갈아 확인하면서 조사하세요.',
    ],
  },
  {
    id: 'accuse',
    title: '범인 지목과 엔딩',
    subtitle: '수집한 단서를 근거로 최종 추리를 제출합니다.',
    icon: Target,
    steps: [
      {
        title: '범인 지목 가능 상태인지 확인하세요.',
        description:
          '처음부터 범인을 지목할 수는 없습니다. 충분한 증거를 확보하여 서버의 지목 조건을 충족해야 지목 기능이 활성화됩니다.',
      },
      {
        title: '의심하는 인물을 선택하세요.',
        description:
          '「범인 지목」 화면에서 현재 선택 가능한 인물 중 범인이라고 판단하는 사람을 선택합니다.',
      },
      {
        title: '근거 증거를 선택하세요.',
        description:
          '확보한 증거 중 1~3개를 선택하여 최종 추리 기록에 남기세요. 실제 범인 판정은 서버가 관리하는 게임 상태와 규칙에 따라 진행됩니다.',
      },
      {
        title: '지목 결과를 확인하세요.',
        description:
          '지목에 실패하면 남은 기회가 줄어들 수 있습니다. 반면 증거가 부족하여 지목 자체가 허용되지 않은 경우에는 기회가 소모되지 않습니다.',
      },
      {
        title: '사건의 결말을 확인하세요.',
        description:
          '게임이 종료되면 엔딩 스토리를 볼 수 있습니다. 결과에 따라 결말이 달라지며, 서버에서 성공을 확인한 경우에만 비공개 사건의 진실이 공개됩니다.',
      },
    ],
    tips: [
      '범인 지목 기회는 최대 3회입니다.',
      '지목하기 전에 증거와 인물의 진술을 충분히 비교하세요.',
      '선택한 근거 증거와 추리 노트는 자신의 조사 기록을 정리하기 위한 정보입니다.',
      '사건이 종료된 뒤에는 최종 기록 화면에서 결과를 다시 확인할 수 있습니다.',
    ],
  },
  {
    id: 'help',
    title: '막혔을 때 확인하세요',
    subtitle: '게임 진행 중 자주 발생하는 상황과 해결 방법입니다.',
    icon: CircleHelp,
    steps: [
      {
        title: 'NPC가 답변을 거절합니다.',
        description:
          '아직 관련 정보가 공개되지 않았거나, 현재 대화에서 검증할 수 있는 근거가 부족할 수 있습니다. 다른 증거를 먼저 수집한 뒤 다시 질문해 보세요.',
        example:
          '시도할 방법\n- 사건 발생 시간이나 장소를 구체적으로 질문\n- 다른 인물과 먼저 대화\n- 관련 증거 확보 후 재질문',
      },
      {
        title: '증거를 발견했는데 보관함에 없습니다.',
        description:
          '대화 화면에 「확보」 버튼이 나타나 있는지 확인하세요. 발견 가능한 상태와 실제 확보 완료 상태는 다릅니다.',
      },
      {
        title: '증거 제시 후에도 새로운 정보가 없습니다.',
        description:
          '해당 인물과 관련 없는 증거일 수 있으며, 다른 선행 조사가 필요할 수 있습니다. 증거 본문을 다시 살펴보고 관련된 사람에게 질문해 보세요.',
      },
      {
        title: '다른 인물이 잠겨 있습니다.',
        description:
          '특정 증거를 확보해야 다음 인물이 열릴 수 있습니다. 현재 대화 가능한 인물을 조사하고 증거 확보 알림을 확인하세요.',
      },
      {
        title: '범인 지목 버튼이 비활성화되어 있습니다.',
        description:
          '아직 서버의 지목 조건을 충족하지 못했을 수 있습니다. 증거 수집 상태를 확인하고 조사를 이어가세요.',
      },
      {
        title: '게임을 이어서 진행하고 싶습니다.',
        description:
          '메인 화면에서 「이어하기」를 이용하세요. 서버에 저장된 게임 세션을 기준으로 진행 상태를 복구합니다. 브라우저 데이터나 서버 세션을 삭제한 경우에는 복구가 어려울 수 있습니다.',
      },
    ],
    tips: [
      '대부분의 진행 막힘은 새로운 질문, 증거 확보, 다른 인물 조사로 해결할 수 있습니다.',
      '답변 오류가 발생했다고 지목이나 증거 제시 요청을 무조건 반복해서 전송하지 마세요.',
      '상단 도움말 버튼을 누르면 게임 도중 언제든 이 안내서를 다시 볼 수 있습니다.',
    ],
  },
]

export default function GameHelp({
  open,
  onClose,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const closeRequested = useRef(false)

  const [activeId, setActiveId] =
    useState<GuideId>('start')

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (open && !dialog.open) {
      closeRequested.current = false
      setActiveId('start')
      dialog.showModal()
    } else if (!open && dialog.open) {
      // 프로그램으로 닫을 때 중복 onClose를 방지합니다.
      closeRequested.current = true
      dialog.close()
    }
  }, [open])

  const requestClose = () => {
    if (closeRequested.current) return
    closeRequested.current = true
    onClose()
  }

  const current =
    GUIDES.find((guide) => guide.id === activeId) ??
    GUIDES[0]

  const ActiveIcon = current.icon

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-labelledby="game-help-title"
      onCancel={(event) => {
        event.preventDefault()
        requestClose()
      }}
      onClose={() => {
        if (!closeRequested.current) requestClose()
      }}
    >
      <header className={styles.header}>
        <div>
          <p className={styles.kicker}>
            CASE 001 · INVESTIGATION MANUAL
          </p>

          <h2
            id="game-help-title"
            className={styles.title}
          >
            수사 안내서
          </h2>

          <p className={styles.intro}>
            인물과 대화하고 증거를 모아 사건의 진실을 밝혀보세요.
            각 기능의 사용 방법을 단계별로 안내합니다.
          </p>
        </div>

        <button
          type="button"
          className={styles.close}
          onClick={requestClose}
          aria-label="도움말 닫기"
        >
          <X size={22} />
        </button>
      </header>

      <nav
        className={styles.tabs}
        aria-label="도움말 항목"
      >
        {GUIDES.map((guide, index) => {
          const Icon = guide.icon

          return (
            <button
              key={guide.id}
              type="button"
              className={`${styles.tab} ${
                activeId === guide.id
                  ? styles.tabActive
                  : ''
              }`}
              aria-pressed={activeId === guide.id}
              onClick={() => setActiveId(guide.id)}
            >
              <Icon size={16} />
              <span>
                {String(index + 1).padStart(2, '0')}.
                {' '}{guide.title}
              </span>
            </button>
          )
        })}
      </nav>

      <div className={styles.content} key={activeId}>
        <div className={styles.sectionHead}>
          <div className={styles.sectionIcon}>
            <ActiveIcon size={24} />
          </div>

          <div>
            <h3>{current.title}</h3>
            <p>{current.subtitle}</p>
          </div>
        </div>

        <ol className={styles.steps}>
          {current.steps.map((step, index) => (
            <li key={step.title} className={styles.step}>
              <span className={styles.stepNumber}>
                {String(index + 1).padStart(2, '0')}
              </span>

              <div className={styles.stepBody}>
                <h4>{step.title}</h4>
                <p>{step.description}</p>

                {step.example && (
                  <div className={styles.example}>
                    <strong>실제 사용 예시</strong>
                    <p>{step.example}</p>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>

        <aside className={styles.tips}>
          <h4>
            <Lightbulb size={17} />
            알아두면 좋은 팁
          </h4>

          <ul>
            {current.tips.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </aside>
      </div>

      <footer className={styles.footer}>
        <p>
          진행이 막히면 언제든 도움말을 다시 확인하세요.
          사건의 정답은 포함되어 있지 않습니다.
        </p>

        <button
          type="button"
          className={styles.start}
          onClick={requestClose}
        >
          확인하고 게임하기
        </button>
      </footer>
    </dialog>
  )
}
