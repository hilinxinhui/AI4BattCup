# AI for Batteries Cup（AI4Batt Cup）

AI 电池挑战赛。

本仓库用于长期维护赛事资料、数据说明、评测代码和平台部署配置。评测平台采用自建 Codabench，参赛者提交 CSV 预测结果，方案代码私有保存。

## 分支约定

- `main`：维护最新年份的比赛信息，经确认后合并当年分支的更新。
- `2026`：2026 年比赛的工作分支。
- 后续每年创建以年份命名的分支，保留历年比赛内容。

数据集、测试标签、参赛代码、提交文件、凭据和运行产物不提交到 Git。

## 本地平台

Windows Docker 部署配置和使用说明见 [deploy/README.md](deploy/README.md)。
本地网站：<http://localhost:8080>。管理员凭据保存在 `.local/admin-credentials.txt`。
