# UI 动态互动化设计 - 让文档网站更有趣

> **项目:** OpenHarness 文档网站
> **日期:** 2026-04-12
> **状态:** 设计中

---

## 设计目标

将文档网站从"渐变多彩"升级为"动态互动"体验，增加微交互、趣味动效和沉浸感，让用户在使用文档时感到愉悦和惊喜。

**核心原则:**
- 趣味但不失专业
- 互动但不干扰阅读
- 有趣但不花哨
- 细节但不喧宾夺主

---

## 新增视觉特性

### 1. 呼吸式背景

```
效果：缓慢流动的渐变背景，营造"呼吸"感
实现：CSS 动画 + 渐变背景位置
时长：20秒循环
```

**CSS 实现:**
```css
:root {
  --bg-gradient-start: linear-gradient(135deg, #F8FAFC 0%, #EEF2FF 50%, #E0E7FF 100%);
  --bg-gradient-end: linear-gradient(135deg, #0F172A 0%, #1E1B4B 50%, #312E81 100%);
}

.breathing-bg {
  background-size: 200% 200%;
  background-position: 0% 0%;
  animation: breathing-bg 20s ease-in-out infinite;
}

@keyframes breathing-bg {
  0%, 100% { background-position: 0% 0%; }
  50% { background-position: 100% 100%; }
}
```

### 2. 浮动装饰元素

```
效果：页面角落有 subtle 的浮动物体（几何形状或粒子）
实现：纯 CSS 形状 + float 动画
可关闭：通过 prefers-reduced-motion 禁用
```

**装饰元素类型:**
- 圆角矩形（半透明渐变）
- 小圆点（品牌色）
- 细线条（装饰用）

**CSS 实现:**
```css
.floating-shape {
  position: fixed;
  pointer-events: none;
  opacity: 0.1;
  z-index: -1;
  animation: float-soft 15s ease-in-out infinite;
}

@keyframes float-soft {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-20px) rotate(5deg); }
}

/* 不同延迟和位置 */
.shape-1 { top: 10%; left: 5%; animation-delay: 0s; }
.shape-2 { top: 20%; right: 10%; animation-delay: 3s; }
.shape-3 { bottom: 15%; left: 15%; animation-delay: 6s; }
```

### 3. 按钮涟漪效果

```
效果：点击按钮时从点击位置扩散的圆形波纹
实现：CSS 伪元素或 JS 计算位置
```

**CSS 实现:**
```css
.ripple-btn {
  position: relative;
  overflow: hidden;
}

.ripple-btn::after {
  content: '';
  position: absolute;
  width: 100%;
  height: 100%;
  background: radial-gradient(circle, var(--gradient-primary-start) 0%, transparent 70%);
  opacity: 0;
  transform: scale(0);
  transition: opacity 0.6s, transform 0.6s;
}

.ripple-btn:active::after {
  opacity: 1;
  transform: scale(2);
}
```

### 4. 链接智能下划线

```
效果：hover 时下划线从中心向两侧扩展
实现：CSS transform + transition
```

**CSS 实现:**
```css
.smart-link {
  position: relative;
  color: var(--gradient-primary-start);
}

.smart-link::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 50%;
  width: 0;
  height: 2px;
  background: var(--gradient-primary);
  transform: translateX(-50%);
  transition: width 0.3s ease-out;
}

.smart-link:hover::after {
  width: 100%;
}
```

### 5. 代码块打字动效

```
效果：首页关键代码示例显示打字效果
实现：JS 逐字添加，配合光标闪烁
仅限：首页 2-3 个关键示例
```

**实现思路:**
- 使用 `data-typing` 属性标记需要打字的代码块
- JS 监听元素进入视口后触发
- 每个字符延迟 20-40ms

### 6. 侧边栏展开/收起动画

```
效果：点击分区时，内容平滑展开，箭头旋转
实现：CSS max-height 或 grid 动画
```

**CSS 实现:**
```css
.sidebar-content {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.4s var(--ease-smooth);
}

.sidebar-content.open {
  max-height: 500px; /* 足够大即可 */
}

.sidebar-chevron {
  transition: transform 0.3s var(--ease-spring);
}

.sidebar-chevron.rotated {
  transform: rotate(180deg);
}
```

### 7. 滚动进度指示器

```
效果：页面顶部细线，随滚动进度填充
实现：JS 监听 scroll 事件
```

**HTML:**
```html
<div id="scroll-progress" class="fixed top-0 left-0 right-0 h-1 z-50"></div>
```

**CSS:**
```css
#scroll-progress {
  background: var(--gradient-border);
  transform-origin: left;
  transform: scaleX(0);
  transition: transform 0.1s linear;
}
```

### 8. 标题悬停效果

```
效果：hover 标题时显示微妙的光晕或下划线动画
实现：CSS 伪元素
```

**CSS 实现:**
```css
.prose h2:hover {
  color: var(--gradient-primary-start);
}

.prose h2::before {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  width: 0;
  height: 3px;
  background: var(--gradient-primary);
  transition: width 0.3s ease-out;
}

.prose h2:hover::before {
  width: 100%;
}
```

### 9. 卡片悬停抬升

```
效果：hover 时卡片块轻微上浮，阴影加深
实现：transform + box-shadow 过渡
```

**CSS 实现:**
```css
.hover-lift {
  transition: transform 0.3s var(--ease-spring), box-shadow 0.3s;
}

.hover-lift:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0,0,0,0.15);
}
```

### 10. 主题切换旋转动效

```
效果：切换主题时图标旋转 180 度
实现：CSS transform
```

**CSS 实现:**
```css
.theme-icon {
  transition: transform 0.5s var(--ease-spring);
}

.theme-icon.rotating {
  transform: rotate(180deg);
}
```

### 11. 页面过渡动画

```
效果：页面切换时内容淡入淡出
实现：Astro ViewTransitions
```

**Astro 配置:**
```astro
<slot name="head">
  <ViewTransitions />
</slot>
```

**CSS:**
```astro
<style is:global>
  .astro-page {
    animation: fade-in-up 0.5s ease-out;
  }

  @keyframes fade-in-up {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
</style>
```

---

## 新增文件结构

### 1. `src/components/FloatingShapes.astro`

```
组件：浮动的背景装饰形状
输出：3-4 个 fixed 定位的几何形状
```

```astro
---
---
<div class="floating-shapes-container">
  <div class="floating-shape shape-1"></div>
  <div class="floating-shape shape-2"></div>
  <div class="floating-shape shape-3"></div>
</div>

<style>
  /* 形状样式 */
  .floating-shape {
    /* ... */
  }
</style>
```

### 2. `src/components/ScrollProgress.astro`

```
组件：滚动进度指示器
```

```astro
---
---
<div id="scroll-progress" class="fixed top-0 left-0 right-0 h-1 z-50"></div>

<script>
  // 监听滚动，更新进度条宽度
  const progress = document.getElementById('scroll-progress');
  window.addEventListener('scroll', () => {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const percent = scrollTop / docHeight;
    progress?.style.transform = `scaleX(${percent})`;
  });
</script>
```

### 3. `src/components/TypingCode.astro`（可选）

```
组件：带打字动效的代码块
```

### 4. `src/scripts/interactions.ts`

```
JS 模块：统一管理交互逻辑
- 涟漪效果
- 打字动效
- 其他需要 JS 的交互
```

---

## 修改文件清单

### 1. `src/styles/global.css`

**新增 CSS:**
- 呼吸背景动画 (`breathing-bg`)
- 浮动形状动画 (`floating-shape`)
- 智能链接下划线 (`smart-link`)
- 涟漪按钮 (`ripple-btn`)
- 标题悬停效果
- 卡片抬升效果 (`hover-lift`)
- 主题切换旋转 (`.theme-icon.rotating`)

### 2. `src/layouts/DocLayout.astro`

**修改:**
- 导入 `FloatingShapes` 组件
- 添加 `ScrollProgress` 组件
- 应用 `breathing-bg` 到 body 或主容器
- 添加 ViewTransitions 支持

### 3. `src/components/TopNav.astro`

**修改:**
- 链接添加 `smart-link` 类
- 按钮添加 `ripple-btn` 类
- 主题切换图标添加 `theme-icon` 类

### 4. `src/components/Sidebar.astro`

**修改:**
- 链接添加 `smart-link` 类
- 折叠面板使用平滑过渡动画
- chevron 图标添加旋转类

### 5. `src/pages/docs/[...slug].astro`

**修改:**
- prose 标题添加悬停效果
- 首页关键代码块添加打字动效（可选）
- 警告框/提示框添加 `hover-lift` 类

### 6. `src/pages/docs/index.astro`（如果存在）

**修改:**
- 添加 Hero 区域
- 使用打字动效展示示例代码
- 添加快速导航卡片（带 hover 抬升）

---

## 性能优化

### CSS 优化

- 使用 `will-change` 提示浏览器优化动画
- 动画使用 `transform` 和 `opacity`（不触发布局重排）
- 装饰元素使用 `pointer-events: none`

### JS 优化

- 滚动事件使用 `requestAnimationFrame` 节流
- 打字动效使用 `IntersectionObserver` 懒触发
- 避免不必要的 DOM 操作

### 资源

- 所有动画使用 CSS（避免 JS 动画）
- 减少重绘区域

---

## 可访问性

### 动画控制

```css
@media (prefers-reduced-motion: reduce) {
  .breathing-bg {
    animation: none;
  }

  .floating-shape {
    display: none;
  }

  .smart-link::after {
    transition: none;
  }

  .hover-lift {
    transform: none;
  }
}
```

### 焦点状态

- 所有交互元素保持清晰的 focus 状态
- 键盘导航不受动画影响

### 对比度

- 所有渐变效果保持足够对比度（≥4.5:1）
- 装饰元素不降低内容可读性

---

## 验收标准

### 背景效果
- [ ] 呼吸背景流动自然（20秒循环）
- [ ] 装饰元素浮动不干扰内容
- [ ] 暗色模式背景同样有效

### 微交互
- [ ] 按钮点击有涟漪效果
- [ ] 链接 hover 下划线从中心扩展
- [ ] 卡片 hover 抬升流畅
- [ ] 标题 hover 有微妙光晕

### 动效
- [ ] 页面加载有淡入动画
- [ ] 主题切换图标旋转
- [ ] 滚动进度条跟随滚动
- [ ] 侧边栏展开/收起平滑

### 可访问性
- [ ] prefers-reduced-motion 时禁用所有动画
- [ ] 动画不干扰键盘导航
- [ ] 对比度符合 WCAG AA 标准

### 性能
- [ ] 滚动时无卡顿（60fps）
- [ ] 减少不必要的重绘
- [ ] 移动端流畅运行

---

## 实施优先级

### P0（核心体验）
1. 呼吸背景
2. 链接智能下划线
3. 滚动进度指示器
4. 卡片 hover 抬升

### P1（互动增强）
5. 按钮涟漪效果
6. 标题悬停效果
7. 主题切换旋转

### P2（高级效果）
8. 浮动装饰元素
9. 侧边栏平滑展开
10. 代码块打字动效

---

## 测试计划

### 功能测试
- [ ] 所有动画在亮/暗模式正常
- [ ] 移动端动画效果正常
- [ ] reduced-motion 用户无动画
- [ ] 各浏览器兼容（Chrome, Firefox, Safari, Edge）

### 性能测试
- [ ] Lighthouse Performance ≥90
- [ ] 滚动帧率 ≥60fps
- [ ] 无明显内存泄漏

### 可访问性测试
- [ ] 屏幕阅读器可正常导航
- [ ] 键盘用户可操作所有功能
- [ ] WCAG 对比度检查通过
