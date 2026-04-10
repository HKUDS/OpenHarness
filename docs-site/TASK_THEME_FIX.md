# 主题切换功能修复任务

## 任务概述
修复主题切换（Light/Dark/System）功能的多个问题，确保符合验收标准。

## 现有问题分析

### 问题 1: DOM 元素未准备好时初始化
**位置**: `DocLayout.astro:118`
```javascript
initTheme();  // 在 <head> 的 inline script 中调用
```
**问题**: 此时 `<body>` 中的按钮元素还不存在，`updateThemeButton()` 无法正确更新按钮状态。

### 问题 2: 系统主题变化监听逻辑错误
**位置**: `DocLayout.astro:118-126`
```javascript
if (themes[themeIndex] === 'system' || !localStorage.getItem('theme')) {
  applyTheme('system');
}
```
**问题**: 当用户设置为 light/dark 模式时，`localStorage.getItem('theme')` 存在值，这个逻辑是正确的。但 `initTheme()` 可能会导致 `themeIndex` 与实际存储值不一致。

### 问题 3: `initTheme()` 调用位置不当
`initTheme()` 在 inline script 的末尾被调用，但此时按钮 DOM 元素还未渲染。应该延迟到 DOMContentLoaded 后调用。

### 问题 4: FOUC（闪烁）风险
虽然使用了立即执行的脚本来设置 `dark` class，但后续 `initTheme()` 可能覆盖这个状态。

## 开发任务

### Task 1: 重构主题初始化逻辑

**文件**: `docs-site/src/layouts/DocLayout.astro`

**问题**:
1. `initTheme()` 在 DOM 准备好之前被调用
2. 按钮状态没有正确初始化

**解决方案**:
1. 将核心主题设置逻辑（设置 dark class）保留在 inline script 中（防止 FOUC）
2. 将按钮初始化逻辑移到 DOMContentLoaded 事件处理
3. 确保 `themeIndex` 与 localStorage 值保持一致

**修改点**:
```javascript
// 在 <head> 的 inline script 中：
// 1. 保留立即执行的主题 class 设置
// 2. 移除 initTheme() 调用
// 3. 将 initTheme 包装在 DOMContentLoaded 事件中

window.addEventListener('DOMContentLoaded', function() {
  initTheme();
  // 初始化按钮
  var button = document.getElementById('theme-toggle-btn');
  if (button) {
    button.addEventListener('click', cycleTheme);
  }
});
```

### Task 2: 修复系统主题响应逻辑

**文件**: `docs-site/src/layouts/DocLayout.astro`

**问题**: 系统主题变化时，响应逻辑可能有边界情况未覆盖

**解决方案**:
明确只在当前模式为 'system' 时才响应系统变化
```javascript
var systemHandler = function() {
  var currentTheme = themes[themeIndex];
  if (currentTheme === 'system') {
    applyTheme('system');
  }
};
```

### Task 3: 改进图标更新逻辑

**文件**: `docs-site/src/layouts/DocLayout.astro`

**问题**: `updateThemeButton()` 在按钮不存在时提前返回，这在初始化阶段是预期的，但需要在按钮存在后重新调用

**解决方案**:
在 DOMContentLoaded 后立即调用一次 `updateThemeButton()` 确保按钮状态正确

### Task 4: 添加调试日志（可选）

**文件**: `docs-site/src/layouts/DocLayout.astro`

**用途**: 帮助排查问题
```javascript
console.log('[Theme] Initial theme:', localStorage.getItem('theme') || 'null');
console.log('[Theme] System dark:', window.matchMedia('(prefers-color-scheme: dark)').matches);
console.log('[Theme] Current theme index:', themeIndex);
```

## 实施步骤

1. **备份当前实现**
   ```bash
   git checkout -b fix/theme-switching
   ```

2. **修改 DocLayout.astro**
   - 重构 inline script 的初始化逻辑
   - 修复系统主题响应
   - 添加调试日志

3. **本地测试**
   - 清除 localStorage 测试初始加载
   - 测试三种模式切换
   - 测试系统主题变化响应
   - 测试跨页面导航

4. **修复发现的问题**
   - 根据测试结果调整实现

5. **代码审查**
   - 提交 PR
   - 等待代码审查

6. **验收测试**
   - 按照 `ACCEPTANCE_THEME_SWITCHING.md` 进行验收
   - 修复验收中发现的问题

7. **合并到主分支**

## 测试检查清单

在开发过程中，每完成一个 Task 需要验证：

- [ ] 初始加载无 FOUC
- [ ] 默认为 system 模式
- [ ] Light/Dark/System 三种模式正确切换
- [ ] 按钮图标正确显示
- [ ] localStorage 正确保存和读取
- [ ] 系统主题变化在 system 模式下正确响应
- [ ] 系统主题变化在非 system 模式下不响应
- [ ] 刷新页面后主题保持不变

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 改动较大导致回归 | 高 | 充分测试，逐步提交 |
| 浏览器兼容性问题 | 中 | 测试主流浏览器 |
| 初始化时机问题 | 中 | 确保 DOMContentLoaded 后再操作按钮 |

## 完成

- [ ] 所有任务完成
- [ ] 所有测试通过
- [ ] 代码审查通过
- [ ] 验收测试通过
