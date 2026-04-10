# 主题切换功能验收方案

## 背景
主题切换功能包含三种模式：亮色（light）、暗色（dark）、系统（system）。需要确保所有模式都能正确工作。

## 验收环境
- 浏览器：Chrome, Firefox, Safari, Edge（最新版本）
- 系统主题切换：测试 macOS 和 Windows 的系统主题切换响应

## 功能验收标准

### 1. 初始加载

**验收点 1.1 - 页面首次加载**
- [ ] 页面加载时不应出现主题闪烁（FOUC - Flash of Unstyled Content）
- [ ] 默认主题应为 "system"
- [ ] 系统为浅色时，页面应显示浅色主题
- [ ] 系统为深色时，页面应显示深色主题

**验收点 1.2 - localStorage 优先级**
- [ ] 用户之前设置了主题后，刷新页面应保持该主题
- [ ] 清除 localStorage 后，应恢复到 "system" 模式

### 2. 三种主题模式切换

**验收点 2.1 - Light 模式**
- [ ] 点击切换到 Light 模式后，页面立即变为浅色
- [ ] 按钮图标应为太阳图标
- [ ] 按钮 tooltip 显示 "light"
- [ ] localStorage 存储值为 "light"
- [ ] 不会因系统主题变化而改变

**验收点 2.2 - Dark 模式**
- [ ] 点击切换到 Dark 模式后，页面立即变为深色
- [ ] 按钮图标应为月亮图标
- [ ] 按钮 tooltip 显示 "dark"
- [ ] localStorage 存储值为 "dark"
- [ ] 不会因系统主题变化而改变

**验收点 2.3 - System 模式**
- [ ] 点击切换到 System 模式后，页面立即跟随系统主题
- [ ] 按钮图标应为显示器图标
- [ ] 按钮 tooltip 显示 "system"
- [ ] localStorage 存储值为 "system"
- [ ] 当系统主题改变时，页面主题同步改变

### 3. 系统主题变化响应

**验收点 3.1 - System 模式下的响应**
- [ ] 在 System 模式下，手动切换系统主题（浅色→深色或深色→浅色）
- [ ] 页面应立即响应系统主题变化
- [ ] 不需要刷新页面即可看到主题变化

**验收点 3.2 - 非 System 模式下的响应**
- [ ] 在 Light 或 Dark 模式下，手动切换系统主题
- [ ] 页面主题应保持不变（不受系统影响）

### 4. 循环切换顺序

**验收点 4.1 - 切换顺序**
- [ ] 当前为 Light → 点击 → 变为 Dark
- [ ] 当前为 Dark → 点击 → 变为 System
- [ ] 当前为 System → 点击 → 变为 Light
- [ ] 无限循环：Light → Dark → System → Light

**验收点 4.2 - 状态持久化**
- [ ] 切换后刷新页面，主题和按钮状态应保持一致
- [ ] localStorage 存储的值与当前主题正确对应

### 5. 视觉效果

**验收点 5.1 - 颜色正确性**
- [ ] 背景色：
  - Light: `bg-white`
  - Dark: `dark:dark:bg-gray-950`
- [ ] 文本颜色：
  - Light: `text-gray-900`
  - Dark: `dark:text-gray-100`
- [ ] 导航栏颜色：
  - Light: `bg-white/80 border-gray-200`
  - Dark: `dark:bg-gray-900/80 dark:border-gray-800`

**验收点 5.2 - 所有组件响应**
- [ ] 侧边栏正确响应主题
- [ ] 代码块正确响应主题
- [ ] 链接文字正确响应主题
- [ ] 所有使用 `dark:` 前缀的 Tailwind 类都生效

### 6. 辅助功能

**验收点 6.1 - 键盘导航**
- [ ] Tab 键可以聚焦到主题切换按钮
- [ ] Enter/Space 键可以触发主题切换
- [ ] 屏幕阅读器正确读取按钮的 aria-label

**验收点 6.2 - 焦点状态**
- [ ] 按钮获得焦点时有明显的焦点指示器
- [ ] 点击后焦点保持在按钮上

### 7. 性能

**验收点 7.1 - 渲染性能**
- [ ] 主题切换不应导致页面重绘卡顿
- [ ] CSS transition 200ms 应流畅无卡顿

**验收点 7.2 - 脚本执行**
- [ ] 阻塞渲染的 inline script 执行时间 < 5ms
- [ ] 不影响页面 First Contentful Paint (FCP)

## 浏览器兼容性验收

| 浏览器 | 版本 | 通过/失败 |
|--------|------|-----------|
| Chrome | 最新 2 个版本 | |
| Firefox | 最新 2 个版本 | |
| Safari | 最新 2 个版本 | |
| Edge | 最新 2 个版本 | |

## 已知问题与改进点

### 当前实现潜在问题

1. **FOUC（闪烁）问题**
   - 问题：inline script 在页面加载时立即执行，但可能在 DOM 头部样式之前
   - 验收：检查是否有明显的主题"闪烁"

2. **System 模式初始化**
   - 问题：`initTheme()` 在按钮 DOM 查询之前执行
   - 验收：确保按钮初始状态正确

3. **事件监听器重复绑定**
   - 问题：在某些 SPA 场景下可能重复绑定事件
   - 验收：需要测试多页面导航场景

## 验收步骤

### 手动测试步骤

1. **测试初始加载**
   ```
   1. 打开浏览器控制台 > Application > Local Storage
   2. 清除所有 Local Storage 数据
   3. 刷新页面
   4. 观察页面初始主题是否与系统一致
   5. 检查 localStorage.getItem('theme') 是否为 'null' 或 'system'
   ```

2. **测试主题切换**
   ```
   1. 连续点击主题切换按钮 6 次（完成两个完整循环）
   2. 记录每次点击后的：
      - 按钮图标
      - 页面主题
      - localStorage 值
   3. 验证顺序正确：Light → Dark → System → Light
   ```

3. **测试 System 模式响应**
   ```
   1. 将主题切换到 System 模式
   2. 打开系统设置的显示/外观设置
   3. 切换系统的浅色/深色主题
   4. 返回浏览器，主题应立即改变
   ```

4. **测试跨浏览器刷新**
   ```
   1. 在浏览器 A 中设置为 Dark 模式
   2. 在浏览器 B 中打开同一页面
   3. 验证主题是否独立（localStorage 是浏览器级别的）
   ```

### 自动化测试建议

```javascript
// E2E 测试伪代码
describe('主题切换功能', () => {
  test('默认为 system 模式', async () => {
    await page.goto('/docs/');
    const theme = localStorage.getItem('theme');
    expect(theme).toBe('system');
  });

  test('切换循环正确', async () => {
    await page.click('#theme-toggle-btn');
    let ariaLabel = await page.getAttribute('#theme-toggle-btn', 'aria-label');
    expect(ariaLabel).toContain('dark');

    await page.click('#theme-toggle-btn');
    ariaLabel = await page.getAttribute('#theme-toggle-btn', 'aria-label');
    expect(ariaLabel).toContain('system');
  });
});
```

## 完成标准

所有验收点必须通过，测试结果填写完整，无阻塞性问题。

## 签字确认

- 功能验收：___________ 日期：___________
- 测试验收：___________ 日期：___________
