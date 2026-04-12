# 扩展 Tailwind 配置支持 CSS 变量

## 背景
参考设计规范：`docs/superpowers/specs/2026-04-12-ui-gradient-design.md`

## 依赖
- TASK_UI_GRADIENT_CSS_SYSTEM（CSS 变量必须先定义）

## 修改文件
- `tailwind.config.mjs`

## 具体实现

### 1. 添加颜色扩展
在 `theme.extend.colors` 中添加 CSS 变量引用：
```javascript
colors: {
  'bg-start': 'var(--color-bg-start)',
  'bg-end': 'var(--color-bg-end)',
  'text-primary': 'var(--color-text)',
  'text-secondary': 'var(--color-secondary)',
  'sidebar-bg': 'var(--color-sidebar-bg)',
  'sidebar-bg-dim': 'var(--color-sidebar-bg-dim)',
  'border': 'var(--color-border)',
  'cta': 'var(--color-cta)',
  'hover-bg': 'var(--color-hover-bg)',
  'active-bg': 'var(--color-active-bg)',
  'active-text': 'var(--color-active-text)',
}
```

### 2. 添加动画扩展
```javascript
animation: {
  'fade-in-down': 'fade-in-down 300ms var(--ease-smooth) forwards',
  'fade-in-up': 'fade-in-up 400ms var(--ease-smooth) forwards',
  'slide-in-left': 'slide-in-left 400ms var(--ease-smooth) forwards',
}
```

## 验收标准
- [ ] Tailwind 配置文件更新
- [ ] 颜色变量正确扩展
- [ ] 动画变量正确扩展
- [ ] TypeScript/IntelliSense 能识别新变量
- [ ] 构建不报错
