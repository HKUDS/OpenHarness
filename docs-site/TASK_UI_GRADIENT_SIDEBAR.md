# 实现 Sidebar 组件渐变效果

## 背景
参考设计规范：`docs/superpowers/specs/2026-04-12-ui-gradient-design.md`

## 依赖
- TASK_UI_GRADIENT_CSS_SYSTEM（渐变 CSS 变量必须可用）

## 修改文件
- `src/components/Sidebar.astro`

## 具体实现

### 1. 添加背景渐变
```html
<aside class="... sidebar-gradient-bg">
```
```css
.sidebar-gradient-bg {
  background: linear-gradient(180deg, var(--color-sidebar-bg) 0%, var(--color-sidebar-bg-dim) 100%);
}
```

### 2. 激活链接使用渐变边框
使用伪元素实现渐变边框效果（而非渐变背景，保持可读性）：
```html
<a class="... sidebar-active-link">
  <span>{node.label}</span>
</a>
```
```css
.sidebar-active-link {
  position: relative;
  background: rgba(59, 130, 246, 0.1);
  color: var(--gradient-primary-start);
}

.sidebar-active-link::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 8px;
  background: var(--gradient-primary);
  z-index: -1;
}
```

### 3. 分区标题使用渐变文字
使用 `background-clip: text` 技术实现渐变文字：
```html
<span class="gradient-text">{node.label}</span>
```
```css
.gradient-text {
  color: var(--color-secondary); /* Fallback */
  background: var(--gradient-secondary);
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
}
```

### 4. 添加页面加载动画
给侧边栏添加 `animate-slide-in-left` 类：
```html
<aside class="... animate-slide-in-left">
```

### 5. 折叠图标使用品牌色
将深色图标改为使用品牌色：
```html
<svg class="..." style="color: var(--gradient-primary-start)">
```

## 验收标准
- [ ] 侧边栏背景有垂直渐变
- [ ] 激活链接有渐变边框
- [ ] 分区标题显示渐变文字
- [ ] 页面加载有滑入动画
- [ ] 折叠图标使用品牌色
- [ ] 亮/暗模式都正确显示
- [ ] 移动端响应式正常
