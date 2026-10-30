# Tailscale Funnel HTTPS 入口

标准 Compose 默认只监听本机。Funnel 方案建立独立副本，入口为浏览器 → HTTPS → 本机 18080 Web 代理 → 副本 API → 副本 PostgreSQL。

首次配置需要 Docker、本机栈已就绪、Node.js 22、PowerShell 7、Tailscale 账号以及与当前索引一致的模型缓存。

```powershell
pwsh -NoProfile -File .\scriptsunnel.ps1 -Action Prepare
pwsh -NoProfile -File .\scriptsunnel.ps1 -Action Build
pwsh -NoProfile -File .\scriptsunnel.ps1 -Action LocalStart
```

Prepare 仅向空白副本复制数据并生成独立账号凭据和密钥。它不实时同步，重复执行不会覆盖已初始化副本。账号凭据只保存在本机 `.private/funnel/` 中，勿提交 Git。Build 根据配置构建公开网页镜像；API 使用本机已构建镜像。

安装 Tailscale，按实际提示登录并授权设备、启用 HTTPS/Funnel，再执行：

```powershell
pwsh -NoProfile -File .\scriptsunnel.ps1 -Action Start
pwsh -NoProfile -File .\scriptsunnel.ps1 -Action Status
```

使用实际输出的网址访问。此工具拒绝覆盖设备上其他 Serve/Funnel 配置。Stop 关闭公开入口；LocalStop 停止副本容器，均保留数据。部署主机需要保持在线。

如果是已导入完整迁移包，直接核对 LocalStart、Start 和 Status，无需 Prepare 或 Build。新设备需要重新登录，网址应重新确认。仅公开网页代理，不公开数据库或 API 调试端口。官方配置：https://tailscale.com/kb/1223/funnel 。
