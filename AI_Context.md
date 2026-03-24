# LogicAnchor 个人资产管理系统 - AI 知识库 (AI_Context)

**最后更新日期：** 2026-03-24

## 📌 1. 项目简介
LogicAnchor 是一个基于本地 SQLite 和 AkShare 接口的个人基金资产管理系统。
核心目标是提供一个**绝对精准（一分不差）**、**可追溯（流水与每日快照留痕）**、**可扩展（预留AI分析与Grafana展示接口）**的资管底座。

---

## 🗂️ 2. 目录结构与模块职责

```text
LogicAnchor/
├── data/
│   ├── logic_anchor.db         # SQLite 底层数据库（核心资产数据）
│   └── 交易流水.csv            # 增量买卖数据录入入口（手动维护，程序自动消费）
├── config/
│   └── config.yaml             # 系统配置（预留给飞书Webhook、API Keys等）
├── infrastructure/
│   └── db_manager.py           # 数据层：封装 SQLite 的初始化与增删改查，所有数值用 TEXT 存取
├── services/
│   └── calc_engine.py          # 计算层：纯函数库，严格使用 Decimal 处理所有的加减乘除
├── adapters/
│   └── akshare_adapter.py      # 适配层：封装 AkShare 获取净值，包含【指数退避重试】和【QDII延迟标记】
├── core/
│   ├── trade_listener.py       # 业务层：流水监听器，负责读取 CSV -> 计算份额 -> 数据库去重与双写
│   └── ai_interface.py         # 业务层：预留的 AI 分析接口（当前为空实现）
├── scripts/
│   └── init_anchor.py          # 脚本层：基于 2026-03-20 的绝对数据初始化系统底座（仅需运行一次）
└── 运行.py                     # 表现层/主入口：执行监听 -> 抓取最新净值 -> 计算收益 -> 打印看板
```

---

## ⚙️ 3. 核心业务逻辑与避坑指南 (AI 接手必读)

### 3.1 精度控制：绝对禁止使用 `float`
- **规则**：系统内所有涉及金额、份额、净值、收益的变量，**必须**使用 `decimal.Decimal`。
- **数据库**：SQLite 原生不支持 Decimal，因此在 [db_manager.py] 中，所有数值字段（如 `amount`, `nav`, `hold_volume`）都定义为 `TEXT`，入库时 `str(val)`，出库时 `Decimal(val)`。
- **目的**：杜绝浮点数四舍五入导致的“几分钱对不上”的坏账问题。

### 3.2 QDII 基金与“数据延迟”策略 (`is_dirty`)
- **背景**：纳指等 QDII 基金存在 T+2 时差，中国白天的 AkShare 接口拿不到美国当天的净值。
- **逻辑**：[akshare_adapter.py] 在获取净值时，如果返回的 `actual_date < target_date`，会将 `is_dirty` 标志位置为 `True`。
- **表现**：在 [运行.py] 看板中，不会将这些基金的昨日收益算作 0，而是：
  1. 状态栏显示：`⚠️ 数据延迟(净值日:2026-03-20)`
  2. 昨日收益显示：`--` （避免误导用户以为今天没涨跌）
  3. 总计昨日收益：不包含这些未更新的基金，并提示 `(X只基金暂不可算)`。

### 3.3 交易流水监听与防重复入库
- **触发**：[运行.py] 启动时调用 `TradeListener.process_csv()` 读取 `data/交易流水.csv`。
- **去重机制**：使用 `hashlib.md5(f"{date}_{code}_{amount}_{type}")` 生成唯一 `trade_id`。如果 `transactions` 表中已有该 ID，则跳过。
- **份额计算**：买入份额 = `买入金额 / 当日净值`（如果买入日还没出净值，程序会挂起该笔交易报错，需等净值出了再运行）。
- **卖出逻辑**：采取**等比例扣减成本**法。卖出后新成本 = `老成本 - (老成本 × (卖出份额 / 老份额))`。

### 3.4 “昨日收益”的精准推算逻辑
- 当我们查看 T 日看板时，如果发生过买卖，不能直接用 `T日市值 - (T-1)日市值` 算昨日收益，必须剔除现金流。
- **公式**：`当日真实收益 = (T日市值 + T日卖出到账) - ((T-1)日市值 + T日买入本金)`
- 该逻辑已在 [运行.py] 的 `display_portfolio` 函数中通过 `cashflow` 和 `volumes` 字典完美实现。

---

## 🗄️ 4. 数据库表结构 (`logic_anchor.db`)

### 4.1 统一约定（非常重要）
- 所有金额/份额/净值字段一律用 `TEXT` 存储（内容为 Decimal 的字符串），避免浮点误差。
- 所有写入数据库的数值都来自 `Decimal`，写入用 `str(x)`，读取后用 `Decimal(x)`。

### 4.2 `positions`（持仓表：你现在手里有多少“货”）
**用途**：运行看板、计算持有收益、市值、份额。

**主键**：`fund_code`

**字段说明**：
- `fund_code`：基金代码（PK）
- `fund_name`：基金名称
- `initial_cost`：累计持仓成本（TEXT/Decimal）
- `hold_volume`：绝对持有份额（TEXT/Decimal）
- `last_nav`：最近一次成功使用的净值（TEXT/Decimal）
- `nav_date`：`last_nav` 对应日期（YYYY-MM-DD）
- `is_dirty`：1 表示净值延迟/待校准（例如 QDII 时差）
- `updated_at`：更新时间

### 4.3 `transactions`（流水表：每一次定投/卖出动作）
**用途**：记录可追溯流水；同时作为“昨日收益剔除现金流”的输入。

**主键**：`id`（MD5 去重哈希）

**字段说明**：
- `id`：MD5（由 `日期+代码+金额+类型` 拼接生成），用于防重复导入
- `trade_date`：交易日期（YYYY-MM-DD）
- `fund_code`：基金代码
- `trade_type`：买入/卖出
- `amount`：交易金额（TEXT/Decimal）
- `nav`：确认净值（TEXT/Decimal，来自 AkShare）
- `volume`：确认份额（TEXT/Decimal，买入=amount/nav；卖出目前也用 amount/nav 作为“反推份额”的简化口径）
- `status`：默认 SUCCESS（预留给未来“挂起/失败/待补数据”）
- `created_at`：写入时间

### 4.4 `daily_nav`（每日净值留痕表：防止历史修正导致对不上）
**用途**：净值“锁定”，避免 AkShare 历史净值修订导致回头看时收益变化。

**主键**：`(fund_code, nav_date)` 联合主键

**字段说明**：
- `fund_code`：基金代码
- `nav_date`：净值日期（YYYY-MM-DD）
- `nav`：当日净值（TEXT/Decimal）
- `is_dirty`：1 表示该净值是“延迟拿到的”（如 QDII 请求 3/24 得到 3/20）
- `updated_at`：更新时间

### 4.5 `daily_metrics`（每日资产快照表：给 Grafana/曲线使用）
**用途**：每天跑一次看板，就把总资产汇总固化下来。

**主键**：`metric_date`

**字段说明**：
- `metric_date`：日期（YYYY-MM-DD）
- `total_cost`：总持仓成本（TEXT/Decimal）
- `total_value`：总当前市值（TEXT/Decimal）
- `day_profit`：总“昨日收益”（TEXT/Decimal 或 NULL；当部分基金不可算时为 NULL）
- `hold_profit`：总持有收益（TEXT/Decimal）
- `is_dirty`：1 表示当日快照存在延迟数据（例如纳指 QDII 未更新）
- `updated_at`：更新时间

### 4.6 `trade_history`（历史遗留表）
当前代码仍保留 `trade_history` 的建表语句用于兼容迁移，但**业务逻辑已统一使用 `transactions`**。

---

## 🧭 5. 日常操作流程（写 CSV 会发生什么）

### 5.1 每天你需要做什么
1. 在 [交易流水.csv](file:///e:/IDEA_code/个人项目/智矩交易LogicAnchor/data/交易流水.csv) 追加一行（示例）：
   - `2026-03-23,000216,50.00,买入`
2. 运行：
   - `python 运行.py 2026-03-24`（看 3/24 看板；若 3/24 无新净值，会沿用 3/23 的收益表现，并显示净值日）

### 5.2 程序启动后执行的标准链路
以你追加的这行 `2026-03-23,000216,50.00,买入` 为例，程序内部发生以下事情：

**A. 读取 CSV 并识别新交易**（[trade_listener.py](file:///e:/IDEA_code/个人项目/智矩交易LogicAnchor/core/trade_listener.py)）
- 逐行读取 CSV 的 `日期/代码/金额/类型`
- 生成 `trade_id = MD5(f\"日期_代码_金额_类型\")`
- 去数据库查询 `transactions`，若 `trade_id` 已存在则跳过（防重复）

**B. 获取确认净值（含重试）**（[akshare_adapter.py](file:///e:/IDEA_code/个人项目/智矩交易LogicAnchor/adapters/akshare_adapter.py)）
- 调用 `AkShareAdapter.get_fund_nav(code, date)`，遇到网络抖动会自动指数退避重试
- 得到 `(nav, actual_date, is_dirty)`：
  - `actual_date` 可能小于请求日期（QDII 时差），此时 `is_dirty=True`

**C. 入库净值留痕**（[db_manager.py](file:///e:/IDEA_code/个人项目/智矩交易LogicAnchor/infrastructure/db_manager.py)）
- 写入/更新 `daily_nav(fund_code, actual_date)`，把净值锁定下来，后续优先使用留痕净值

**D. 入库流水 + 更新持仓**（[trade_listener.py](file:///e:/IDEA_code/个人项目/智矩交易LogicAnchor/core/trade_listener.py)）
- 计算份额：买入 `volume = amount / nav`
- 写入 `transactions`：新增一条流水记录
- 更新 `positions`：
  - 买入：`initial_cost += amount`，`hold_volume += volume`
  - 同时更新 `last_nav/nav_date/is_dirty`

**E. 打印看板 + 写入每日快照**（[运行.py](file:///e:/IDEA_code/个人项目/智矩交易LogicAnchor/运行.py)）
- 对每只基金抓取“看板日的净值”（可能延迟），并显示“净值日”用于解释口径
- 计算并显示：
  - 当前市值：`hold_volume * nav`
  - 持有收益：`当前市值 - initial_cost`
  - 昨日收益：按照“剔除现金流”的公式计算；如果净值日落后太多则显示 `--`
- 写入 `daily_metrics`：固化当天总成本/总市值/昨日收益（可空）/持有收益/is_dirty

### 5.3 你在库里会看到哪些变化（总结）
当你追加一条买入记录并运行程序后，通常会出现：
- `transactions` 增加 1 行（新流水）
- `positions` 对应基金的 `initial_cost`、`hold_volume` 发生变化
- `daily_nav` 增加 1 行或更新 1 行（净值留痕）
- `daily_metrics` 增加/更新 1 行（当天资产汇总快照）

### 5.4 常见现象解释
- “净值日”不是看板日：说明数据延迟（尤其是 QDII），系统会标记为 `is_dirty` 并避免产生坏账
- “昨日收益 = --”：说明这只基金当天无法严格按“昨日”口径计算（例如净值日停留在更早日期）

---

## 🚀 6. 未来扩展方向 (AI 接手提示)
当用户提出新需求时，AI 应优先考虑以下方向：
1. **数据可视化**：基于 `daily_metrics` 表，生成前端 HTML 或对接 Grafana。
2. **飞书/微信机器人推送**：在 [运行.py] 跑完后，将看板字符串格式化后推送到 Webhook。
3. **AI 持仓诊断**：实现 `core/ai_interface.py`，把 `positions` 数据喂给大模型，让大模型结合宏观数据给出调仓建议。
4. **定投策略回测**：基于 `daily_nav` 里的历史数据，写一个虚拟的回测引擎（在 `services` 目录下新建模块）。
