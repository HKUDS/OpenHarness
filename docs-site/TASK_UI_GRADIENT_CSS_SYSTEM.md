# 实现 CSS 变量和动画系统

## 背景
参考设计规范：`docs/superpowers/specs/2026-04-12-ui-gradient-design.md`

## 依赖
无

## 修改文件
- `src/styles/global.css`

## 具体实现

### 1. 添加缺失的颜色变量
```css
:root {
  --color-sidebar-bg-dim: #E8EEF5;
}

.dark {
  --color-sidebar-bg-dim: #0F172A;
}
```

### 2. 定义渐变 CSS 变量
```css
:root {
  /* 渐变定义 */
  --gradient-primary: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%);
  --gradient-secondary: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%);
  --gradient-code: linear-gradient(180deg, #F1F5F9 0%, #E0E7FF 100%);
  --gradient-border: linear-gradient(90deg, #3B82F6, #8B5CF6, #EC4899);
}

.dark {
  --gradient-primary: linear-gradient(135deg, #60A5FA 0%, #A78BFA 100%);
  --gradient-secondary: linear-gradient(135deg, #818CF8 0%, #C084FC 100%);
  --gradient-code: linear-gradient(180deg, #1E293B 0%, #312E81 100%);
  --gradient-border: linear-gradient(90deg, #60A5FA, #A78BFA, #F472B6);
}
```

### 3. 定义动画关键帧
```css
@keyframes fade-in-down {
  from { opacity: 0; transform: translateY(-20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes slide-in-left {
  from { opacity: 0; transform: translateX(-20px); }
  to { opacity: 1; transform: translateX(0); }
}
```

### 4. 定义动画工具类
```css
.animate-fade-in-down {
  animation: fade-in-down 300ms var(--ease-smooth) forwards;
}

.animate-fade-in-up {
  animation: fade-in-up 400ms var(--ease-smooth) forwards;
}

.animate-slide-in-left {
  animation: slide-in-left 400ms var(--ease-smooth) forwards;
}
```

### 5. 添加减少动效媒体查询
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

## 验收标准
- [ ] 亮/暗模式都有完整的 CSS 变量定义
- [ ] 渐变变量使用正确的语法
- [ ] 动画关键帧正确定义
- [ ] 动画工具类正确引用关键帧
- [ ] prefers-reduced-motion 媒体查询正确定义
- [ ] 所有变量都有亮/暗模式变体
- [ ] CSS 在亮/暗模式下都能正常工作
