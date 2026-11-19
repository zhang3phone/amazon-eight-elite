# 卖家精灵与 SIF：提交自己的 MCP Key

本项目提供两家官方远程 MCP 的 **Codex 配置向导**，不用另装抓取器。配置器不执行网络请求、不查询ASIN、不消费业务额度，也不证明 Key 有效；真实鉴权与数据验收需提交 Key 后进行。

## 1. 去官方页面取得 Key

| 服务 | MCP 地址 | Key 获取入口 |
|---|---|---|
| 卖家精灵 V2 | `https://mcp.sellersprite.com/v2/mcp` | [MCP密钥管理](https://www.sellersprite.com/v3/mcp-manager?tab=secret) |
| SIF | `https://mcp.sif.com/mcp` | [MCP密钥管理](https://www.sif.com/mcp?tab=secret) |

选择自己的 MCP 密钥，不能用普通网页登录密码替代。权限、套餐、点数以账号当前状态为准；开源套件免费不代表第三方服务免费。

官方依据（2026-11-19核对）：[卖家精灵接口文档](https://www.sellersprite.com/v3/knowledge/feature/mcp-interface-description)、[SIF安装文档](https://blog.sif.com/article/mcp-install/Sif-MCP安装文档)、[Codex MCP配置](https://developers.openai.com/codex/mcp)。卖家精灵使用 `secret-key` 请求头；SIF当前官方示例同时在URL查询参数与请求头配置密钥。本向导按该示例生成，回执不打印带密钥URL。不要把完整配置、`codex mcp get` 的输出或连接日志贴到聊天/GitHub。

## 2A. 在本地浏览器填写 Key（推荐）

```sh
# 先预览：不启动监听、不读取或保存Key
python3 -m aee research-mcp-ui --provider both
# 确认后打开本机表单
python3 -m aee research-mcp-ui --provider both --apply
```

自动打开默认浏览器，使用密码框填写。仅监听127.0.0.1的随机端口；默认10分钟到期，成功保存后输入服务自动关闭，不留密钥回执文件。地址只在当前电脑可用。不能控制终端的Codex环境可启动此命令，再使用输出的本地地址打开浏览器，让用户亲自填写，不让AI代填或读取Key。

可加 `--no-browser` 仅显示本地地址、由用户或Codex打开；`--timeout 600` 设置10—3600秒有效期；`--provider sellersprite` / `sif` 可只填一家。`--config` 选择私有配置目标。未提交而关闭页面不会写入，进程到期结束（退出码2）；也可Ctrl+C取消。表单不是HTTPS远程服务，不提供公网/局域网绑定选项，不应通过隧道公开。

表单检查Host、Origin和一次性页面校验令牌，限制请求大小，禁用缓存与访问日志，不引用外部脚本。提交后仅保存配置，不验证Key、不远程取数或自动消费点数；真实验收按第3节另行进行。保持浏览器与本机环境可信，勿分享完整配置或带Key的URL。

## 2B. 在本地终端提交 Key（可选）

在完整源码目录运行，先预览：

```sh
python3 -m aee research-mcp --provider both
```

确认目标是自己的 Codex 配置后执行：

```sh
python3 -m aee research-mcp --provider both --apply
```

依次提示“卖家精灵 MCP Key”“SIF MCP Key”，在隐藏输入提示中粘贴并回车。**不需要把 Key 发给 Codex 对话、作者或 GitHub Issue。** 取消输入不会写入配置。不提供 `--key` 参数，避免进入进程参数与shell历史。可只配置一项：`--provider sellersprite` 或 `--provider sif`；缺少任意一家不妨碍先使用另一家。

默认写入当前用户的 `~/.codex/config.toml`；使用其他 Codex home 时，通过 `--config /your/private/config.toml` 明确指定，先预览再加 `--apply`。本辅助写入只验证POSIX；Windows请在官方支持的客户端私有配置中操作，未验收Windows文件ACL。

Key保存在本机Codex私有配置中（0600），不会写进项目或业务数据库。已有配置原文保留，生成0600本地备份；发现同名服务或已有该官方地址则停止，不覆盖或重复安装。备份也含原有凭据，留在私有配置目录。Git工作区内不允许写入；不要把私有配置用于公开发行。

### 回滚与并发编辑

配置时请勿同时编辑Codex配置或运行其他配置器；本向导锁只协调自身实例，并在替换前再次检查文件，不能替所有程序加锁。

使用默认Codex配置时，可通过 `codex mcp remove aee_sellersprite` 或 `codex mcp remove aee_sif` 移除对应服务，保留其他设置。若配置到自定义路径，请在该私有文件中仅删除生成的 `[mcp_servers.aee_sellersprite]` / `[mcp_servers.aee_sif]` 段（含其URL和http_headers），不要删除其他服务。

已有文件的备份位于相邻的 `config.toml.aee-backup-<时间戳>`，权限0600。需要整份恢复时，先关闭相关配置编辑，比较备份后发生的其他配置变更，再自行恢复并保持0600；不要用旧备份覆盖需要保留的新设置。初次新建配置无旧文件备份，移除两项服务即可。

## 3. 连接与业务验收

1. 重开Codex对话或按客户端要求重启，检查工具目录。配置成功只记为 `configured`，不是 `connected`。
2. 先发现实际工具名称和参数；SIF可在当前目录提供该工具时使用 `ping` / `sif_catalog`，不可假设版本固定。
3. 第一次业务取数前，说明站点、ASIN/关键词、日期、条数/页数和可能点数；按用户授权做小样本，不自动全页或批量消耗配额。鉴权失败不猜其他端点、不跨服务商回退、不输出响应中的凭据。
4. 记录来源、原始返回、抓取时间、统计周期、样本和估算性质，再交给选品流程。外部市场估计与领星/店铺真实订单分开，不把两家估计当作独立事实的双重证明。

可直接使用的任务：

> 亚马逊八项全能精英v1.0：检查已配置的卖家精灵和SIF工具目录，列可用能力；先提出美国站指定ASIN的最小选品取数计划，说明点数范围，不立即批量查询或改店铺后台。

报错时只反馈脱敏状态；Key无效、额度不足、客户端未刷新与没有市场样本是不同问题。没有两家Key时仍可进行店内分析或导入已授权报表，不伪造外部市场结论。
