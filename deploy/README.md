# Windows 本地 Codabench

本配置用于 AI4Batt Cup 的本机试运行，固定上游版本 `v1.33`。网站地址为 <http://localhost:8080>，存储服务为本机端口 9000；两个端口均只绑定 `127.0.0.1`。

源码位于仓库的 `.local/codabench`，凭据位于 `.local/codabench/.env` 和 `.local/admin-credentials.txt`。这些目录被 Git 忽略。数据库、文件存储及评测缓存存入 Docker 持久化卷。真实比赛数据与参赛代码不得加入 Git。

## 日常启动和停止

在仓库根目录使用 PowerShell：

```powershell
./deploy/Start-Local.ps1
docker compose --env-file .local/codabench/.env -f deploy/compose.yaml ps
docker compose --env-file .local/codabench/.env -f deploy/compose.yaml logs --tail 100 django compute_worker
docker compose --env-file .local/codabench/.env -f deploy/compose.yaml stop
```

重新构建镜像和前端时使用 `./deploy/Start-Local.ps1 -Build`。不要使用 `down -v`，它会删除比赛数据库和存储卷。

## 初次安装的构成

1. 安装 Docker Desktop，开启 WSL 2 与 Linux 容器。
2. 下载上游 <https://github.com/codalab/codabench/releases/tag/v1.33> 的源码包，将内容置于 `.local/codabench`。本次下载的 ZIP 的 SHA256 为 `32620F299AC66270E06DA5A180EC8F2058384DD14C1480E2ED985CEF530392F7`。
3. 根据上游 `.env_sample` 创建 `.env`，使用独立随机密码和 SECRET_KEY。设置 `DJANGO_SETTINGS_MODULE=settings.ai4batt`、数据库连接、RabbitMQ 凭据、MinIO 凭据、管理员环境变量。存储端点为 `http://localhost:9000/`，评测 API 为 `http://minio:8000/api`，域名为 `localhost:8080`，保留 `DEBUG=False`。
4. 运行 `./deploy/Start-Local.ps1 -Build`。前端构建须先完成，随后 Django 自动执行迁移和静态文件收集。
5. 启动脚本等待网站健康检查通过后，自动执行 `deploy/bootstrap_admin.py` 创建管理员；该脚本不会重置已有管理员密码。

## 已验证的流程

2026-10-11 已验证首页、前端静态资源、带 CSRF 的网页登录、管理员后台，以及 API 提交 → 消息队列 → 隔离评测容器 → 结果文件存储 → 排行榜评分。虚拟数据测试中，打乱行顺序的正确预测 RMSE 为 0，整体偏移 1 的预测 RMSE 为 1；参考文件的匿名请求返回 403。

可用以下命令重跑虚拟测试（会保留一个未发布的测试比赛和测试提交记录）：

```powershell
docker compose --env-file .local/codabench/.env -f deploy/compose.yaml cp deploy/smoke_test.py django:/tmp/smoke_test.py
docker compose --env-file .local/codabench/.env -f deploy/compose.yaml exec -T django python manage.py shell -c "exec(open('/tmp/smoke_test.py').read())"
```

测试比赛中仅含三个虚拟样本。原生提交界面使用 ZIP，本次提交包只包含 `predictions.csv`，没有参赛代码。平台目前仍保留上游通用提交功能，正式比赛前需要限制可接收的文件、制定 CSV 格式并配置真实比赛规则；本次测试不等于完成了所有权限与安全审计。

上游前端安装的 npm 审计报告为 12 项（4 项 moderate、8 项 high）。为保留上游兼容性，本次未强制升级依赖，正式对外部署前需评估修复。

## 本地适配

普通账户采用参赛者权限：可以浏览比赛、报名、下载允许访问的数据、上传自己的私有提交文件和查看结果；禁止创建或管理比赛、数据集、评分程序、任务、队列、组织及排行榜。前端隐藏管理入口，`participant_policy.py` 在后端同时检查 Session 和 Token 请求。提交上传仍使用上游的数据接口，但仅允许 `submission` 类型，并禁止公开或复用为其他资源。评分 worker 通过原有的单次提交 secret 回传状态和分数。

`participant_urls.py` 保留原有路由，同时兼容管理员创建的无邮箱账户报名；不虚构邮箱，跳过没有收件地址的邮件。人工审批规则仍由每场比赛决定。

首页只显示一个 `Benchmarks` 列表，按创建时间从新到旧列出已发布的比赛，不再分为 Popular 和 Recent；未发布的比赛和测试记录不显示。

`verify_participant_policy.py` 用真实 HTTP 请求验证禁止管理、报名审批、签名文件上传、提交评分、结果读取和管理员访问。运行测试时通过 `POLICY_TEST_USERNAME` 和 `POLICY_TEST_PASSWORD` 环境变量提供普通账户凭据，测试只使用虚拟数据，并保留未发布的测试记录。

`deploy/templates` 保存本站页面模板，通过 `local_settings.py` 优先加载，无需修改 `.local` 中的上游源码。首页和页脚已移除上游机构标志、Partners、About、News、项目历史、论文引用以及其他平台宣传链接，改用 AI4Batt Cup 标题。保留比赛列表、数据集、登录与管理入口。修改模板后重启 Django 即可生效，无需重新构建镜像。

`templates/base.html` 基于 Codabench v1.33 的同名模板修改，上游采用 Apache-2.0 许可，许可副本见 `templates/LICENSE.TXT`。

通过 Caddy 提供网站和静态文件。Django 和两个 worker 共享 MinIO 的网络空间，使同一个 `localhost:9000` 存储签名地址同时供浏览器和后端使用。数据库等服务通过 Compose 网络连接。此网络布局只用于本地试运行，正式部署应改为稳定域名和 HTTPS。

评测 worker 使用 Docker socket 创建评测容器，评测容器禁用网络，worker 并发数为 1。宿主机评测路径采用命名卷 `ai4batt-worker`。自动拉取评分镜像已禁用，使用本地构建的 `ai4batt/scoring:v1.33`；更换评分镜像时应预先构建或拉取。该镜像清除了应用镜像的 shell entrypoint，供 worker 直接运行评分命令。这仍需在正式比赛前配置独立评测机器、资源配额、备份和访问策略。

## 迁移

部署配置和评测代码可以迁移，数据库和存储卷须另行备份并恢复；只拷贝镜像不会包含这些持久化数据。`.env` 和管理员凭据须通过私有渠道迁移。Mac ARM 设备需重新构建对应架构镜像。
