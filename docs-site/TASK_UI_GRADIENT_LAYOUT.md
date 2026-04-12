# 实现主内容区域渐变效果

## 背景
参考设计规范：`docs/superpowers/specs/2026-04-12-ui-gradient-design.md`

## 依赖
- TASK_UI_GRADIENT_CSS_SYSTEM（渐变 CSS 变量必须可用）

## 修改文件
- `src/layouts/DocLayout.astro`

## 具体实现

### 1. 主内容区域背景使用渐变
```html
<body class="... main-gradient-bg">
```
```css
.main-gradient-bg {
  background: linear-gradient(180deg, var(--color-bg-start) 0%, var(--color-bg-end) 100%);
}
```

### 2. 添加页面加载动画
给主内容区域添加 `animate-fade-in-up` 类：
```html
<main class="... animate-fade-in-up">
```

### 3. 更新布局间距适配浮动导航栏
确保 `pt-20` 适配 `top-4` 的浮动导航栏：
```html
<main class="flex-1 lg:ml-64 pt-20 min-h-screen transition-all duration-300">
```

## 验收标准
- [ ] 主内容区域有垂直渐变背景
- [ ] 页面加载有淡入动画
- [ ] 布局间距适配浮动导航栏
- [ ] 亮/暗模式都正确显示
