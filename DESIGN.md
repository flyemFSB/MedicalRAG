# MedicalRAG 设计系统 — Many Islands Clinical（多岛临床）

> Register: **product**（聊天工作台 + 运营控制台）。Platform: **web**（Vite SPA）。
> 本文件是前端视觉与交互的唯一权威；实现落在 `apps/web/src/styles/tokens.css` 与 shadcn/base-ui 组件覆写。
> 术语一律以 [CONTEXT.md](../CONTEXT.md) 为准（Evidence / Citation / Safety Boundary / Document / Chunk…）。

---

## 1. 风格锚点（命名）

**Many Islands Clinical（多岛临床）** — 融合 JetBrains "Many Islands" 模块化工作空间与 Apple Design（HIG）的层次、克制与精密：

| 锚点 | 借鉴什么 | 不借什么 |
|---|---|---|
| **JetBrains Many Islands** | 桌面底板承托独立悬浮工作岛、清晰视隙（Gutter）、多窗格明确界限 | 繁重暗色开发者工具边框堆叠 |
| **Apple Design（HIG）** | Inset Grouped 列表/内嵌卡片、精细微圆角梯级、Segmented 药丸选项卡、触觉按压反馈 | 纯扁平不可辨识控件、过度模糊耗能毛玻璃 |
| **assistant-ui 设计法** | 证据与正文流式段落一体、阅读型输入胶囊、无装饰性「AI 光效」 | 营销页式大图插画、聊天气泡割裂感 |
| **临床信息设计** | 安全边界黑带最高对比、Evidence 永远可达、固定刻度、tabular 严谨数字 | 医院刺眼绿、仪表盘霓虹、低对比度文本 |

**一句话：** 像一张开阔的数字化诊疗桌面——底板沉静雅致，各项任务模块作为独立的「工作岛屿」悬浮其上，内容触手可及，证据明晰可查。

---

## 2. 空间与材质层级（Spatial Hierarchy）

采用四级精密空间阶梯，消除传统通顶通底的僵硬裁切线：

```
Level 0: Window Canvas (窗口底板画布 --color-canvas: #f2f1ec / #141312)
   ↓ 留出 8px–12px 自然视隙（gap / margin）
Level 1: Modular Islands (独立工作区岛屿 --color-surface, rounded-2xl, border-island, shadow-island)
   ↓ 岛内内嵌组织
Level 2: Inset Grouped Items (内嵌卡片/列表行/控件 rounded-lg~xl, hover 水洗)
   ↓ 悬浮交互
Level 3: Floating Overlays (浮层: Dialog / Menu / Popover rounded-2xl, --shadow-elevated)
```

1. **Level 0 — Window Canvas（底板画布）**
   统一的深底色（浅色 `#f2f1ec`，暗色 `#141312`），提供全局视界基准，避免白色大面积刺激视觉。
2. **Level 1 — Modular Islands（独立工作岛屿）**
   顶栏、侧栏、主工作区、右侧检查器均为独立圆角实体（`rounded-2xl`，发丝线描边，极淡微阴影 `shadow-xs`），岛与岛之间由自然视隙（`gap-2.5` / `gap-3`）隔开。每个岛具有独立视口与内嵌滚动条。
3. **Level 2 — Inset Grouped Items（内嵌分组与控件）**
   Apple HIG 风格的内嵌条目（会话行、导航项、指标微岛、表格行），带内缩安全边距与柔和交互反馈（hover 浅水洗，active `scale-[0.99]`）。
4. **Level 3 — Floating Overlays（浮层）**
   模态弹窗、下拉菜单和提示框轻盈浮于岛屿之上，高层级发丝线与微投影。

---

## 3. 设计原则（强制）

1. **证据即界面** — Citation `[n]` 与 Evidence 检查器同层可达、互相关联高亮；无证据时诚实展示空态，严禁虚构。
2. **克制即权威** — 纯净无眩光、无彩虹渐变、无玻璃拟态；强调依托字重、信息密度与单一功能色。
3. **安全边界最显眼** — Safety Boundary 必须以高对比黑底带 + 医疗警示红（`safety-band` / `medical-strong`）在岛屿顶部突显展示。
4. **岛屿独立性** — 每个岛屿拥有清晰的语义边界，岛内自主滚动，岛外视隙暴露桌面底板，信息不粘连。
5. **触觉式微动效** — 150–200ms ease-out，轻柔阻尼感，点击有微触觉反馈；`prefers-reduced-motion` 全量降级。
6. **跨面一致性** — 聊天工作台与运营控制台共用同一套岛屿阶梯与 Inset 控件语法。

---

## 4. 色彩与 Token

### 4.1 品牌中性色（底板与岛屿）

| Token | 浅色值 | 暗色值 | 用途 |
|---|---|---|---|
| `--color-canvas` / `--background` | `#f2f1ec` | `#141312` | 桌面底板画布（Canvas） |
| `--color-surface` / `--card` / `--popover` | `#ffffff` | `#1c1b18` | 岛屿主表面（Island Surface） |
| `--color-panel` | `#eae8e1` | `#23221e` | 岛本次级工作面、内嵌背景 |
| `--color-panel-strong` | `#dfdcce` | `#2c2a25` | 激活胶囊、user 气泡底色 |
| `--color-ink` | `#1a1a18` | `#f5f3ee` | 主标题、强调文字、主按钮 |
| `--color-body` | `#3d3b36` | `#e4e0d6` | 正文、普通描述 |
| `--color-faint` | `#6b6860` | `#a8a49a` | 次要元数据、输入框占位符（≥4.5:1） |
| `--border` | `#e2ded4` | `oklch(1 0 0 / 12%)` | 岛屿与控件发丝线 |
| `--input` | `#d4cfc4` | `oklch(1 0 0 / 16%)` | 输入框发丝边框 |
| `--ring` | `#2f6fed` @ 45% | `#6b9cff` @ 45% | Apple 风格无障碍焦点环 |

### 4.2 功能色（唯一）

| Token | 值 | 用途 |
|---|---|---|
| `--color-accent-ink` | `#2f6fed` | 链接、Citation 引用、激活指示、选中标线 |
| `--color-accent-hover` | `#1f5cd4` | 悬浮加深态 |
| `--color-accent-soft` | `#e8f0fe` | 引用高亮浅底、激活背景水洗 |
| `--color-accent-soft-ink` | `#1a4fad` | 浅底上的高对比蓝字 |
| `--accent` | `#f0ede6` | 控件中性悬浮水洗 |

主按钮规则：**墨色/反转色实体填充**（`--primary: ink`），保持权威基准，严禁大块蓝色实体按钮。蓝色仅用于「指示/证据/运行状态」。

### 4.3 语义状态（soft + 图标/文案）

| 状态 | 前景（浅/暗） | soft 背景（浅/暗） |
|---|---|---|
| success | `#2d6a4f` / `#6aaf90` | `#e8f2ed` / `#1a2e24` |
| warning | `#8a6d1f` / `#c4a35a` | `#f7f0dc` / `#2e2818` |
| error / destructive | `#c23b22` / `#e07a6a` | `#fceeea` / `#2e1c18` |
| info | `#2f6fed` / `#6b9cff` | `#e8f0fe` / `#1e2a44` |
| medical | `#c23b22` / `#e07a6a` | `#fceeea` / `#2e1c18` |
| medical-strong | `#ff8a80` | —（黑带专用警示红） |

### 4.4 安全边界黑带（Safety Band）

`--safety-band: #1a1a18`（暗色 `#0f0e0c`），文字 `#faf8f5`，警示红 `#ff8a80`。仅用于安全边界条；禁止用作装饰分隔。

---

## 5. 形状与阶梯（Geometry & Radii）

| 层级 | 圆角 | 阴影 / 边框 |
|---|---|---|
| Level 0: 桌面底板 (Canvas) | 0 | 0 |
| Level 1: 顶栏 / 工作岛 (Islands) | 16px (`rounded-2xl`) | 1px border + `--shadow-island` |
| Level 2: 岛内卡片 / 数据表 (Cards) | 12px (`rounded-xl`) | 1px border 或无边框 Inset |
| Level 2: 控件 / 按钮 / 输入框 | 8px (`rounded-lg`) | 1px border, 触觉轻按压 |
| Level 3: 浮层 / 弹窗 (Overlays) | 16px (`rounded-2xl`) | `--shadow-elevated` |
| 胶囊 (Capsule / Tag / Switch) | 9999px (`rounded-full`) | 0 |

---

## 6. 布局规范（Islands & Workstation Layout）

- **顶栏（Top Navigation Bar）**：
  在工作台作为一体化顶栏（`border-b h-11`，无外边距零缝隙），在管理与状态页作为悬浮顶栏岛（`rounded-2xl border shadow-island`）。集成 BrandMark、Apple Segmented Control 式选项卡（工作台 / 服务状态 / 运营控制台）与用户账号。
- **聊天工作台（Unified Tri-Column Workstation）**：
  三栏与顶栏采用一体化工作台视口咬合，顶栏与三栏间无多余外边距与缝隙（零间距，1px 精密发丝分割线），沉浸高效：
  - `会话侧栏 (w-64)`：左侧内嵌列表，细发丝分割线（`border-r`），次级微底水洗（`bg-panel/30`），内部为 Inset Grouped 会话条目，带右上角新建操作。
  - `聊天视口主工作区 (flex-1)`：居中主要工作区，顶部无缝连接安全边界横幅，中间流式消息段落，底部为浮动 Composer 胶囊与免责声明。
  - `证据检查器 (w-72)`：右侧无缝关联检查器，细发丝分割线（`border-l`），次级微底水洗（`bg-panel/20`），卡片式展示来源分块与置信度，底部基座内嵌评价反馈。
- **运营控制台（Dual-Island Console）**：
  - `运营导航岛 (w-60)`：左侧导航岛，分组 Inset 菜单。
  - `运营工作表主岛 (flex-1)`：右侧工作区主岛，统领页头、KPI 瓷贴微岛与 Inset 数据表格。
- **移动端**：
  小屏下侧栏折叠至抽屉浮层，主工作区自适应填满横向视口。

---

## 7. 动效与触觉微交互

- 基础转场：150–200ms `cubic-bezier(0.16, 1, 0.3, 1)`（Apple 风格自然回弹）。
- 按钮按压：`:active` 触发 `scale-[0.985]` 与平滑微降深，提供明确触觉反馈。
- 消息入场：150ms 淡入微抬升（`fade-in slide-in-from-bottom-1`）。
- 全面遵守 `prefers-reduced-motion: reduce`。

---

## 8. 无障碍（WCAG 2.2 AA）

- 文本对比度正文 ≥ 4.5:1，大字 ≥ 3:1。
- 焦点环全覆盖：`focus-visible:ring-2 focus-visible:ring-ring/45 focus-visible:outline-none`。
- 语义状态复合表达（颜色 + 图标 + 明确文案）。
- 全键盘无障碍导航（Tab 键通达所有岛屿与内嵌控件）。

---

## 9. 签名交互：Citation ↔ Evidence

正文中的引用锚点 `[n]` 与右侧证据检查器卡片具备双向聚焦高亮（`accent-soft` 水洗底色 + `accent-ink` 发丝线边界），提供临床级精确溯源体验。
