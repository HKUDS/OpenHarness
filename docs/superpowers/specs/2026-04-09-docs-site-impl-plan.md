# 文档站实现计划

## 任务依赖图

```
[T2] Init Astro project
  └── [T3] Configure content collection
        ├── [T4] Build dynamic route pages/docs/[...slug]
        └── [T7] Build DocLayout + Sidebar + TopNav
              ├── [T10] MermaidBlock island
              └── [T8] ImageGenIsland
        └── [T6] Theme toggle (blocks: T6)

[T4]+[T7]+[T6]+[T10]+[T8] ──→ [T5] GitHub Pages deployment ──→ [T9] Verify
```

## 任务详情

| ID | 任务 | 状态 | 说明 |
|----|------|------|------|
| T2 | Init Astro + Tailwind + React | pending | 初始化项目，安装依赖 |
| T3 | Configure Astro content collection | pending | 映射 docs/**/*.md |
| T4 | Build dynamic docs route | pending | pages/docs/[...slug].astro |
| T7 | DocLayout + Sidebar + TopNav | pending | 布局与导航组件 |
| T10 | MermaidBlock island | pending | Mermaid → SVG 渲染 |
| T8 | ImageGenIsland | pending | AI 图片生成 |
| T6 | Theme toggle | pending | dark/light 模式 |
| T5 | GitHub Pages deployment | pending | CI/CD 自动部署 |
| T9 | Verify all acceptance criteria | pending | 端到端验证 |

## 验收标准

- [ ] `docs/index.md` 在 `/docs/` 正常渲染
- [ ] Mermaid 图表（如 `docs/dev/architecture-overview.md` 中的流程图）正确渲染为 SVG
- [ ] 暗色/亮色主题切换正常
- [ ] 侧边栏导航自动反映 `docs/` 目录结构
- [ ] `ImageGenIsland` 组件能成功生成并显示图片
- [ ] 静态构建产物可部署到 GitHub Pages
- [ ] 无 404 死链，所有内部链接正常跳转
