# docs-site 验收方案与任务文档 - 迭代 2

## 问题诊断

### 当前状态
1. **主题切换** - React island 渲染但 `onClick` 循环未生效，按钮 aria-label 不随模式变化更新
2. **侧边栏折叠** - 存在但视觉效果不明显，`width: 0` 动画有延迟
3. **首页链接** - remark 插件已添加，但首页 (`docs/index.md`) 渲染后链接可能仍有问题

### 根因分析
1. **React island 水合问题**: Astro 的 React island 将组件打包为独立模块，`onClick` 事件可能被丢失或未正确绑定
2. **ThemeToggle 组件复杂化**: 使用 `useState` + `useEffect` 的方式在 Astro island 中可能不完全可靠
3. **侧边栏宽度过渡**: 仅用 `style.width = '0px'` 在 transition 中可能不是最佳实践

## 2. 改进方案

### 2.1 简化主题切换

**方案**: 放弃 React island，使用纯 JS inline script 控制主题切换

```javascript
// 直接在 DocLayout.astro 的 script 中处理，不依赖 React island
// 优点： guaranteed 执行，无 hydration 不确定性
```

**验收条件**:
- 页面加载后直接应用主题
- 点击按钮循环切换 light/dark/system
- 按钮显示当前模式
- aria-label 实时更新
- localStorage 持久化
- 切换时 mermaid 重新渲染

### 2.2 增强侧边栏折叠效果

**方案**:
1. 添加明显的"完全折叠"视觉反馈
2. 折叠时侧边栏宽度平滑过渡到 `0`
3. 主内容区同步扩展

**验收条件**:
- 折叠时：side width → 0, padding → 0, overflow → hidden
- 展开时：side width → 16rem, padding/padding → 原值
- 主内容区：ml-0 <→> ml-64
- 过渡动画流畅（300ms）
- 图标清晰指示当前状态

### 2.3 修复首页链接

**方案**: remark 插件已存在，验证在构建后是否正确重写链接

**验收条件**:
- 首页 article 内所有链接为 `/docs/{slug}/` 格式
- 无 `.md` 后缀链接
- 点击后导航到正确页面

## 3. 开发任务清单

### Task 1: 重写主题切换为纯 JS

**文件**: `DocLayout.astro`

**步骤**:
1. 移除 React ThemeToggle island
2. 在 DocLayout 头部添加简单 `<button id="theme-toggle-btn">`
3. 在 script 中直接监听按钮点击，循环切换主题
4. 确保 aria-label 和 title 实时更新
5. 同步更新 mermaid 图表

**验证点**:
- [ ] 点击按钮后 aria-label 变为 "Theme: light/dark/system"
- [ ] 按钮图标随模式变化
- [ ] localStorage 正确保存和读取
- [ ] 系统模式响应 `prefers-color-scheme` 变化

### Task 2: 增强侧边栏折叠效果

**文件**: `DocLayout.astro` (script + Sidebar.astro)

**步骤**:
1. Sidebar 添加更明显的折叠指示器（背景色变化 + 文字提示）
2. 优化 width 过渡（transition-all 300ms ease-in-out）
3. 折叠时设置 border-right-width: 0
4. 添加 aria-expanded 属性到按钮
5. 确保 mobile/desktop 行为一致

**验证点**:
- [ ] 折叠时侧边栏完全隐藏（width 0）
- [ ] 过渡动画平滑
- [ ] 主内容区占满
- [ ] 无视觉残留（border/overflow）
- [ ] 图标清晰指示当前折叠状态

### Task 3: 验证 remark 插件工作

**文件**: 验证构建输出

**步骤**:
1. 构建项目
2. 检查首页 HTML 中所有链接格式
3. 测试点击链接后的导航
4. 着眠/重新构建验证

**验证点**:
- [ ] 无 `.md` 后缀链接
- [ ] 所有链接以 `/docs/` 开头
- [ ] 点击后正确跳转

### Task 4: 本地测试完整功能

**步骤**:
1. 启动 dev server `npx astro dev`
2. 打开浏览器检查各项功能
3. 手动触发主题切换并验证
4. 手动触发侧边栏折叠并验证
5. 在首页测试各个链接
6. 在含 mermaid 的页面验证渲染

## 4. 验收检查清单

```
主题切换
□ 点击按钮循环切换
□ 亮：白色背景 + 太阳图标
□ 暗：深色背景 + 月亮图标
□ 系统：显示器图标 + 跟随系统
□ aria-label 实时显示 "Theme: X"
□ 刷新页面后主题不变

侧边栏折叠
□ 点击桌面折叠按钮侧边栏滑出
□ 点击移动汉堡菜单侧边栏滑出
□ 折叠后主内容区占满宽度
□ 过渡动画流畅
□ 图标切换（展开/收起）
□ localStorage 持久化
□ 各分组可独立折叠

首页链接
□ 用户手册 → /docs/user/getting-started/
□ 开发者文档 → /docs/dev/architecture-overview/
□ 核心模块正确嵌套显示
□ 无 .md 后缀链接残留
□ 点击后正确导航

Mermaid 渲染
□ flowchart/graph 代码块渲染为 SVG
□ 亮色主题用 default
□ 暗色主题用 dark
□ 切换主题图表重新渲染
```

全部通过后才算 **完全完成**。
