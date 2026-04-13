<template>
  <div class="markdown-text" v-html="renderedMarkdown"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

const props = defineProps<{
  content: string
}>()

// 配置 Markdown 解析器
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  highlight: function (str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch (__) {}
    }
    return ''
  }
})

const renderedMarkdown = computed(() => {
  if (!props.content) return ''
  return md.render(props.content)
})
</script>

<style scoped>
.markdown-text {
  line-height: 1.6;
  color: var(--n-text-color);
}

.markdown-text :deep(h1),
.markdown-text :deep(h2),
.markdown-text :deep(h3),
.markdown-text :deep(h4),
.markdown-text :deep(h5),
.markdown-text :deep(h6) {
  margin-top: 1.5rem;
  margin-bottom: 1rem;
  font-weight: 600;
}

.markdown-text :deep(h1:first-child),
.markdown-text :deep(h2:first-child),
.markdown-text :deep(h3:first-child) {
  margin-top: 0;
}

.markdown-text :deep(p) {
  margin-bottom: 1rem;
}

.markdown-text :deep(code) {
  background: var(--n-code-color);
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 0.9em;
}

.markdown-text :deep(pre) {
  background: var(--n-code-color);
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
  margin-bottom: 1rem;
}

.markdown-text :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown-text :deep(ul),
.markdown-text :deep(ol) {
  margin-left: 2rem;
  margin-bottom: 1rem;
}

.markdown-text :deep(li) {
  margin-bottom: 0.5rem;
}

.markdown-text :deep(blockquote) {
  border-left: 4px solid var(--n-primary-color);
  padding-left: 1rem;
  margin-left: 0;
  margin-bottom: 1rem;
  color: var(--n-text-color-2);
}

.markdown-text :deep(a) {
  color: var(--n-primary-color);
  text-decoration: none;
}

.markdown-text :deep(a:hover) {
  text-decoration: underline;
}

.markdown-text :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 1rem;
}

.markdown-text :deep(th),
.markdown-text :deep(td) {
  border: 1px solid var(--n-border-color);
  padding: 0.5rem;
  text-align: left;
}

.markdown-text :deep(th) {
  background: var(--n-th-color);
  font-weight: 600;
}
</style>
