# OpenHarness 文档站设计规格

## 1. 概述与目标

**项目**：将 `docs/` 下的 Markdown 文档转换为静态前端网页，支持 Mermaid 图表渲染和 AI 图片生成。

**核心目标**：
- 文档完全静态托管（GitHub Pages / Vercel / Cloudflare Pages）
- 渲染 Markdown，支持 Mermaid 图表代码块
- 支持 AI 生成文档配图（封面、文中插图）
- 响应式布局，导航友好

---

## 2. 技术选型

### 方案：C (推荐) — Astro + React 岛屿

| 组件 | 选择 | 理由 |
|------|------|------|
| 静态框架 | **Astro 4.x** | 内容集合原生支持 Markdown，性能最优 |
| 交互组件 | **React 18** | 通过 Astro 岛屿嵌入，不影响静态性能 |
| 图表渲染 | **mermaid** | 解析 Mermaid 代码块，渲染为 SVG |
| AI 图片 | **React 图片生成岛屿** | 调用 OpenHarness 的 LLM API 生成配图 |
| 样式 | **Tailwind CSS** | 快速开发，响应式，无需构建复杂设计系统 |
| 部署 | **静态导出** (`output: 'static'`) | 无需服务端，天然兼容 GitHub Pages |

**替代方案 A (Vite + React)**：更轻量，但 Markdown 路由需自己实现，适合简单场景。
**替代方案 B (Next.js)**：生态完整，但静态导出配置复杂，首屏性能劣于 Astro。

---

## 3. 站点结构

```
docs-site/                          # 新建前端项目
├── public/                         # 静态资源
├── src/
│   ├── components/
│   │   ├── MermaidBlock.tsx       # React 岛屿：渲染 Mermaid
│   │   ├── ImageGenIsland.tsx     # React 岛屿：AI 生成图片
│   │   ├── DocLayout.astro        # 文档页面布局
│   │   ├── Sidebar.astro          # 侧边导航
│   │   ├── TopNav.astro           # 顶部导航
│   │   └── ThemeToggle.astro      # 主题切换
│   ├── content/
│   │   └── docs/                  # Astro 内容集合（映射 docs/）
│   ├── pages/
│   │   └── docs/[...slug].astro   # 动态文档路由
│   └── styles/
│       └── global.css
├── astro.config.mjs
├── tailwind.config.mjs
└── package.json
```

**内容映射策略**：Astro 内容集合直接读取项目根目录的 `docs/` 文件夹，通过 glob 模式 `docs/**/*.md` 匹配，无需复制文件。

---

## 4. 功能规格

### 4.1 Markdown 渲染
- 使用 `@astrojs/mdx` 或 Astro 原生 Markdown 支持
- 支持 GFM (表格、任务列表、代码高亮)
- 代码高亮：`shiki` 主题（与编辑器风格统一）
- Mermaid 代码块自动识别，渲染为 SVG

### 4.2 Mermaid 图表渲染
- 识别 ` ```mermaid ` 代码块
- 使用 `mermaid` npm 包将图表定义渲染为 SVG
- React 岛屿组件 `<MermaidBlock definition="..." />` 包装
- 支持暗色/亮色主题切换（Mermaid 图表跟随站点主题）

### 4.3 AI 图片生成
- 每个文档页面顶部可选 AI 封面图
- 文档中可插入 `<ImageGenIsland prompt="..." />` 岛屿组件
- 调用 OpenHarness 的 API（或配置外部 LLM API key）生成图片
- 图片存储在 `public/generated/` 目录，提交到 Git
- 支持配置项：
  - `OPENHARNESS_API_URL`：API 端点
  - `IMAGE_GEN_PROVIDER`：`openai` / `anthropic` / `oharness`

### 4.4 导航与侧边栏
- 侧边栏按 `docs/` 目录结构自动生成（`user/` / `dev/` / `dev/core/` 等）
- 当前页面高亮
- 顶部面包屑导航
- 上一页 / 下一页自动推断

### 4.5 主题支持
- 亮色 / 暗色主题切换
- Mermaid 图表同步主题切换
- 使用 CSS 变量 + Tailwind `dark:` 变体

### 4.6 搜索（可选，后续实现）
- 使用 Pagefind 静态搜索（无后端依赖）

---

## 5. 文档路由设计

| 文档路径 | 访问 URL |
|----------|----------|
| `docs/index.md` | `/docs/` |
| `docs/user/getting-started.md` | `/docs/user/getting-started/` |
| `docs/dev/core/agent-loop.md` | `/docs/dev/core/agent-loop/` |
| `docs/SHOWCASE.md` | `/docs/showcase/` |

---

## 6. 组件详细设计

### MermaidBlock（React 岛屿）
```
Props:
  - definition: string  // mermaid 图表定义代码
  - className?: string

行为：
  - 客户端渲染（useEffect + mermaid.run()）
  - 渲染前显示加载占位符
  - 错误时显示原始代码块
```

### ImageGenIsland（React 岛屿）
```
Props:
  - prompt: string      // 图片生成提示词
  - alt?: string         // alt 文本
  - apiUrl?: string      // 覆盖默认 API
  - cacheKey?: string    // 缓存键，避免重复生成

行为：
  - 首次渲染时调用 LLM API 生成图片
  - 缓存结果到 localStorage + public 目录
  - 加载中显示骨架屏
  - 支持重新生成按钮
```

### DocLayout（ Astro 布局）
```
Props:
  - frontmatter: { title, description, section }

包含：
  - <TopNav />
  - <Sidebar currentPath={...} />
  - <article> { children } </article>
  - 注入 <MermaidBlock> 处理器到全局
```

---

## 7. 部署方案

- **构建**：`astro build`（静态输出到 `dist/`）
- **托管**：GitHub Pages（GitHub Actions 自动部署）
- **域名**：可配置 `SITE_URL`
- **CI 流程**：push 到 main → 触发 GitHub Actions → 构建 → 部署

---

## 8. 实现步骤（初步）

1. 初始化 Astro 项目 + Tailwind + React 集成
2. 配置 Astro 内容集合，glob 映射 `docs/**/*.md`
3. 实现 DocLayout + Sidebar + TopNav
4. 集成 Mermaid 渲染（mermaid 包 + React 岛屿）
5. 实现 AI 图片生成岛屿组件
6. 主题切换功能
7. 部署到 GitHub Pages
8. 添加 Pagefind 搜索（可选）

---

## 9. 验收标准

- [ ] `docs/index.md` 在 `/docs/` 正常渲染
- [ ] Mermaid 图表（如 `docs/dev/architecture-overview.md` 中的流程图）正确渲染为 SVG
- [ ] 暗色/亮色主题切换正常
- [ ] 侧边栏导航自动反映 `docs/` 目录结构
- [ ] `ImageGenIsland` 组件能成功生成并显示图片
- [ ] 静态构建产物可部署到 GitHub Pages
- [ ] 无 404 死链，所有内部链接正常跳转
