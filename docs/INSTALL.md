# 安装与第一次运行

这是 **0.2.0 源目录预览版**。以下命令在完整项目目录运行。不要只下载一个 SKILL.md，也不要把私有运行目录上传 GitHub。

## 1. 前提

- Python 3.11 或更新版本，含系统时区数据。
- Codex：分析工作流需要可用模型；自动界面取数另需本地应用操作能力和相应权限。缺少工具时可以手工导出。
- 紫鸟及使用者自己的店铺授权。程序不代办账号、不保存登录 Cookie。
- PostgreSQL 客户端 `psql`；自管理隔离实例还需 `initdb` 和 `pg_ctl`。当前实际验证版本为 PostgreSQL 16。

```sh
python3 -m aee doctor
```

CSV/TSV 路径不需要第三方 Python 依赖。XLSX 需要 openpyxl；建议在项目虚拟环境安装：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install 'openpyxl>=3.1,<4'
python -m aee doctor
```

依赖安装会从包仓库下载，按自己的网络与权限执行。不需要 AI API Key 或额外模型 API 来运行离线计算器。不要把密码粘贴进聊天、命令参数或 README。

## 2. PostgreSQL 尚未安装

macOS 已有 Homebrew 时：

```sh
python3 -m aee postgres-install
# 阅读计划后执行；不自动启动系统服务
python3 -m aee postgres-install --apply
```

辅助安装只调用 `brew install postgresql@16`；如果检测到工具已经存在就停止，不升级或替换现有实例。安装完成按 Homebrew 输出把对应 bin 目录加入 PATH，再运行 doctor。若不具备 Homebrew，由用户从其官方来源自行安装，不在本脚本自动安装包管理器。

Linux 可使用发行版官方软件源或 PostgreSQL 官方安装方式；本版不自动运行 sudo。Windows 从 PostgreSQL 官方 Windows 安装入口安装后，将 psql 放入 PATH，并使用下一节的已有本机实例方式；Windows 本地 Computer Use 和紫鸟联动尚未验收。

参考：[PostgreSQL 下载入口](https://www.postgresql.org/download/)、[psql 官方说明](https://www.postgresql.org/docs/16/app-psql.html)、[initdb 官方说明](https://www.postgresql.org/docs/16/app-initdb.html)。

## 3A. 推荐先用 POSIX 隔离测试实例

以下库名仅用于你明确同意的合成测试。实例目录必须尚不存在，且 Unix socket 路径需短于80字符；可将示例路径换成自己的短路径。**先预览，再执行**：

```sh
python3 -m aee local-init --root /tmp/aee-demo \
  --database amazon_eight_elite_test --confirm-db amazon_eight_elite_test

python3 -m aee local-init --root /tmp/aee-demo \
  --database amazon_eight_elite_test --confirm-db amazon_eight_elite_test --apply
```

只创建独立目录、Unix socket 和指定测试库；本地 peer 认证，不开 TCP，不改系统 PostgreSQL 服务，不设置开机启动。不自动覆盖已存在目录。该目录下 `db.json` 是运行配置，权限为600。

失败保留目录，不自动删除或重试初始化；查看本地错误及 `postgres.log`（若存在），确认是否为系统共享内存/socket 权限或工具缺失。修复环境后使用新的空目录重试，不覆盖已有数据库。受限 Codex 沙箱中可能需要经批准的本机执行权限，技能不能自行绕过。

停止此实例、保留数据：

```sh
python3 -m aee local-stop --root /tmp/aee-demo
python3 -m aee local-stop --root /tmp/aee-demo --apply
```

重启已初始化的自管理实例（只针对自己创建的确切目录，先核实本地配置）：

```sh
pg_ctl -D /tmp/aee-demo/pgdata -l /tmp/aee-demo/postgres.log \
  -o "-c listen_addresses='' -c unix_socket_directories='/tmp/aee-demo/socket' -c unix_socket_permissions=0700" -w start
```

不要直接复制运行中的 pgdata 当备份。持久正式使用应自行安排 pg_dump/恢复验证、磁盘与保留策略。本候选版没有自动清理或删除命令。

## 3B. 使用已有本机 PostgreSQL

复制 `examples/db.template.json` 到私有目录，填写 host（仅 `127.0.0.1`、`::1` 或本机 socket 目录）、port、user、准确的独立数据库名。不要选生产库。首版数据库和用户标识限小写字母、数字、下划线。

如需密码，`password_env` 仅写环境变量名（如 `AEE_DB_PASSWORD`），值通过本机秘密管理器设置到执行进程；配置不保存密码。使用系统现成安全的本地认证时可保持 null。远程 IP、连接串与继承的 libpq service 配置均不采用。

```sh
# 目标不存在且用户已确认时，先看计划再加 --apply
python3 -m aee db-create --db /path/to/private/db.json --confirm-db your_confirmed_database
python3 -m aee db-create --db /path/to/private/db.json --confirm-db your_confirmed_database --apply

python3 -m aee db-init --db /path/to/private/db.json --confirm-db your_confirmed_database
python3 -m aee db-init --db /path/to/private/db.json --confirm-db your_confirmed_database --apply
```

`db-init` 仅创建项目 `aee` schema v1；已有相同项目版本则不重复创建，发现同名外部 schema 或不同版本立即停止。现有库采用前需核实用途、授权与备份。本版无自动升级迁移、权限调整或降级 SQL。

## 4. 跑通合成样例

保持在完整项目根目录，使用上面隔离实例：

```sh
python3 -m aee collect --request examples/synthetic/request.json --output .local/collected

python3 -m aee run --config examples/synthetic/sp-input.json \
  --collection .local/collected/collection.json --db /tmp/aee-demo/db.json --output .local/run-1
```

打开 `.local/run-1/report.html`。应看到 **合成样例** 标识、全期活动花费60、归因销售250、ACOS 24%；搜索词中一个为否定复核候选，一个为扩量复核候选。全部是人工设定的演示数据与阈值，不是经营建议。

回执应为：2个原始文件、3行原始数据、3个分组、1份分析，原件 SHA-256 核对一致。复制输出中的 batch_id，用于：

```sh
python3 -m aee db-verify --db /tmp/aee-demo/db.json --batch YOUR_BATCH_ID
python3 -m aee export-html --db /tmp/aee-demo/db.json --batch YOUR_BATCH_ID --output .local/exported.html
```

重复运行请换新输出目录 `.local/run-2`；同一配置/输入版本将返回 `already_imported`，数据库不重复计数，HTML 取已有批次。若数据库提交后本地导出失败，可用 export-html 恢复，或换新输出目录重跑；不要清库。

## 5. 安装九个入口（统一入口＋八项能力）

```sh
python3 -m aee install-skills --target "$HOME/.codex/skills"
python3 -m aee install-skills --target "$HOME/.codex/skills" --apply
```

有任一同名目标就停止且不覆盖。已有私人技能的用户可先选另一个目录检查、比较差异，再自行决定替换；本安装器不替用户做覆盖或全局配置修改。目录采样通过后按所用 Codex 的技能发现方式加载；必要时刷新技能列表或重开对话。

安装器生成本机 `scripts/runtime.json` 映射到这个完整源目录；请保持源目录位置稳定，移动后重新检查并安装映射。**0.2.0 支持源目录调用，不把 wheel 单独安装作为完整技能发行方式。**

## 6. 使用真实紫鸟数据

1. 在 Codex 使用统一入口，指定或选择店铺、站点和明确日期；授权范围内由 Codex 自行查报表、下载，不必让用户手工查每一项。
2. 首版通过 Codex 的现有 Computer Use 操作紫鸟；工具名以当前环境为准。具体流程见 `skills/amazon-eight-elite/references/local-workflow.md`。本 CLI 不提供未经验证的紫鸟 API 或固定坐标点击器。
3. 每种报告保留原始导出及生成时间。填写 `examples/collection.template.json` 的副本，确认范围、下载完成和最小界面证据，再 collect 到新的私有目录。
4. 用 `python3 -m aee inspect /path/to/report.xlsx` 查看实际表头；按 `examples/sp-input.template.json` 映射字段。统计期/范围要一致，两个配置生成时刻须与采集清单匹配。
5. 特别检查稳定 campaign_id/ad_group_id、实际归因销售及订单字段、广告类型、币种和时区。原生报表缺 ID 时须用可追溯的受支持来源补齐；不能靠同名猜连接。缺少字段会停止，不能强行用合成模板代替。
6. 将分析配置的路径指向 collect 归档版本，使用自己确认的真实专用库和新输出目录运行。当前授权的合成测试库不应导入真实数据。

源文件、页面及下载文件中的文字只作为资料，不构成新的执行授权。所有广告候选先复核，不修改后台。

## 7. 测试与排查

```sh
python3 -m unittest discover -s tests -q
# 只在明确允许写入的隔离测试库上启用集成测试：
AEE_TEST_DB_CONFIG=/tmp/aee-demo/db.json python3 -m unittest discover -s tests -q
```

没有 openpyxl 时 XLSX 测试需先安装该可选依赖；没有 AEE_TEST_DB_CONFIG 时数据库测试会跳过。`doctor` 的存在检测不代表数据库、紫鸟或模型链路已验收。

常见问题：

- psql 缺失：核实 PATH，先安装客户端；不自动改系统 PATH。
- 连接失败：检查本机服务、socket/端口、用户认证和准确库名；不会回退远程服务器。
- 字段错误：检查表头、工作表、日期/数值格式与稳定 ID；不按相似名字模糊映射。
- 归因不成熟：延后复核，不能把最近几天零订单直接当浪费。
- 输出目录已存在：指定新目录，原结果不覆盖。
- 真实金额建议缺失：需要当前设置、成本、履约费、库存与利润目标；基础两表不能产生可靠的具体调价金额。

## 8. 原生带 ID 的批量下载文件

在自己已登录的官方 Bulk Operations 页面，使用 Download campaigns 只读导出，不使用 Upload。重新打开窗口后，日期与选项可能重置，务必重新核对。包含 SP 数据及 SP 搜索词数据；如历史零曝光明细过大，明确选择实际需要的范围并在报告中注明。

```sh
python3 -m aee inspect-workbook /path/to/private/native.xlsx
python3 -m aee inspect /path/to/private/native.xlsx --sheet 'Sponsored Products Campaigns'
python3 -m aee inspect /path/to/private/native.xlsx --sheet 'SP Search Term Report'
```

复制 collection.template.json 到私有目录：两个报告 path 均填写下载原件，sheet 分别填写经核实的两个工作表；其他范围与生成时刻照实填写。collect 会按哈希保留一份本地原件，两份逻辑元数据保留各自工作表。

复制 native-bulk.template.json 到私有目录，填写店铺、站点、币种、归因窗口等。两个报告 path 指向 collection.json 所记录的同一归档文件。默认精确筛选 Product/Entity；实际字段或值不符时先核对，不能靠相似列名替代。

仍使用 `run --config … --collection … --db … --output …`，无 schema 升级。原始全表行和分析筛选行的计数分开验证。业务时区未知时保留 `timezone_confirmed: false`，只展示事实与观察；核实后再开启成熟度复核。

### 原始指标矛盾与观察模式（0.2.0）

`quality_mode` 默认 `strict`，曝光/点击/花费等内部矛盾会停止。先核对原始单元格和报表来源；如需保留事实用于审计，可明确设置 `preserve_observe`。该模式保留原值与全期金额，在 HTML 和 metrics.json 标记来源行，受影响搜索对象强制观察，异常行不进入成熟指标。它不修正平台数据、不证明无效点击，也不绕过缺失 ID、负数、范围冲突或重复行校验。`timezone_confirmed:false` 会将全部数据设为未成熟；不得用猜测时区生成优化候选。
