# Cartoon CV UI：可用性与科学误解风险评审

评审日期：2026-07-21  
角色：独立 QA + 第一次访问者代表  
范围：`docs/CARTOON_UI_LIVE_TASKS.md` 与当前 `demo/`  
限制：本评审不修改实现，不重新判断模拟器的科学模型是否正确。

## 结论

**Verdict：APPROVE WITH CONDITIONS（有条件批准方向，设计合同冻结前不批准实现）。**

把页面改成“可操作的实验卡通”是正确方向，因为当前页面已经严谨、可审计，却仍然要求访客先读懂大量文字、图表和术语，才知道页面在讲什么。卡通不能只是装饰；它必须成为页面的主导航和状态解释器，同时持续区分：

1. 已发表、作者处理过的真实实验曲线；
2. 解释性的实验流程插图；
3. 独立的 synthetic policy benchmark。

如果这三个层次在同一画面中以相同颜色、动画语法或箭头连接，卡通版会比当前页面更容易让人误以为真实数据驱动了模拟器，或者浏览器正在控制真实仪器。因此，以下条件是实现前门禁，不是以后再补的 polish。

## 当前页面为什么仍不直观

### 1. 第一眼看到的是说明，不是实验

首屏由标题、长副标题、模拟声明和第一块文字卡组成。真实 CV 图、样品名称、三电极与 potentiostat 的物理关系都不在第一视觉焦点内。第一次访问者能看到“CV”和“policy”，但看不到“谁连接到谁、什么被改变、什么被测量”。

### 2. 页面结构像技术报告和审计台

页面按 `01` 到 `08` 顺序展开，包含 fact cards、run identity、完整 metric table、event ledger、JSON 下载和 post-run reveal。这对审计很好，但主要故事被平均分配到很多同等重量的 panel 中。访客不知道应先看真实曲线、策略对比，还是逐事件 ledger。

### 3. 图表呈现结果，却没有呈现测量因果链

真实 CV 图显示 potential 与 current density；synthetic chart 显示 scan rate 与 normalized response。但页面没有一个持续可见的场景把下面这条链连起来：

```text
potentiostat 改变工作电极电位
→ 三电极电化学池产生电流响应
→ 记录 current vs potential 的 CV
→ 改变 scan rate 后比较响应规律
```

所以“Potential goes in. Current comes out.”虽然准确，仍主要依靠文字解释。

### 4. 真实层和模拟层虽然有标签，视觉语言仍太相似

两层都使用同样的米色 panel、绿色按钮、SVG 曲线和逐步播放控件。全局 sticky banner 同时写 “SIMULATED RUN” 和 “REAL CV REFERENCE”，反而要求访客一直解析一句复合声明。真实曲线与 synthetic response 在不同章节、不同纵轴单位下出现，但缺少持久、不可混淆的双层标记。

### 5. “更换样品”和“改变扫描速率”在空间上没有被彻底拆开

真实区允许选择三个 formulation，并播放 remove/rinse/load 流程；模拟区则对同一个 virtual sample 选择多个 scan rates。文本已经说明二者不同，但两种交互都被表现为“选择 → 播放 → 曲线变化”，访客仍可能把每次新的 scan rate 理解成重新换液。

### 6. 策略差异需要读定义和事件，不能一眼比较

Fixed Grid、Information Gain、Random 的结果卡主要显示 attempt 数和最终机制。要理解策略为什么不同，访客还要切 tab、逐步播放并观察曲线与 belief bars。没有一个并排的“下一点如何选”视觉对比，也没有直接显示：

- Fixed Grid：按预定位置走；
- Information Gain：每一步根据当前不确定性选最有辨识力的位置；
- Random：在合法范围内随机选。

### 7. 当前自动播放更像 slideshow，而不是可理解的状态变化

真实流程每约 1.05 秒推进一次，策略回放每约 1.25 秒推进一次。文字、曲线、belief bars 和事件列表同时变化。对第一次访问者、屏幕阅读器用户和认知负荷较高的用户，这个速度不足以理解“发生了什么、为什么、证据是什么”。

## 卡通交互最可能造成的误解

| 风险 | 访客可能形成的错误理解 | 必须采用的设计保护 |
| --- | --- | --- |
| 真实控制错觉 | 点击 Run 后，网站正在操作真实 potentiostat 或实验室 | 主场景永久显示 `Illustrated replay — no hardware connection`；Run 使用 `Replay` 或 `Show steps`，不用 `Start instrument` |
| 数据生成错觉 | 屏幕上的动画实时产生了已发表 CV 曲线 | 真实图旁永久显示 `Published, author-processed experimental data`；动画只移动游标/揭示已有点，不称为 measurement generation |
| 数据管道错觉 | 上面的真实 RFB 曲线被拿来训练或校准下面的 synthetic benchmark | 两层使用独立容器和不同背景/边框；不要用从真实层指向 synthetic 层的单向数据箭头；明确写 `context only — not benchmark input` |
| 样品更换错觉 | 每改变一次 scan rate 都会更换 electrolyte | cell 上持续显示同一个 `Virtual sample A` 标签；只有 formulation selector 改变时才出现 remove/rinse/load；scan-rate change 只移动控制旋钮 |
| 真实诊断错觉 | diffusion/surface/mixed 是对上方真实配方的诊断结论 | 三个 hypothesis 只出现在明确标有 `Synthetic world` 的区域；禁止把真实 formulation 名称带入 synthetic conclusion |
| 单位混淆 | normalized current 等同于真实的 mA cm⁻² current density | 两张图的单位和 provenance 始终贴近轴与数值；synthetic 数值写全 `unitless normalized response`，不能简称 `current` |
| 仪器机理误解 | potentiostat 向样品“发送电流”，或 reference/counter electrode 的功能相同 | 卡通上标注 `controls potential` 与 `measures current`；三电极用文字标签与简短角色说明，不靠颜色猜测 |
| 卡通几何被当真 | 画出的液位、体积、电极间距、管路顺序是本实验的精确 apparatus | 图注明 `schematic, not to scale`；除非有来源，不展示精确体积、几何或自动化管路 |
| 失败来源混淆 | timeout、drift、saturation 是发表实验中观察到的故障 | 每个故障显式标 `injected synthetic failure`；真实实验流程不复用相同警报图标和故障叙事 |
| 策略优越性过度外推 | 单次 run 中最快的 planner 一般都最好 | 结果区写 `one fixed synthetic scenario/run`；首先比较行为和预算，不设置通用“winner”奖杯 |
| 概率含义误解 | belief bar 是经过真实校准的物理概率或实验置信区间 | 标为 `planner belief in this synthetic model set`；不要使用 `scientific certainty` |
| 清洗步骤过度断言 | 演示的 rinse/equilibrate 是论文逐字记录的完整 SOP | 标为 explanatory workflow；只有被来源明确支持的 protocol 细节才能称为 published procedure |

## 5 秒 comprehension test

`CARTOON_UI_LIVE_TASKS.md` 当前要求 5 秒内回答七个问题，不现实。5 秒测试应只验证首屏的核心心智模型，而不是术语记忆。

### 测试方法

1. 招募至少 5 名第一次看到该项目、非项目开发者的参与者；至少 2 名不具备电化学背景。
2. 分别在常见桌面宽度和 390 px 左右手机宽度展示加载完成后的默认首屏 5 秒。
3. 5 秒后遮住页面，不允许继续阅读。
4. 让参与者用自己的话回答三个问题：
   - 这个页面展示的是什么实验？
   - 实验改变什么、测量什么？
   - 这是实时控制真实实验，还是数据/模拟回放？

### 通过标准

- 至少 80% 的参与者能回答“CV/电化学电位扫描实验”，不要求说出 cyclic voltammetry 全名。
- 至少 80% 能说出“改变电位或扫描条件，测量电流响应”。
- 100% 不得回答“网站正在远程运行真实仪器”。
- 至少 80% 能意识到页面同时包含真实参考数据和模拟内容，即使暂时说不出两者的全部关系。

若首屏仍需滚动才能看到样品、电极/仪器、输入箭头、输出箭头和 provenance 标签，则自动判定失败。

## 30 秒 comprehension test

### 测试方法

1. 从同一默认状态开始，允许参与者自由查看和点击 30 秒，但不提供口头指导。
2. 允许使用 sample selector、step/next 和 planner selector；不要求打开 JSON 或 metric table。
3. 30 秒后要求参与者完成七项口述或卡片分类。

### 必须理解的七件事

1. **物理样品**：上方是真实数据所对应的 named all-iron RFB anolyte。
2. **操作与信号**：potentiostat 扫描 working-electrode potential，系统记录 current/current density。
3. **真正换样时机**：只有切换 formulation 才 remove/rinse/load；同一 formulation 的不同 scan rate 不换样。
4. **真实数据来源**：真实曲线是已发表、作者处理的数据，不是网页刚刚测出来的。
5. **模拟边界**：planner 比较是另一个独立 synthetic teaching benchmark，真实曲线不是其输入。
6. **三个策略的差异**：Fixed Grid 预先布点；Information Gain 根据当前 belief 选下一点；Random 合法随机选点。
7. **结果边界**：一次 synthetic run 不能证明某策略普遍更优，也不能证明真实样品的机理。

### 通过标准

- 每位参与者至少正确 6/7；整体每题正确率至少 80%。
- 第 4、5 项属于 safety-critical comprehension：任何参与者把模拟结果称为发表实验结果，或声称真实曲线训练/校准了 benchmark，都判定本轮设计失败。
- 参与者不打开详细 ledger，也应能完成第 6 项；否则主交互仍然过度依赖审计层。

## 无障碍与交互验收标准

### 键盘和语义

- 所有可操作对象必须使用原生 `button`、`a`、radio 或符合 ARIA pattern 的 tab；卡通中的可点击 SVG 区域不能只绑定 pointer event。
- Tab 顺序必须与视觉故事一致：sample → step controls → planner → replay controls → audit details。
- tablist 支持 Left/Right、Home/End；radio/sample selector 具有可读名称和选中状态。
- 每个动态 SVG 有随当前 sample/planner/step 更新的 `<title>` 和 `<desc>`，并提供等价的短文本摘要。
- 焦点状态清楚且不被 sticky banner、动画层或 tooltip 遮挡。
- 自动更新不把焦点抢走；`aria-live` 只播报用户触发的关键状态，不按 1 秒频率朗读每个视觉帧。
- 播放超过 5 秒的序列提供随时可用的 Pause、Resume 和 Reset；手动 Next 永远可用。

### Reduced motion

- 不仅使用 CSS `prefers-reduced-motion` 缩短 transition；JavaScript 也必须读取该 preference。
- reduced-motion 模式下不得自动启动或继续 `setInterval` 播放；点击 Replay 后应显示静态当前状态，用户通过 Next 前进，或提供一次性“显示全部步骤”。
- 电位箭头、电子流、液体流、曲线游标和 belief bar 都必须有静态等价状态。
- 切换系统 motion preference 后无需刷新即可停止后续自动播放，是推荐验收项。

### 颜色和图形编码

- 普通文字与背景对比度至少 4.5:1；大字和关键图形至少 3:1；focus indicator 至少 3:1。
- real、illustration、synthetic 三层不能只靠颜色区分，必须同时使用完整文字标签、边框/纹理或图标形状。
- diffusion、surface、mixed 曲线同时使用颜色、线型和直接文字标签；数据点/失败点同时使用不同形状与文本状态。
- selected、completed、failed 状态均不得只改变颜色；需有 check、边框、形状或状态文字。
- 在灰度和常见色觉缺陷模拟下，三条策略、三种 hypothesis 与 success/failure 仍可区分。

### 触屏和响应式

- 所有主要触控目标至少 44 × 44 CSS px，目标之间保留足够间距。
- 不依赖 hover 才显示名称、解释、单位、来源或控制。
- 在 320 CSS px 宽度和 200% zoom 下不发生页面级横向滚动；若 chart/workflow 内部必须横滚，要有文字提示和可见的滚动 affordance。
- SVG 标签和按钮在 390 px 手机宽度仍可读，不以缩小整张桌面图解决响应式问题。
- 支持 tap 选择、tap 再确认；不能要求精细拖拽才能设定 scan rate。若有 slider，还必须有加减按钮、键盘输入和当前数值文本。
- 用户缩放不得被禁用；横竖屏切换后当前 sample、step 和 planner 状态保持一致。

## 数据来源和科学边界验收标准

### 真实实验层

- 真实图附近始终显示 `Published, author-processed experimental data`、样品名称、轴名称、单位、DOI 和 license。
- 数据加载时校验 `provenance: published_processed_experimental_data`；未通过时不画“近似替代曲线”。
- 动画只能揭示既有 published points，不得用“正在测量”“模型生成实验值”等措辞。
- formulation 切换必须同步更新 sample label、composition、pH、protocol、曲线和 accessible description。

### 解释性卡通层

- 永久显示 `Explanatory schematic — not to scale`。
- 未被来源支持的移液、清洗、平衡时间、仪器连接和故障细节不能呈现为论文事实。
- 卡通状态必须来自一个显式 state model：fresh cell、same sample/new scan condition、switch formulation、failed/paused；不允许仅凭动画位置推断科学状态。

### Synthetic benchmark 层

- 容器、图表、结果卡和 failure message 均持续显示 `Synthetic benchmark`，不能只在章节开头出现一次。
- normalized response 明确为无量纲 synthetic value；不得沿用真实 current-density 单位。
- 同一 campaign 始终显示同一 `Virtual sample` 标识；只有 scan rate 和操作改变。
- 真实 CV 数据不得进入 planner state、belief update 或 evaluator；UI 箭头不能暗示这种数据流。
- timeout、drift、saturation 写作 `injected synthetic failure`。
- hidden truth 只能来自 verified completed summary 的 `post_run_reveal`，且 reveal 后仍写 `synthetic truth, not experimental truth`。
- 页面永久说明：无 LLM、无真实仪器调用、无实验室控制、无机构背书。

## 对拟议卡通方向的批准条件

在实现前，reconciled design contract 至少要冻结下面八项：

1. **一个首屏主场景**：样品、三电极 cell、potentiostat、potential input、current output 与 CV 小图在同一视觉因果链中。
2. **双层而非流水线**：Real reference 与 Synthetic sandbox 并列或明确断开，不使用暗示训练/校准关系的箭头。
3. **持久 provenance 标签**：标签跟随相关图、数值和动画，而不是只放在页面顶部或脚注。
4. **明确的样品状态机**：首次装样、同一样品改变条件、切换 formulation、清洗/装样都有可测试状态和文本。
5. **策略的并排差异**：无需打开 ledger，30 秒内能看出预定、适应性、随机三种选点逻辑。
6. **progressive disclosure**：默认层只讲实验和策略；manifest、完整 metrics、event hashes 与 JSON 保留在明确的 Audit/Details 层。
7. **真正的 reduced-motion 路径**：JavaScript timer 也停止，静态文本与手动 Next 功能完整。
8. **先测再发布**：桌面和手机都通过上述 5 秒/30 秒测试、键盘检查、200% zoom、灰度/色觉检查和 provenance boundary test。

## Block 条件

出现任一项即应阻止发布，而不是仅记录为已知问题：

- 有访客测试者认为浏览器正在控制真实仪器；
- 真实数据和 synthetic response 使用同一未区分的单位或图例；
- 视觉箭头暗示真实 CV 是 planner 的输入；
- 改 scan rate 时出现 remove/rinse/load；
- 卡通把 hypothesis 结论关联到 named real formulation；
- reduced-motion 下自动 timer 仍持续推进；
- provenance、单位或状态只能通过颜色、hover 或动画获得；
- 手机/键盘用户无法完成 sample selection、step progression 和 planner comparison。

## 最终 QA 立场

当前页面适合作为严谨的工程审计原型，但尚未通过第一次访问者的“看图即懂”标准。卡通化可以解决这个问题，前提是它重构信息层次与状态表达，而不是在现有八段长页面上增加会动的实验室图标。

因此本轮对方向给出 **APPROVE WITH CONDITIONS**；对立即进入实现阶段给出 **BLOCK，直到 reconciled design contract 明确满足上述八项条件**。
