import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as Icons from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router.js'

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus)
app.use(router)

for (const [name, comp] of Object.entries(Icons)) {
  app.component(name, comp)
}

app.mount('#app')
