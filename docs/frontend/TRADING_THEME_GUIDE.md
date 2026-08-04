# 同花顺风格交易主题指南

> 📊 黑色交易风格主题配置说明

## 🎨 设计理念

本主题参考同花顺等专业交易软件的视觉风格，采用：
- **黑色主背景**：减少视觉疲劳，适合长时间使用
- **绿涨红跌**：符合中国股市习惯的配色方案
- **高对比度**：确保数据清晰可读
- **专业感**：体现金融交易软件的严谨性

## 🎨 配色方案

### 背景色
```scss
$bg-primary: #000000;      // 主背景（纯黑）
$bg-secondary: #1a1a1a;    // 次要背景（深灰）
$bg-tertiary: #2a2a2a;     // 第三级背景（中灰）
$bg-card: #1e1e1e;         // 卡片背景
```

### 文字色
```scss
$text-primary: #ffffff;     // 主文字（白色）
$text-secondary: #b0b0b0;  // 次要文字（浅灰）
$text-tertiary: #808080;   // 第三级文字（中灰）
```

### 功能色
```scss
$primary-color: #1E88E5;   // 主色（深蓝色）
$success-color: #00C853;   // 上涨绿色（同花顺风格）
$danger-color: #F44336;    // 下跌红色（同花顺风格）
$warning-color: #FFA726;   // 警告（橙色）
$info-color: #78909C;      // 信息（灰蓝色）
```

### 边框色
```scss
$border-color: #333333;     // 边框色（深灰）
$border-color-light: #404040; // 浅边框
```

## 📁 文件结构

### 核心样式文件
```
frontend/src/styles/
├── variables.scss          # 颜色变量定义（已更新）
├── index.scss              # 全局样式（已更新）
├── dark-theme.scss         # Element Plus 暗色主题
└── trading-theme.scss      # 交易风格主题（新增）
```

### 修改的页面组件
- `frontend/src/App.vue` - 主应用容器
- `frontend/src/layouts/BasicLayout.vue` - 布局组件
- `frontend/src/views/Dashboard/index.vue` - 仪表板
- `frontend/src/views/About/index.vue` - 关于页面
- `frontend/src/main.ts` - 入口文件（导入主题）

## 🔧 使用方法

### 1. 默认启用暗色主题

主题已设置为默认暗色模式：
```typescript
// frontend/src/stores/app.ts
theme: (useStorage('app-theme', 'dark').value || 'dark')
```

### 2. 应用交易风格

交易风格主题已自动导入：
```typescript
// frontend/src/main.ts
import './styles/trading-theme.scss'
```

### 3. 使用工具类

在组件中使用交易风格工具类：

```vue
<template>
  <!-- 上涨绿色 -->
  <span class="text-up">+5.23%</span>
  
  <!-- 下跌红色 -->
  <span class="text-down">-3.45%</span>
  
  <!-- 背景色 -->
  <div class="bg-card">卡片内容</div>
</template>
```

## 🎯 关键特性

### 1. 绿涨红跌配色

在表格和数据显示中：
- **上涨**：使用 `$success-color` (#00C853) - 绿色
- **下跌**：使用 `$danger-color` (#F44336) - 红色
- **平盘**：使用 `$text-secondary` (#b0b0b0) - 灰色

### 2. 高对比度设计

- 白色文字在黑色背景上，确保清晰可读
- 边框使用深灰色，不会过于突兀
- 卡片背景使用深灰色，与主背景区分

### 3. 专业交易界面

- 去除花哨的渐变，使用简洁的纯色
- 减少圆角，使用更小的圆角值（4px-8px）
- 统一的间距和布局规范

## 📊 组件样式

### 卡片组件
```scss
.el-card {
  background-color: #1e1e1e;
  border-color: #333333;
  border-radius: 8px;
}
```

### 按钮组件
- **主要按钮**：深蓝色 (#1E88E5)
- **成功按钮**：上涨绿色 (#00C853)
- **危险按钮**：下跌红色 (#F44336)
- **默认按钮**：深灰色背景

### 表格组件
```scss
.el-table {
  background-color: #1e1e1e;
  
  th {
    background-color: #1a1a1a;
  }
  
  tr:hover > td {
    background-color: #2a2a2a;
  }
}
```

### 输入框组件
```scss
.el-input__wrapper {
  background-color: #2a2a2a;
  border-color: #333333;
}
```

## 🎨 自定义样式

### 在组件中使用 SCSS 变量

```vue
<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.my-component {
  background-color: $bg-card;
  color: $text-primary;
  border: 1px solid $border-color;
  
  .price-up {
    color: $success-color; // 上涨绿色
  }
  
  .price-down {
    color: $danger-color; // 下跌红色
  }
}
</style>
```

## 🔄 主题切换

虽然默认使用暗色主题，但用户仍可以通过设置切换：

1. 进入 **设置** → **外观设置**
2. 选择主题模式：
   - **亮色**：传统浅色主题
   - **暗色**：交易风格暗色主题（推荐）
   - **自动**：跟随系统设置

## 📝 注意事项

### 1. 颜色一致性
- 所有上涨数据使用绿色 (#00C853)
- 所有下跌数据使用红色 (#F44336)
- 保持颜色使用的一致性

### 2. 对比度要求
- 确保文字与背景的对比度符合 WCAG AA 标准
- 白色文字 (#ffffff) 在黑色背景 (#000000) 上对比度为 21:1（优秀）

### 3. 可访问性
- 不要仅依赖颜色传达信息
- 使用图标或文字辅助说明
- 确保色盲用户也能理解信息

## 🚀 后续优化建议

1. **数据可视化**
   - ECharts 图表使用交易风格配色
   - K线图使用绿涨红跌配色

2. **实时行情**
   - 价格变动时闪烁提示
   - 涨跌幅用颜色区分

3. **自定义主题**
   - 允许用户自定义颜色方案
   - 保存用户偏好设置

## 📚 相关文档

- [前端设计风格分析](./FRONTEND_DESIGN_STYLE_ANALYSIS.md)
- [Element Plus 暗色主题](https://element-plus.org/zh-CN/guide/dark-mode.html)

---

**最后更新**: 2025-02-13  
**主题版本**: v1.0.0
