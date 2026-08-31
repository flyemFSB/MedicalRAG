# MedicalRAG — Design System

> Product register. DESIGN 是证据优先的医疗知识工作台：聊天界面 + 运营控制台。本规范借鉴 **Vercel 设计语言**（vercel.com/design）——单色、Geist 字体、连续画布、发丝边框、零装饰、默认静止——并将其应用于医疗证据表面。核心判断：Vercel 的「克制 + 证据驱动 + 排版优先」与 MedicalRAG 的「证据即界面」定位天然同构。实现 token 位于 `apps/web/src/styles/tokens.css`（Tailwind v4 `@theme`）。
>
> **本规范取代此前所有前端视觉（Notion 暖纸壳、JetBrains Many Islands）。** 连续画布取代漂浮岛，黑白灰取代暖冷 tint，发丝边框取代浮影与光晕。

## 1. Identity & scene

**场景：** 临床医生或知识维护者在诊室/办公桌前、会议间隙，桌面办公光线下阅读证据、核验答案。他们需要一个**高对比、低干扰、扫一眼即信任**的浅色表面。

- **主题：** light（场景使然——不是"工具都该深色"）。
- **色彩策略：** Restrained 的 Vercel 变体——**单色为主，蓝色仅在有意义处出现**。"Design in monochrome. Use color only when it adds significant meaning to state, action, or data, and pair it with a non-color cue."（颜色永远搭配非颜色线索：形状、权重、位置。）
- **身份由排版与证据结构确立，不由装饰。** 工具消失在任务里；熟悉 Vercel 语言的用户不会在任何一处停顿。

## 2. Design principles

Vercel 的判断，不是 Vercel 的装饰。逐条落地到医疗表面：

1. **默认静止。** 动效只在三种情形出现：解释状态变化、保持连续性、确认动作。没有自动滚动、模拟打字光标、装饰性脉冲、hover 位移、视差、滚动显现。
2. **单色设计。** 灰色承载全部结构；蓝色只用于状态/动作/数据且必然带非颜色线索。
3. **排版优先于表面。** 层级来自字体大小/字重/字距，先于边框、色块与图标。
4. **证据即界面。** 溯源、引证、分块 ID、相关度始终可达；每个回答的"证据支撑什么、不支撑什么"同样明确。
5. **克制即权威。** 不用面板、边框、图标、色块去填补证据空缺；空缺就让它空着。
6. **自信来自证明，不是宣传。** 语气精确、冷静、直接、技术上诚实、编辑式克制。

## 3. Color

### 3.1 单色刻度（全部承载结构）

| Token | 值 | 角色 |
|---|---|---|
| `--vbg-surface-primary` | `#ffffff` | 主画布——唯一连续表面 |
| `--vbg-surface-secondary` | `#fafafa` | 次级表面：侧栏、工具栏、悬停 wash |
| `--vbg-surface-contrast` | `#0a0a0a` | **强对比带**：医疗安全边界（最高信号） |
| `--vbg-text-primary` | `#0a0a0a` | 主文本（≈18:1） |
| `--color-body` | `#2e2e2e` | 正文（≈12:1） |
| `--vbg-text-secondary` | `#555555` | 次要文本（≈7.6:1） |
| `--color-faint` | `#767676` | 占位符/禁用（≈4.8:1） |
| `--vbg-border-subtle` | `oklch(0 0 0 / 0.08)` | 发丝边框（默认） |
| `--vbg-border-default` | `oklch(0 0 0 / 0.14)` | 输入框、强调分组 |
| `--vbg-border-strong` | `oklch(0 0 0 / 0.24)` | hover/选中边框 |

**规则：** 正文/次要/占位符全部 ≥4.5:1。灰就是灰（chroma 0）——不偏暖不偏冷。边框一律发丝级，不用阴影表达结构。

### 3.2 功能色（Vercel 蓝，唯一 accent）

| Token | 值 | 角色 |
|---|---|---|
| `--color-accent` | `#0070f3` | 选中、链接、引证、focus ring、进度条 |
| `--color-accent-hover` | `#0061cf` | accent hover |
| `--color-accent-ink` | `#0070f3` | 链接/强调文本（≈4.8:1） |
| `--color-accent-soft` | `#eaf3ff` | 浅蓝 wash：ghost 按钮、选中态背景 |
| `--color-accent-soft-ink` | `#0a5fb8` | accent-soft 上的文本（≈6:1） |

蓝只用在这些地方：**选中、交互反馈、链接、数据高亮**。做主按钮的是黑（见 §7.1），不是蓝——那是 Vercel 的决定性句法。图表只用"需要区分序列或编码有源状态"时上蓝。

### 3.3 语义状态（medical 最高信号）

| Token | 值 | 使用 |
|---|---|---|
| `--color-success` | `oklch(0.52 0.12 158)` | 完成、健康 |
| `--color-warning` | `oklch(0.6 0.13 70)` | 降级、排队、部分 |
| `--color-error` | `oklch(0.55 0.2 25)` | 失败、拒绝、不可达 |
| `--color-info` | `oklch(0.55 0.15 252)` | 信息提示 |
| `--color-medical` | `oklch(0.5 0.21 24)` | **安全边界**——红，仅在临床风险场景出现 |

每个语义色带 `-soft`（浅底）与 `-border`（浅边框）变体。**状态永不只靠颜色**：一律配文案/符号/权重。

### 3.4 医疗安全边界（对比带）

安全边界是全部产品中**唯一**使用 `--vbg-surface-contrast`（近黑）强对比带的元素：**近黑底 + 白正文 + `--color-medical` 红标题与图标**。这是本产品"唯一证据承载的构型动作"——它在任何页面上都不可忽略，也从不静默消失。

## 4. Typography

**Geist Sans**（Google Fonts，`wght@400..600`）：正文、标题、标签、控件、表格、KPI、日期、计数、百分比、时长。**Geist Mono**：仅用于代码、命令、路径、原始 token、时间戳、短操作标识符（source/chunk/run ID、评分）——**只把标识符设成 Mono，不把整句设成 Mono**。

- 字重阶梯：400 regular / 500 medium / 600 semibold。**没有 700+，没有任意字重。**
- 数字比较用 `tabular-nums`（表格、评分、KPI、ID）。
- 标题一律 sentence-case，陈述"面向用户的具体主张"。**禁用**：全大写 eyebrow、overline、装饰性节号、em dash。
- 正文每行 60–68 字符（阅读列 max ~720px）；表格/图表可满宽。
- 首行不缩进，段落以间距分隔。

### 4.1 固定刻度（product register 不用 clamp）

| 角色 | 尺寸 | 行高 | 字重 |
|---|---|---|---|
| display | 2.5rem | 1.1 | 600（-0.03em）|
| page-title | 1.5rem | 1.25 | 600 |
| title | 1.25rem | 1.3 | 600 |
| section | 1.125rem | 1.4 | 600 |
| lede | 1.125rem | 1.6 | 400 |
| body | 1rem | 1.6 | 400 |
| compact | 0.875rem | 1.5 | 400 |
| label | 0.875rem | 1.4 | 500 |
| caption | 0.8125rem | 1.4 | 500 |
| metadata | 0.75rem | 1.4 | 400 |

`display` 只给**单个页面定调语句**（欢迎屏 headline）。其余一律用 page-title 以下。`text-wrap: balance` 于 h1–h3，`pretty` 于长正文。

## 5. Grid & spacing

- 共享外网格：**桌面 12 列 / 平板 6 列 / 移动 4 列**。阅读正文通常占 6–7 列；表格、图表、对比可占满 12 列。
- 每个对象对齐共享边线/基线/网格线；列沟槽清晰可辨。
- **留白必须放大焦点对象**——大块空矩形是布局失败。
- 间距刻度（4px 基）：`space-1` 4 / 2:8 / 3:12 / 4:16 / 5:24 / 6:32 / 8:48 / 10:64 / 12:96 / 16:128。
  - 组内间隙 8–16；组间 24–32；大节 48–64；`space-16`（128）只用于真正的章断，不作默认页距。
- 每个间隙只有一个 owner；子元素不得叠加竞争性 margin。

## 6. Shape & surface

- **通常是一整块连续画布。** 边框/表面只出现在：选中、交互、警示、对比、或间距无法表达的**真实分组**。**不要用卡片包裹每个区块/指标/图表**——"不用深色圆角矩形围住每个图表"。
- 无嵌套面板；无"每个节一张卡"。
- **圆角克制且统一：** `--radius-small` 4px / `--radius` 6px / 大块 8px 封顶。圆形仅用于 dot/开关/pill。卡片、输入、按钮全部 ≤8px。
- **无阴影。** 层级由发丝边框与字重表达，不由 drop shadow。（唯一的例外：悬浮浮层如 palette/dropdown/toast 可加一道 ≤8px blur 的极淡阴影，用于从画布分离。）
- 连续画布上，面板之间的"分组"用 `--vbg-border-subtle` 发丝边框表达。

## 7. Components

### 7.1 Buttons

| 变体 | 实现 |
|---|---|
| **Primary** | 黑底 `--vbg-text-primary` 白字，radius 6，hover 深灰 `#2a2a2a`。**主按钮是黑，不是蓝。** |
| **Secondary (outline)** | 白底、黑字、`--vbg-border-default` 边框，hover 灰 wash |
| **Ghost** | 透明，hover 灰 wash `#f2f2f2` |
| **Link** | 蓝 `--color-accent-ink`，hover underline |
| **Danger** | 红底白字或 `--color-error-soft` 底红字 |

每按钮带 default / hover / focus（可见蓝 ring）/ active / disabled / loading。一视图一个 Primary，其余 defer 到 ghost/text。

### 7.2 Form controls

- Input/select/textarea/search：白底、`--vbg-border-default` 发丝边框、radius 6、focus = 蓝 ring + 蓝边框。禁用 = faint。错误 = 红边框 + 内联错误 + `aria-invalid`。loading = 骨架字段。
- Checkbox/radio/switch 用原生语义；开关用于二元设置（开 = 黑或蓝，选中态用蓝 ring）。

### 7.3 Chat（核心表面）

- **连续画布，无气泡岛。** 线程阅读列 max 720px 居中。
- **User 消息：** 黑底白字气泡（`--vbg-text-primary` bg），radius 8，右对齐，max-width 70%。身份即"我发出的"。
- **Assistant 消息：** **无气泡**——正文直接落在画布上，全阅读宽；元数据与引证在正文下方。证据即界面：不要包装盒。
- **引证：** 蓝色 pill（`--color-accent-soft` 底 / `--color-accent-soft-ink` 字，选中态 `--color-accent` 实底白字），编号即证物。
- **流式：** 黑色 2px 方块 caret 闪烁，或内容块 pulse——不是转圈。
- **证据 / 来源：** 扁平列表；每项是发丝边框分组（真实分组）——标题、source/chunk ID（Mono）、snippet、`tabular-nums` 评分、蓝色进度条；选中态蓝边框 + 蓝 wash。expandable；provenance hover 可见。
- **安全边界：** **黑色对比带**（§3.4）——近黑底、白正文、红标题与图标，置于答案上方；涉及治疗/用药/诊断/急症意图时必现，不可静默关闭。
- **推荐问题：** 发丝边框行（白底）可点，右端箭头；不是图标盒。
- **欢迎屏：** 无 eyebrow、无 all-caps、无光晕。一个 Mono 标注（`font-mono` caption）+ display headline（sentence-case）+ lede + 建议问题行 + 安全边界脚注。

### 7.4 Admin（运营控制台）

- **Data table：** 扁平、满宽、发丝行分隔；表头 `label` 字重 caption 灰；**数值列右对齐 + `tabular-nums`**；ID/时间戳 Mono；行 hover 灰 wash；选中态浅蓝；排序指示蓝。无卡片包装、无 column 装饰。loading = 骨架行；空态 = 教学式空态。
- **Dashboard：** **stat strip 而非 metric boxes**——一组 KPI 由发丝竖线分隔（`vbg-stat-strip`），不是"大数字+小标签+渐变"的 hero 模板。图表扁平；直接标签优先于图例；caption 说明"这张图展示什么、不建立什么"。
- **Badges/pills：** 仅用于**真实状态**（running/succeeded/failed/降级）。metadata 不用 pill 包装。soft 底 + 高对比字，颜色配文案。
- **Nav（顶栏/侧栏）：** 连续画布。顶栏白底 + 发丝底边框；侧栏白底 + 发丝右边框。nav 项 text；hover 灰 wash；active = ink + `font-medium` + 灰 wash pill（单色表达"当前位置"）。蓝色留给真正选中（表格选中/引证），不用于导航当前位置。
- **Empty states** 教界面：具体文案 + 一个动作。

### 7.5 Overlays

- **Dialog** 仅在 inline/渐进式替代都用尽时（产品规则）。focus-trap、esc 关闭、backdrop 半透明黑。
- **Toast：** 白底发丝边框、语义图标；error 手动关闭；右上。
- **Command palette**（运营）：面板 + 搜索 + 键盘导航——模式是 palette，不是自定义 modal。

## 8. Motion

- **默认静止。** 不加动效。
- 加动效只当它：解释状态变化（折叠展开）、保持连续性（列表重排）、或确认动作（按钮按压、toast 进入）。
- 动效参数：150–250ms、ease-out-quart；无 bounce、无 elastic、无 hover 位移、无视差、无页面级入场序列、无"每节同一入场反射"。
- 加载 = **骨架 shimmer**，不是内容中央转圈。
- **Reduced motion（非可选）：** `@media (prefers-reduced-motion: reduce)` 全部折叠为瞬时/交叉淡入。

## 9. Accessibility

- 对比：正文/次要/占位符 ≥4.5:1；大文本 ≥3:1。禁止浅灰正文、禁止 tint 底上的灰正文。
- Focus：每个交互元素可见 `:focus-visible` ring（2px 蓝 + 2px offset）。
- 键盘：完整导航；skip-link；focus 顺序 = 阅读顺序；仅 dialog 有意 trap。
- 语义：语义化 HTML；`aria-label`/`aria-live` 于流式与异步；`aria-invalid` + `aria-describedby` 于错误；**状态永不只靠颜色**。
- Reduced motion：见 §8。

## 10. Do / Don't

**Do：** 白画布 + 灰阶结构 + 发丝边框；蓝只给选中/链接/引证/focus；**黑主按钮**；Geist Sans/Mono；数值右对齐 tabular；连续画布不包卡；安全边界黑色对比带；默认静止；教学式空态；一致性按钮/表单词汇。

**Don't：** 装饰性渐变、渐变文字、glow、blobs、条纹、纹理、网格背景、玻璃拟态、纸面模拟、彩色侧栏、装饰性阴影、伪深度；卡片包一切；全大写 eyebrow；装饰性节号（01/02/03）；metadata pill 化；为装饰而动的任何东西；em dash；正文首行缩进。

## 11. Implementation

- Tailwind v4 `@theme` 与 CSS 自定义属性在 `apps/web/src/styles/tokens.css`。
- Geist Sans/Mono 经 Google Fonts 在 `apps/web/index.html` 加载；`--font-sans: 'Geist'`，`--font-mono: 'Geist Mono'`。
- shadcn 变量映射：`--primary`（黑主按钮）→ `--vbg-text-primary`；`--accent`（hover wash）→ 灰 `#f2f2f2`；`--ring` → `--color-accent` 蓝；`--background` → `--vbg-surface-primary` 白。
- 聊天表面（assistant-ui）消费消息/证据/安全 token；运营控制台（recharts/TanStack Table）消费同一语义 token。
- 组件状态由设计系统组件强制，不在每个 screen 里临时 ad-hoc。
