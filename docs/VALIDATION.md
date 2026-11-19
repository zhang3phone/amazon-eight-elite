# 0.1.0 候选版验收

验证日期：2026-11-18（洛杉矶）；UTC 跨至2026-11-19。本节记录发布前的本机验收；GitHub 发布状态以仓库为准。

## 实际完成

| 项目 | 证据与范围 | 状态 |
|---|---|---|
| 9个技能入口 | skill-creator 官方 quick_validate 校验统一入口和8项技能，全部通过 | verified |
| 技能安装 | 安装到独立测试目录，9个目录和 runtime 映射可调用；未改现有全局技能 | applied in test target |
| 离线与集成回归 | 50项全部通过；Python 3.12 捆绑运行时，含 openpyxl；显式启用隔离 PostgreSQL | verified |
| 真实紫鸟下载 | macOS、紫鸟环境内已登录的广告后台、现成已完成 SP 搜索词 XLSX，使用 Download 和保存对话框下载 | verified_read_only |
| 真实文件读取 | 检查表头与实际数据行；修正原生 XLSX 的错误范围声明 A1:A1 导致的截断，并加回归测试 | verified_read_only |
| 本机数据库 | PostgreSQL 16.15，独立临时库 amazon_eight_elite_test；peer认证、私有 Unix socket、无 TCP 监听 | applied in isolated test |
| 合成端到端 | 2份原件、3行原始数据、3个分组、1份分析，原件哈希一致；花费60、销售250、ACOS 24% | verified synthetic |
| 幂等与事务 | 重复输入返回 already_imported、不重复计数；故意制造中途错误后无部分入库 | verified synthetic |
| 证据一致性 | 检验之后改变原始路径文件，分析和入库仍使用同一份有界快照；哈希不符会在接触数据库前停止 | verified synthetic |
| 报告重导出 | 由数据库导出 HTML，与首次生成文件逐字节一致 | verified synthetic |
| HTML 页面 | 本机临时回环 HTTP 预览，检查实际页面内容和桌面截图；合成标识、日期、指标与候选可读 | verified desktop |
| 安装失败保护 | 模拟中途文件移动失败，回滚仅本次新建的技能目录，不动无关文件 | verified synthetic |
| 审查 | 独立只读源码审查发现快照竞态、前置资源限制和部分安装问题；修正后复审，无未解决阻塞项（限审查范围） | reviewed |

## 当前限制与 pending

- 真实下载的原生搜索词报表不含稳定活动/广告组 ID；未在本次补齐同周期活动报表及可追溯 ID。真实广告的完整“校验→入库→诊断”仍 pending，程序不会按同名猜配。
- 用户仅允许在临时测试库导入合成资料；真实文件只下载和检查，未入该库。真实业务资料不进入本发行目录。
- 八项入口保留，但确定性采集文件校验/入库/计算管线目前只覆盖 SP 活动与搜索词。其他能力是可调用专业流程，不代表所有自动化采集已实现。
- Homebrew 实际下载/安装分支未执行：本机已经具备 PostgreSQL 工具。本版不会替换现有 PostgreSQL 或自动启动系统服务。
- Windows、Linux、其他紫鸟内核、跨站点/SB/SD、超大文件、无人值守与定时任务未完成端到端验收。手机真实断点和打印分页也未验收。
- 数据库存储成功不是利润、预算金额或经营效果验证。候选仍需真实产品、成本、库存、当前设置和业务目标复核。
- 本地数据保存不等于完全离线推理；云端 Codex 分析所需内容仍涉及模型服务。

## 运行收尾

临时预览 HTTP 服务已停止；隔离 PostgreSQL 已通过 local-stop 停止，测试目录与数据保留，没有删除型回滚。没有开端口、改系统启动项、改真实店铺、连接既有远程库、写 NAS、覆盖全局技能或发布 GitHub。

## 复现

先依照 INSTALL.md 建立自己确认的隔离实例；设置 AEE_TEST_DB_CONFIG 指向该实例 db.json，执行全部 unittest。不要将变量指向生产或真实业务数据库。

发行目录由 `scripts/export_public.py` 仅按白名单生成，排除运行目录、数据库配置、Cookie、日志、缓存和真实报表。PUBLIC_MANIFEST.json 记录逐文件哈希；其隐私扫描不代替正式发布前人工审查。
