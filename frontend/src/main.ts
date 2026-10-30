import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import './mobile.css'
import './account.css'
import './assessments.css'
import './assistantExperience.css'

const app = createApp(App)
const assetsChanged = () => window.dispatchEvent(new Event('rag:assets-stale'))
window.addEventListener('vite:preloadError', event => {
  event.preventDefault()
  assetsChanged()
})
app.config.errorHandler = error => {
  const message = error instanceof Error ? error.message : String(error)
  if (/dynamically imported module|Unable to preload CSS|Importing a module script failed/.test(message)) assetsChanged()
  else console.error(error)
}
app.mount('#app')
