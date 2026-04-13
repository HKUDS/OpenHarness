import { createApp } from 'vue'
import { createPinia } from 'pinia'

// Naive UI
import naive from 'naive-ui'

import App from './App.vue'
import './assets/styles/main.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(naive)
app.mount('#app')
