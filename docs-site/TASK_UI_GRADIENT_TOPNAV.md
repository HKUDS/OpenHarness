# 实现 TopNav 组件渐变效果

## 背景
参考设计规范：`docs/superpowers/specs/2026-04-12-ui-gradient-design.md`

## 依赖
- TASK_UI_GRADIENT_CSS_SYSTEM（渐变 CSS 变量必须可用）

## 修改文件
- `src/components/TopNav.astro`

## 具体实现

### 1. 添加渐变边框效果
使用伪元素 `::after` 实现底部渐变边框：
```html
<header class="... navbar-gradient-border">
```
```css
.navbar-gradient-border {
  position: relative;
}

.navbar-gradient-border::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--gradient-border);
  transition: opacity 0.3s;
}
```

### 2. Logo 容器使用渐变背景
```html
<div class="w-8 h-8 text-white font-bold text-sm shadow-[var(--shadow-sm)]" style="background: var(--gradient-primary)">OH</div>
```

### 3. 添加页面加载动画
给导航栏添加 `animate-fade-in-down` 类：
```html
<header class="... animate-fade-in-down">
```

### 4. 优化链接 hover 效果
链接 hover 时显示下划线动画：
```html
<a class="... nav-link">Home</a>
```
```css
.nav-link {
  position: relative;
}

.nav-link::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  width: 0;
  height: 1px;
  background: currentColor;
  transition: width 200ms ease;
}

.nav-link:hover::after {
  width: 100%;
}
```

### 5. 主题切换按钮优化
hover 时显示渐变边框，添加渐变类：
```html
<button class="... theme-btn" style="background: var(--gradient-primary)">
```

## 验收标准
- [ ] 导航栏底部有渐变边框
- [ ] Logo 容器使用渐变背景
- [ ] 页面加载有淡入动画
- [ ] 链接 hover 有下划线动画
- [ ] 主题切换按钮 hover 有渐变效果
- [ ] 亮/暗模式都正确显示
- [ ] 响应式在移动端正常工作
