# UI 渐变多彩化设计方案

> **项目:** OpenHarness 文档网站
> **日期:** 2026-04-12
> **状态:** 设计中

---

## 设计目标

将文档网站从"朴实无华"的极简风格升级为"现代多彩"风格，增加视觉吸引力，同时保持专业性和可读性。

---

## 视觉风格

### 配色方案（科技蓝紫渐变）

| 用途 | 亮色 | 暗色 |
|------|-------|-------|
| 主背景渐变 | `#F8FAFC` → `#EEF2FF` (上到下) | `#0F172A` → `#1E1B4B` (上到下) |
| 文本 | `#1E293B` | `#F1F5F9` |
| 主品牌渐变 | `#3B82F6` → `#8B5CF6` → `#EC4899` | `#60A5FA` → `#A78BFA` → `#F472B6` |
| 次要渐变（装饰） | `#6366F1` → `#8B5CF6` | `#818CF8` → `#C084FC` |
| 卡片背景 | 白色 + 渐变边框 | 深色半透明 + 渐变边框 |
| 代码块渐变 | `#F1F5F9` → `#E0E7FF` | `#1E293B` → `#312E81` |

### 字体

保持现有字体：
- 标题：JetBrains Mono
- 正文：IBM Plex Sans

### CSS 变量体系

```css
:root {
  /* 基础颜色 */
  --color-bg-start: #F8FAFC;
  --color-bg-end: #EEF2FF;
  --color-text: #1E293B;
  --color-secondary: #64748B;
  --color-sidebar-bg: #F1F5F9;
  --color-border: #E2E8F0;

  /* 渐变定义 */
  --gradient-primary: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 50%, #EC4899 100%);
  --gradient-secondary: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%);
  --gradient-code: linear-gradient(180deg, #F1F5F9 0%, #E0E7FF 100%);
  --gradient-border: linear-gradient(90deg, #3B82F6, #8B5CF6, #EC4899);

  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
  --shadow-glow: 0 0 20px rgba(59, 130, 246, 0.3);

  /* 动效曲线 */
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --ease-smooth: cubic-bezier(0.4, 0, 0.2, 1);
}

.dark {
  --color-bg-start: #0F172A;
  --color-bg-end: #1E1B4B;
  --color-text: #F1F5F9;
  --color-secondary: #94A3B8;
  --color-sidebar-bg: #1E293B;
  --color-border: #334155;

  --gradient-primary: linear-gradient(135deg, #60A5FA 0%, #A78BFA 50%, #F472B6 100%);
  --gradient-secondary: linear-gradient(135deg, #818CF8 0%, #C084FC 100%);
  --gradient-code: linear-gradient(180deg, #1E293B 0%, #312E81 100%);
  --gradient-border: linear-gradient(90deg, #60A5FA, #A78BFA, #F472B6);

  --shadow-glow: 0 0 20px rgba(96, 165, 250, 0.3);
}
```

---

## 组件设计

### 导航栏 (TopNav.astro)

**样式：**
- 浮动式圆角卡片：`top-4 left-4 right-4 h-14`
- 背景：毛玻璃效果 `bg-[var(--color-bg-start)]/95 backdrop-blur-md`
- 底部边框：渐变 `border-b-2 border-transparent bg-clip-text` 使用 `background: var(--gradient-border)`
- Logo 容器：渐变背景，白色文字
- 主题切换按钮：hover 时显示渐变边框

**交互：**
- 页面加载时 `fade-in-down` 300ms
- 链接 hover：颜色过渡 200ms，下划线从 0-50% 扩展到 0-100%

### 侧边栏 (Sidebar.astro)

**样式：**
- 背景：微妙渐变 `background: linear-gradient(180deg, var(--color-sidebar-bg) 0%, var(--color-sidebar-bg-dim) 100%)`
- 激活链接：渐变背景 `background: var(--gradient-primary)`，白色文字
- 分区标题：渐变文字 `background: var(--gradient-secondary); -webkit-background-clip: text; color: transparent`
- 折叠图标：使用渐变色填充

**交互：**
- 页面加载时 `slide-in-left` 400ms
- 链接 hover：transform translateX(4px) 200ms
- 折叠面板：height 动画 300ms 使用 `--ease-smooth`

### `主内容区域` (DocLayout + prose)

**样式：**
- 页面标题：渐变文字效果（如侧边栏分区标题）
- 链接：使用主渐变色 `color`（而非纯蓝）
- 按钮（如代码复制）：渐变背景
- 卡片/警告框：渐变边框

**代码块：**
- 背景：渐变 `background: var(--gradient-code)`
- 顶部装饰条：渐变（4px 高）
- 复制按钮：hover 时显示渐变边框

---

## 动效规范

### 页面加载动画

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

**应用：**
- 导航栏：`.animate-fade-in-down` 300ms
- 主内容：`.animate-fade-in-up` 600ms
- 侧边栏：`.animate-slide-in-left` 400ms
- 子元素交错延迟：`style="animation-delay: ${index * 50}ms"`

### 交互动效

| 元素 | 效果 | 持续时间 |
|------|-------|-----------|
| 链接 hover | 颜色过渡 + 下划线扩展 | 200ms |
| 按钮 hover | translateY(-2px) + 阴影增强 | 200ms |
| 卡片/区块 hover | 边框渐变流动 + 阴影 | 250ms |
| 主题切换 | 图标旋转 + 颜色渐变 | 300ms |

### 滚动效果

- 导航栏滚动时：背景透明度从 95% → 100%
- 标题（可选）：滚动视差效果（滚动时轻微位移）

---

## 文件修改清单

1. `src/styles/global.css`
   - 添加渐变 CSS 变量
   - 定义动画关键帧
   - 更新基础颜色

2. `src/components/TopNav.astro`
   - 应用渐变边框到导航栏
   - Logo 容器使用渐变
   - 添加加载动画

3. `src/components/Sidebar.astro`
   - 应用渐变背景
   - 激活链接使用渐变背景
   - 分区标题使用渐变文字
   - 添加加载动画

4. `src/layouts/DocLayout.astro`
   - 主内容区域背景使用渐变
   - 添加加载动画

5. `src/pages/docs/[...slug].astro`
   - prose 样式更新（链接颜色渐变）
   - 代码块渐变样式

---

## 可访问性考虑

- 渐变效果必须保持足够的文本对比度（4.5:1 最小）
- 所有动画必须尊重 `prefers-reduced-motion`
- focus 状态保持可见
- 键盘导航不受影响

---

## 性能考虑

- 渐变使用 CSS 变量，避免重复计算
- 动画使用 `transform` 和 `opacity`，避免触发布局重排
- 页面加载动画使用交错延迟，避免同时渲染过多元素

---

## 验收标准

- [ ] 导航栏有渐变边框效果
- [ ] Logo 容器使用渐变背景
- [ ] 侧边栏背景有微妙渐变
- [ ] 激活链接使用渐变背景
- [ ] 分区标题使用渐变文字
- [ ] 链接 hover 有下划线动画
- [ ] 页面加载有入场动画
- [ ] 亮/暗模式都有渐变效果
- [ ] 文本对比度符合 WCAG AA 标准
- [ ] 动画流畅不卡顿
- [ ] 减少 motion 用户没有动画
