# WorkBuddy 使用说明 · mcd-postmortem

本文说明如何把本项目用于 WorkBuddy 工作流，**不是开发对话上下文的导出记录**。如申请专项奖励需要真实开发过程，应提供实际导出记录；本文不虚构历史对话或核验结论。

## MCP 配置

配置占位符见 [mcp-config.example.json](mcp-config.example.json)，服务端为 `https://mcp.mcd.cn`。将占位符替换为自己的 Token 后，仅保存在客户端私有配置中。

本地 CLI 独立从环境变量 `MCD_MCP_TOKEN` 读取凭证；客户端 MCP 配置不意味着 CLI 会自动读取同一份配置。

## 在工作流中运行

若 WorkBuddy 当前环境具有本地终端执行能力，可在项目目录运行：

```bash
python -m pip install .
mcd-postmortem demo --card demo.png
mcd-postmortem audit --json --card my-report.png
```

第一条演示不需要 Token；真实审计需要环境变量。CLI 负责规则判定与卡片绘制，WorkBuddy 可协助解释输出或组织展示材料。单纯让模型在对话中按规则“口算”，不具备本项目代码的确定性保证，也不等于已经执行 CLI。

## 可使用的对话提示

> 在当前项目运行 `mcd-postmortem demo --json --card demo.png`，读取结构化结果，说明触发了哪些规则，以及营养匹配覆盖率。请注明数据是合成演示数据。

> 在已配置本地环境变量的前提下，运行 `mcd-postmortem audit --since 30d --json`，根据证据解释规则事件。不要推断没有被订单字段证明的取消原因、个人摄入或健康结论。

分享卡片隐藏订单号与具体门店；JSON 和终端保留完整证据，适合本地核对。集成边界与数据口径以 [MCP_INTEGRATION.md](MCP_INTEGRATION.md) 为准。
