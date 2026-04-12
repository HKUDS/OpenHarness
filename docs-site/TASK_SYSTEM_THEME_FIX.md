# 系统主题跟随修复 - 开发任务

## 任务概述

修复 `systemHandler` 闭包导致的系统主题跟随失效问题。当前 `systemHandler` 函数在创建时捕获了 `themeIndex` 的初始值，导致后续 `initTheme()` 更新 `themeIndex` 后，`systemHandler` 仍使用旧值判断是否应该响应系统主题变化。

## 根本原因

```javascript
// 问题代码
var themeIndex = 2;  // 初始值

var systemHandler = function() {
  var currentTheme = themes[themeIndex];  // 闭包捕获 themeIndex=2
  if (currentTheme === 'system') {
    applyTheme('system');
  }
};
// 即使后面 initTheme() 更新了 themeIndex，systemHandler 仍看的是初始值
```

## 修复方案

采用对象包装的方式，确保所有函数引用同一状态对象：

```javascript
var themeState = {
  themes: ['light', 'dark', 'system'],
  index: 2
};

var systemHandler = function() {
  var currentTheme = themeState.themes[themeState.index];
  if (currentTheme === 'system') {
    applyTheme('system');
  }
};

// initTheme 中更新
themeState.index = stored ? themeState.themes.indexOf(stored) : 2;
```

## 具体任务

### Task 1: 重构状态管理
**文件**: `docs-site/src/layouts/DocLayout.astro`

将分散的 `themes` 数组和 `themeIndex` 变量整合到 `themeState` 对象中。

**修改清单**:
- [ ] 声明 `themeState` 对象
- [ ] 将 `themes` 改为 `themeState.themes`
- [ ] 将 `themeIndex` 改为 `themeState.index`
- [ ] 更新所有引用这两变量的代码

### Task 2: 修复函数引用
**文件**: `docs-site/src/layouts/DocLayout.astro`

更新以下函数以使用新的状态对象：

```javascript
// getSystemTheme - 无需修改
function getSystemTheme() { ... }

// applyTheme - 需要修改
function applyTheme(currentTheme) {
  var effective = currentTheme === 'system' ? getSystemTheme() : currentTheme;
  document.documentElement.classList.toggle('dark', effective === 'dark');
  localStorage.setItem('theme', currentTheme);
  updateThemeButton(currentTheme);
}

// updateThemeButton - 无需修改
function updateThemeButton(currentTheme) { ... }

// cycleTheme - 需要修改
function cycleTheme() {
  themeState.index = (themeState.index + 1) % themeState.themes.length;
  var nextTheme = themeState.themes[themeState.index];
  applyTheme(nextTheme);
}

// initTheme - 需要修改
function initTheme() {
  var stored = localStorage.getItem('theme');
  if (stored && themeState.themes.includes(stored)) {
    themeState.index = themeState.themes.indexOf(stored);
  } else {
    themeState.index = 2; // Default to 'system'
  }
  applyTheme(themeState.themes[themeState.index]);
}

// systemHandler - 需要修改（关键修复）
var systemHandler = function() {
  var currentTheme = themeState.themes[themeState.index];
  if (currentTheme === 'system') {
    applyTheme('system');
  }
};
```

### Task 3: 添加调试日志
**文件**: `docs-site/src/layouts/DocLayout.astro`

在关键位置添加调试日志，便于后续排查：

```javascript
function applyTheme(currentTheme) {
  var effective = currentTheme === 'system' ? getSystemTheme() : currentTheme;
  document.documentElement.classList.toggle('dark', effective === 'dark');
  localStorage.setItem('theme', currentTheme);
  updateThemeButton(currentTheme);
  console.log('[Theme] Applied:', currentTheme, 'Effective:', effective);
}

var systemHandler = function() {
  var currentTheme = themeState.themes[themeState.index];
  console.log('[Theme] System theme changed. Current mode:', currentTheme, 'Will respond:', currentTheme === 'system');
  if (currentTheme === 'system') {
    applyTheme('system');
  }
};
```

### Task 4: 更新测试页面
**文件**: `docs-site/test-theme.html`

同步修改测试页面的主题逻辑。

## 验证清单

完成所有任务后，按照以下顺序验证：

### 基础功能
- [ ] 页面加载，默认为 system 模式
- [ ] 点击主题按钮：Light → Dark → System → Light 循环正确
- [ ] 按钮图标正确显示（☀️/🌙/💻）
- [ ] localStorage 正确保存和读取
- [ ] 刷新页面后主题保持不变

### 系统主题跟随
- [ ] 在 System 模式下，切换系统主题，页面立即响应
- [ ] 在 Light 模式下，切换系统主题，页面**不**响应
- [ ] 在 Dark 模式下，切换系统主题，页面**不**响应
- [ ] 控制台日志显示正确的主题状态

### 边界情况
- [ ] 页面刷新后，系统主题响应仍然正确
- [ ] 快速连续点击主题按钮，无异常
- [ ] 清除 localStorage 后，恢复为 system 模式

## 预期结果

修复前：
```
User action: Switch to Light mode
Current state: themeIndex = 0, themes[0] = 'light'

User action: Switch system theme (light -> dark)
Result: Page theme changes! (BUG - Should not respond)
System handler sees: themes[2] = 'system' (OLD INDEX!)
```

修复后：
```
User action: Switch to Light mode
Current state: themeState.index = 0, themeState.themes[0] = 'light'

User action: Switch system theme (light -> dark)
Result: Page theme does NOT change (CORRECT)
System handler sees: themeState.themes[0] = 'light' (CURRENT INDEX!)
```

## 回归测试

确保以下功能不受影响：
- [ ] 侧边栏折叠/展开
- [ ] 移动端侧边栏
- [ ] 侧边栏分栏展开/折叠
- [ ] Mermaid 图表渲染
- [ ] 文档链接跳转

## 提交说明

```
fix: resolve system theme handler closure issue

Wrap theme state in object to ensure systemHandler
always reads current value, not captured initial value.

- Create themeState object containing themes and index
- Update all references to use themeState
- Add debug logging for theme changes
- Fix systemHandler to correctly check current mode

This fixes the bug where system theme changes would
incorrectly trigger even when not in 'system' mode
after manually switching themes.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

## 完成

- [ ] 所有代码修改完成
- [ ] 本地测试通过
- [ ] 验收标准满足
- [ ] 代码审查通过（如需）
- [ ] 合并到主分支
