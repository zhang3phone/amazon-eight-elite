# 本地执行指南

## 环境与初始化

1. 用本技能的 `python3 scripts/run.py doctor` 检查 Python、psql、initdb、pg_ctl 和可选 XLSX 支持。Python 至少 3.11；XLSX 使用 openpyxl，CSV 不需要第三方 Python 依赖。
2. 在当前工具列表寻找支持本机应用的 Computer Use。使用其文档提供的 getApp/应用列表与状态读取，按真实窗口导航；不能假定所有 Codex 环境都提供相同工具名。
3. PostgreSQL 已有时由用户指定本机连接、独立库名与范围；用 `db-create`、`db-init` 先预览，再使用准确 `--confirm-db` 和 `--apply`。没有时用 `postgres-install` 预览（首版仅辅助已有 Homebrew 的 macOS）；获得授权后安装。不要自行安装 Homebrew 或要求聊天发送管理员密码。
4. 自管理隔离实例用 `local-init --root <短路径> --database <确认库名> --confirm-db <同名>` 预览，加 `--apply` 执行。POSIX 上只开 Unix socket、peer 认证、无 TCP 监听，不动已有系统服务；`local-stop` 停止但保留文件。Windows 使用已有本机 PostgreSQL。

## 安装完成提醒与选品MCP

安装成功后提醒连接卖家精灵/SIF官方MCP，补充市场、关键词和竞品数据。引导用户运行 `python3 scripts/run.py research-mcp` 预览目标，加 `--apply` 后在本机终端隐藏输入自己的Key；不收集聊天中的Key。源目录 `docs/RESEARCH_MCP.md` 包含官方来源、密钥入口和验证步骤。两家可单独配置，缺Key不影响店内工作流；普通广告诊断不反复催促。仅配置记为configured，工具发现/鉴权与小样本返回通过后才写已连接；付费业务查询须匹配当前任务范围、页数与点数预算。密钥及带密钥URL不进入报告、日志或Git。

## 紫鸟取数（由 Codex 操作）

- 打开本机紫鸟，确认应用身份和当前窗口。若同名浏览器存在多个内核，先盘点并选择真实在用窗口，不猜固定路径或版本。
- 进入“账号”查看亚马逊店铺。未指定范围时列出可选别名，只采集用户选择的店铺、站点、日期。
- 用户自行完成密码、二次验证和 CAPTCHA；不获取 Cookie、凭据文件或隐藏浏览器内部数据。
- 打开对应店铺的广告后台，进入 Sponsored ads reports。优先下载已完成且期间正确、带原生 ID 的 SP 资料。若普通报告缺 ID，检查官方 Bulk Operations 的只读 Download campaigns：选择 SP 活动数据与 SP 搜索词数据，下载同一原生工作簿，禁止上传回后台。若需要新建/运行报告，先解释这会新建报表任务，取得符合当前范围的授权；不触碰投放开关、预算、竞价、否定或发布。
- 每次重新打开下载对话框，都重新核对日期端点、广告类型、状态/零曝光选项和最终导出范围；不能依赖控件保留旧值。大批历史零曝光数据可另存原件，并以明确的有曝光范围做管线验证，报告写清实际覆盖。
- 每一步操作后读取最新页面/应用状态，使用已观察到的按钮、链接和日期；不复制其他用户的元素索引、entityId、路径或商店 ID。
- 使用平台 Download 下载，处理本地保存对话框；确认完成、文件存在且不为空，不把网页成功提示当作本地文件落盘。
- 保存到用户自己的私有目录，保留原文件、店铺/站点/报表类型、统计期、生成时间、采集时间、时区/币种/归因窗口和最小来源说明。证据不含签名 URL、Cookie 或未脱敏的整屏个人信息。
- 下载为 ZIP、XLS 或存在多个工作表时先确认内容，用受支持只读方式准备 CSV/XLSX；禁止执行宏。首版校验器直接支持 CSV/TSV/XLSX。

## 文件交接与完整链路

复制项目 `examples/collection.template.json` 到私有工作目录，填写实际下载路径、范围和界面核实项，用 `collect --request … --output <新目录>` 归档并生成哈希。此工具验证文件与清单，不替代真实 GUI 操作，也不会伪造平台来源。

用 `inspect-workbook` 列工作表，再用 `inspect --sheet` 确认选定表的实际表头；按 `examples/sp-input.template.json` 明确填写稳定 ID、字段、期间、归因窗口和规则。配置报告路径指向归档文件。同一原生工作簿用 `input_layout: shared_xlsx_sheets`，明确两个不同工作表，活动只筛选实际 Campaign 实体；保留原始全表与筛选行数。不得按活动同名自动补 ID。原始导出没有所需字段时，先在受支持数据源补充并可追溯记录；无法补足就停在缺口，不声称完整诊断完成。

执行 `run --config … --collection <归档 collection.json> --db <私有 db.json> --output <新目录>`。事务性写入原始文件 bytea、原始行 JSONB、指标和 HTML；重复输入不重复记账。输出 report.html、metrics.json、candidates.csv、diagnosis.md 和入库回执。`db-verify` 核对计数和文件哈希，`export-html` 验证数据库可重新导出。

真实资料与合成测试严格分开。没有两表、稳定 ID、归因口径或范围，就先交付采集/字段缺口；不能借用合成数据填成真实经营结果。
