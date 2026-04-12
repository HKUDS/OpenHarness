# 优化 prose 和代码块样式

## 背景
参考设计规范：`docs/superpowers/specs/2026-04-12-ui-gradient-design.md`

## 依赖
- TASK_UI_GRADIENT_CSS_SYSTEM（渐变 CSS 变量必须可用）

## 修改文件
- `src/pages/docs/[...slug].astro`

## 具体实现

### 1. 链接使用品牌渐变色
```html
prose-a:text-[var(--gradient-primary-start)] dark:prose-a:text-[var(--gradient-primary-start)]
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
```html
prose-headings:text-gradient
```
```css
.text-gradient {
  color: var(--color-secondary); /* Fallback */
  background: var(--gradient-secondary);
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
}
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
