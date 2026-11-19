# SP 报表与字段约定

## 范围和来源
一次处理一个店铺、站点、币种和归因窗口，恰好一份 campaign 和一份 search_term 逻辑报表。0.2 支持两个独立文件，或同一原生 XLSX 的两个不同显式工作表。多站点、SB/SD、多文件重叠快照分开运行，不静默拼接。只有搜索词报表时可人工做词级初筛，但不能冒充完整账号诊断；本脚本要求两表以作范围核对。

当前官方参考（部署编写核查日期 2026-11-18）：
- [SP 搜索词报表](https://advertising.amazon.com/help/G3HEFZYWZF84NPS9)：仅包含产生过点击的搜索词，可按日或区间汇总。
- [SP 活动报表](https://advertising.amazon.com/help/G4KJE82E7LDKAHZX)：活动层级表现。
- [广告归因](https://advertising.amazon.com/help/GX7KDKHMWQYMJ385)：广告互动日与成交日不同，窗口未结束时数据不完整。实际窗口以本次广告主类型/字段及当前文档为准，不能对所有广告统一套 7/14 天。

## 配置
复制 assets/sp-input.example.json 到独立工作目录，null 需按事实填入。币种使用三字母代码，时区使用 IANA 名称，期间采用 ISO 日期。每份报表有自己的带时区 generated_at，以记录不同生成时刻；归因截止按较早的一份确定，两表不因生成时间不同而被称为同一快照。

scope_confirmed 只表示已人工核实这份文件属于该店铺/站点/币种/广告类型，不能让缺乏这些字段的报表自证范围。若报表有相应列，映射 account_alias / marketplace / currency / ad_product 并作逐行验证；没有这些列会在结果中声明依赖人工范围确认。

不同文件若实际币种或归因窗口不同，应拆分运行；分表配置里的未知字段会被拒绝，避免用户填写了差异但程序忽略。生成时间超过当前时间 5 分钟的文件声明会停止计算。配置期间仅约束日期范围，实际有记录的日期另行列出；未出现的日期不能自动认定为零流量。

columns 的键是规范字段名，值是实际原始表头，不自动模糊匹配：
- 必需：campaign_id、impressions、clicks、spend、orders、sales；search_term 还需 ad_group_id、search_term。
- 可选文本：campaign_name、ad_group_name、target_id、target、match_type、advertised_asin、advertised_sku。
- daily 粒度还需 date；summary 以配置期间作为完整粒度。date_format 默认 %Y-%m-%d，其他日期格式必须显式指定；不猜 01/02/2026 的含义。
- columns 中 account_alias / marketplace / currency / ad_product 如存在须与顶层范围相符。未知字段不能直接加入 columns；其他实际分组列用 extra_dimensions 列出原始表头，以保留广告位/零售商等额外粒度。
- 使用稳定 ID 连接；没有 ID 时先从原始导出补齐或人工明确范围，不能只按活动同名自动合并。XLSX ID 应导出为文本；已经丢失精度的 ID 不能由程序恢复。
- orders 是归因购买/订单数，不是 units；sales 是与之同窗口的总归因销售额，不与 promoted/halo 子集混用。映射只接受用户已确认的归因列；可识别的 7 Day/14 Day 等列名必须与配置窗口一致。

number_format 为 decimal_dot（1,234.56）或 decimal_comma（1.234,56）。数值缺失不是零；负数调整、非有限数和非整数计数先停止处理。数值单元格不根据显示格式猜币种。

订单数为零但总归因销售额大于零时，先核对字段与归因口径，停止分析；不能据此生成否定候选。

## 粒度、公式与可追溯性
单份报表同一日期/期间、稳定实体和已映射额外维度重复时停止，不静默去重或把重复快照相加。需要用户确认遗漏的分组维度，或选择唯一快照。

XLSX 默认只有一个非空工作表时才自动选择；多个非空工作表需 sheet 明确命名。公式单元格一律拒绝，避免缓存缺失/过期；请使用平台原始数值导出。原始 CSV/TSV 使用 UTF-8（含 BOM）或明确配置的 encoding；表头行用 header_row 指定。

结果保留输入文件 SHA-256、大小、表头映射、生成时刻、每组来源行号、实际采用的阈值。CSV 中可能被表格软件解释为公式的文本加前导单引号，原值保留在 JSON，原文件不改。

## 成熟度
按店铺时区，以日期 D 的当天结束加 attribution_window_days 计算窗口结束，再保守增加 reporting_lag_hours（模板为 24 小时；仅是分析缓冲假设，并非平台时效保证）。时间不晚于两份报表中较早的生成时刻才视为成熟。summary 全期间满足截止条件才成熟，不能将横跨成熟与未成熟的汇总拆分推测。

## 退出码与输出
0：校验和计算完成；2：输入/范围/字段/数值等错误；3：输出失败。已有输出目录不覆盖。错误会给出字段/行号和原因，不打印整行私人数据。脚本不联网、不修改原始资料，不调用任何店铺接口。

## 0.2 原生 Bulk Operations 工作簿

优先使用官方只读下载中的 `Sponsored Products Campaigns` 与 `SP Search Term Report`：两表本身含 `Campaign ID` 和 `Ad Group ID`，不按名称推断实体。具体工作表名、字段和实体值必须从本次文件核对；不是所有平台版本都相同。不同来源的 ID 不按外观互换。

- 配置 `input_layout: shared_xlsx_sheets` 时，两种逻辑报表必须指向同一 XLSX 原件、选择不同工作表。默认 `separate_files` 保留独立文件/哈希校验，不放开重复快照。
- `row_filter` 是明确的原始列名到字符串值列表的等值筛选，多个列条件同时满足。活动表常需 `Product=Sponsored Products` 且 `Entity=Campaign`，避免把广告组、广告或关键词行的同一花费重复相加。不得猜实体值。
- 原件保持不变；数据库保留每个逻辑报表的原始全表行。`raw_row_count` 与参与计算的 `row_count` 分别记录，源行号不重编号。相同原件的本地采集副本按哈希去重，两个逻辑入口保留各自工作表元数据；数据库当前仍按逻辑类型保留原件副本。
- 同一搜索词可能对应不同关键词或商品目标，使用 `extra_dimensions` 保留原生 Keyword ID / Product Targeting ID 等真实分组，不把不同投放混成一个对象。
- ID 原样保留。数值 ID 达到16位、非整数或科学计数法字符串会停止；已经丢失的 Excel 精度不能恢复。获取平台文本原值后再处理。
- 归因窗口、币种、业务时区与导出日期需独立核实。任务列表显示的时区不是业务统计时区的充分证明。若业务时区尚未核实，可显式配置计算参考时区并设 `timezone_confirmed: false`；全部记录保持未成熟观察，报告明确待核实，不产生执行候选。`analysis_notes` 记录具体缺口或参考依据。
- 区间汇总跨越成熟与未成熟日期时，不能拆分推算成熟花费；全期事实与成熟指标在 HTML 中分列显示。成熟花费为0不代表未发生实际花费。

模板见 `examples/native-bulk.template.json`，使用前填写真实元数据，并将两个路径指向同一归档原件。所有原始文件仍受大小、解压及行列限制，超限先调整官方导出范围，不截断、不跳过检查。

官方参考：[Bulk Operations 数据说明](https://advertising.amazon.com/API/docs/en-us/bulksheets/2-0/understand-bulksheets-data)。界面行为以使用者当次实际观察为准。

### 原始指标矛盾与观察模式（0.2.0）

`quality_mode` 默认 `strict`，曝光/点击/花费等内部矛盾会停止。先核对原始单元格和报表来源；如需保留事实用于审计，可明确设置 `preserve_observe`。该模式保留原值与全期金额，在 HTML 和 metrics.json 标记来源行，受影响搜索对象强制观察，异常行不进入成熟指标。它不修正平台数据、不证明无效点击，也不绕过缺失 ID、负数、范围冲突或重复行校验。`timezone_confirmed:false` 会将全部数据设为未成熟；不得用猜测时区生成优化候选。
