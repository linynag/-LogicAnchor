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

1. **`positions` (持仓表)**
   - `fund_code` (PK): 基金代码
   - `initial_cost`: 累计持仓成本 (TEXT/Decimal)
   - `hold_volume`: 绝对持有份额 (TEXT/Decimal)
   - `last_nav` / `nav_date`: 最新净值及其日期
   - `is_dirty`: 是否为延迟的脏数据

2. **`transactions` (流水表)**
   - `id` (PK): MD5去重哈希
   - `trade_date`, `fund_code`, `trade_type` (买入/卖出)
   - `amount`: 交易金额
   - `nav`: 确认净值
   - `volume`: 确认份额

3. **`daily_nav` (每日净值留痕表)**
   - `(fund_code, nav_date)` (联合PK)
   - `nav`: 当日净值
   - 作用：避免 AkShare 历史数据修正导致前后测算不一致，优先使用本地留痕的净值。

4. **`daily_metrics` (每日资产快照表)**
   - `metric_date` (PK): 日期
   - `total_cost`: 总投入成本
   - `total_value`: 总市值
   - `day_profit`: 当日总收益 (可能为 NULL/None)
   - `hold_profit`: 累计总持有收益
   - 作用：未来对接 Grafana 或 Echarts 绘制资产增长曲线的数据源。

---

## 🚀 5. 未来扩展方向 (AI 接手提示)
当用户提出新需求时，AI 应优先考虑以下方向：
1. **数据可视化**：基于 `daily_metrics` 表，生成前端 HTML 或对接 Grafana。
2. **飞书/微信机器人推送**：在 [运行.py] 跑完后，将看板字符串格式化后推送到 Webhook。
3. **AI 持仓诊断**：实现 `core/ai_interface.py`，把 `positions` 数据喂给大模型，让大模型结合宏观数据给出调仓建议。
4. **定投策略回测**：基于 `daily_nav` 里的历史数据，写一个虚拟的回测引擎（在 `services` 目录下新建模块）。