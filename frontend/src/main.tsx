import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/noto-serif-kr/korean-400.css'
import '@fontsource/noto-serif-kr/korean-700.css'
import '@fontsource/noto-serif-kr/latin-400.css'
import '@fontsource/noto-serif-kr/latin-700.css'
import '@fontsource/noto-sans-kr/korean-400.css'
import '@fontsource/noto-sans-kr/korean-500.css'
import '@fontsource/noto-sans-kr/korean-700.css'
import '@fontsource/noto-sans-kr/latin-400.css'
import '@fontsource/noto-sans-kr/latin-500.css'
import '@fontsource/noto-sans-kr/latin-700.css'
import '@fontsource/nanum-gothic-coding/korean-400.css'
import '@fontsource/nanum-gothic-coding/latin-400.css'
import './styles/tokens.css'
import './styles/typography.css'
import './styles/effects.css'
import './styles/ui.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
