# WorkBuddy 联动说明 · mcd-postmortem

> 本文档用于麦当劳程序员创意开发大赛 WorkBuddy 专项奖励的联动核验，说明如何在腾讯 WorkBuddy 中配置麦当劳 MCP 连接器并使用 mcd-postmortem 完成一次完整审计。

## 一、项目与 WorkBuddy 的关系

mcd-postmortem 的核心能力（订单审计 → 规则引擎 → 事故复盘报告）以纯 Python 实现，不绑定特定客户端；WorkBuddy 作为对话入口，通过麦当劳官方 MCP 连接器提供同样的数据能力（`order-list` / `list-nutrition-foods` / `now-time-info`），可以直接在对话里复现"麦门彻查"的完整审计体验。

## 二、在 WorkBuddy 中配置麦当劳 MCP 连接器

1. 在 https://open.mcd.cn/mcp 控制台申请 MCP Token（登录 → 控制台 → 激活）
2. 打开 WorkBuddy → 连接器设置 → 从 JSON 导入，粘贴以下配置：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN"
      }
    }
  }
}
```

3. 将 `YOUR_MCP_TOKEN` 替换为你的实际 Token（也可使用环境变量注入，见 `mcp-config.example.json`），保存并启用连接器

> 安全提醒：Token 仅保存在你自己的 WorkBuddy 配置中；本仓库任何文件都不包含真实 Token。

## 三、WorkBuddy 对话上下文示例

配置完成后，在 WorkBuddy 对话框中按以下流程对话，即可完成一次"麦门彻查"审计：

**第 1 步 · 采集证据**

> 帮我查一下我最近的麦当劳历史订单，列出每单的时间、门店、商品和实付金额。

**第 2 步 · 事实核查**

> 拉取麦当劳餐品营养表，把上一步每笔订单里的商品对应到官方营养数据（热量、钠），套餐按子项汇总。

**第 3 步 · 事故判定（本项目的规则引擎逻辑，可直接让 WorkBuddy 按此规则执行）**

- SEV1 重大生产事故：00:00–05:00 下单；或单笔合计 ≥ 1500 kcal
- SEV2 单点故障：同一商品连续 ≥ 3 单；10 分钟内连续下单
- SEV4 隐患告警：单笔钠 ≥ 2400 mg
- SEV5 流程瑕疵：11:30–13:00 午高峰到店自取
- INFO：营养表检索不到的商品记「404 未建档」

每个事故必须附上订单号与触发字段值作为证据链。

**第 4 步 · 输出复盘报告**

> 按 Postmortem 格式输出：事故编号、等级、事故概述、变更时间线、事故明细（按严重度排序）、根因分析、后续行动（Action Items）。语气正经，内容可以损我。

## 四、与本地 CLI 的分工

| 场景 | 用什么 |
|---|---|
| 完整体验（PNG 报告卡、--json、确定性单测） | 本地 CLI：`mcd-postmortem audit --card report.png` |
| 零安装快速体验 | WorkBuddy 对话（按第三节上下文）或 `mcd-postmortem demo` |
| 无 Token 演示 | `mcd-postmortem demo`（合成数据，本地运行） |

## 五、真实性声明

- 本项目对 mcp.mcd.cn 的调用为真实联调，审计结果中的订单号、金额、营养数据均来自官方 MCP 返回
- 规则引擎为确定性代码，同一份订单数据多次运行结果一致（见 tests/test_engine.py 的确定性回归测试）
- 本项目为参赛者独立开发，非麦当劳官方产品；报告结论仅供参考，不构成医疗或营养建议
