import { HashRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AnimatePresence, MotionConfig, motion } from 'framer-motion'
import Main from './screens/Main/Main'
import Placeholder from './screens/Placeholder/Placeholder'
import Chat from './screens/Chat/Chat'
import Evidence from './screens/Evidence/Evidence'
import Relations from './screens/Relations/Relations'
import Story from './screens/Story/Story'
import Accuse from './screens/Accuse/Accuse'
import Final from './screens/Final/Final'
import { useEffect } from 'react'
import { useNoteStore } from './store/noteStore'

function OpenNotes() {
  useEffect(() => useNoteStore.getState().setPanel(true), [])
  return <Navigate to="/chat" replace />
}
import NotesPanel from './components/NotesPanel'

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
    <HashRouter>
      <AnimatedRoutes />
      <NotesPanel />
      <div className="fx-grain" aria-hidden="true" />
      <div className="fx-vignette" aria-hidden="true" />
    </HashRouter>
    </MotionConfig>
  )
}

/** 화면이 바뀔 때 어두워졌다가 밝아지는 짧은 전환. 사건 파일을 넘기는 느낌을 위해 아주 약하게 위로 올라온다. */
function AnimatedRoutes() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname.split('/')[1] || 'main'}
        className="page-fade"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
      >
        <Routes location={location}>
        <Route path="/" element={<Main />} />
        <Route path="/story" element={<Story />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/chat/:npcId" element={<Chat />} />
        <Route path="/evidence" element={<Evidence />} />
        <Route path="/relations" element={<Relations />} />
        <Route path="/notes" element={<OpenNotes />} />
        <Route path="/accuse" element={<Accuse />} />
        <Route path="/final" element={<Final />} />
        <Route path="*" element={<Placeholder title="찾을 수 없는 화면" />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  )
}
