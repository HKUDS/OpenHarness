# 优化 prose 和代码块样式

## 背景
参考设计规范：`docs/superpowers/specs/2026-04-12-ui-gradient-design.md`

## 依赖
- TASK_UI_GRADIENT_CSS_SYSTEM（渐变 CSS 变量必须可用）

## 修改文件
- `src/pages/docs/[...slug].astro`
- `src/styles/global.css`（添加自定义 CSS）

## 具体实现

### 1. 链接使用品牌渐变色
使用渐变起始色 `#3B82F6`（亮模式）或 `#60A5FA`（暗模式）：
```html
prose-a:text-[#3B82F6] dark:prose-a:text-[#60A5FA]
```
或使用 CSS 变量（需要在 CSS 系统任务中定义 `--gradient-primary-start`）：
```css
:root {
  --gradient-primary-start: #3B82F6;
}

.dark {
  --gradient-primary-start: #60A5FA;
}
```
然后在 prose 类中使用：
```html
prose-a:text-[var(--gradient-primary-start)]
```

### 2. 代码块保持纯色背景，顶部装饰条使用渐变
代码块背景使用纯色以保持可读性，仅在顶部 4px 装饰条使用渐变：
```css
.prose pre {
  position: relative;
  background: var(--color-code-bg);
}

.prose pre::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--gradient-primary);
  border-radius: 8px 8px 0 0;
}
```

### 3. 标题使用渐变文字效果
在 `src/styles/global.css` 中定义：
```css
.prose-headings\:text-gradient {
  color: var(--color-secondary); /* Fallback */
  background: var(--gradient-secondary);
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
}
```
然后在 prose 类中使用：
```html
prose-headings:font-['JetBrains_Mono'] prose-headings:text-gradient
```

### 4. 移动端优化
在小屏幕（< 768px）简化或移除渐变效果：
```css
@media (max-width: 768px) {
  .prose pre::before {
    background: var(--color-border);
  }
}
```

## 验收标准
- [ ] 链接使用品牌渐变色
- [ ] 代码块使用纯色背景
- [ ] 代码块顶部有渐变装饰条
- [ ] 标题使用渐变文字
- [ ] 移动端响应式优化
- [ ] 亮/暗模式都正确显示
