---
name: amazon-eight-elite
description: "亚马逊八项全能精英v1.0：协调八项运营能力，按授权通过本地紫鸟获取资料并使用本机 PostgreSQL，生成分析和 HTML 报告；不自动修改店铺后台。"
metadata:
  version: "1.0"
---

# 亚马逊八项全能精英v1.0

用户说目标即可选择相关能力，不必机械跑八项；明确要求全店八项时逐项报告资料覆盖。已确认的范围可复用，未指定店铺先在紫鸟列出可访问店铺供选择，不自行处理全部账号。

## 能力路由

- 日常监控：[amazon-daily-monitor](../amazon-daily-monitor/SKILL.md)
- 广告诊断：[amazon-ads-diagnosis](../amazon-ads-diagnosis/SKILL.md)
- Listing 优化：[amazon-listing-optimization](../amazon-listing-optimization/SKILL.md)
- 选品调研：[amazon-product-research](../amazon-product-research/SKILL.md)
- 库存物流：[amazon-supply-chain](../amazon-supply-chain/SKILL.md)
- 利润分析：[amazon-profit-analysis](../amazon-profit-analysis/SKILL.md)
- 合规初筛：[amazon-compliance-screen](../amazon-compliance-screen/SKILL.md)
- 运营复盘：[amazon-weekly-review](../amazon-weekly-review/SKILL.md)

## 本地工作流

取数、安装、入库和广告报告前，读取 [本地执行指南](references/local-workflow.md)。先检查可用工具和本地环境；能在授权范围自行查询、导出和校验的资料应主动补齐，只有用户登录/验证码、范围歧义或访问受限时才请求处理。没有 Computer Use 的环境不能声称已经打开紫鸟，改用用户导出文件并说明状态。

本技能的 `scripts/run.py` 提供环境检查、采集文件校验、本机 PostgreSQL 初始化/导入及 HTML 报告。CLI 本身不会点击紫鸟：界面动作由当前 Codex 可用的本地 Computer Use 工具执行。没有可用工具则报告缺口，不使用隐藏 Cookie、猜测 API 或未经批准的调试连接绕过。

本机数据库不存在时，先展示安装或隔离实例方案；准确库名、位置与影响由用户确认后执行。已有同名资源不覆盖；不接入远程或已有生产数据库。常规导入在已授权的专用库内继续，不反复询问。

保留原始资料及快照；以店铺、站点、日期、币种、归因口径和稳定 ID 对齐。缺数不当零，报告必须区分事实、待核实和建议。原始广告文件、行、计算结果和 HTML 保存本机数据库；报告可本地导出。数据交给云端模型分析时仍涉及模型服务，不宣称完全离线。

本套件只提供取数、分析与草稿。暂停/否词/竞价/预算、Listing 发布、采购/货件、退款与对外发送均不由入口自动授权。本次默认只读店铺。技能和脚本可用不代表全部平台、系统或真实经营效果已验收；合成数据要醒目标记。
