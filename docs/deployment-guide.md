# 智学助手部署手册

本手册配合根目录 [README](../README.md)，用于从源码建立新系统、保留数据换电脑，以及恢复跨设备访问。以下标准部署使用 Docker Compose；本机操作示例为 Windows PowerShell。

## 1. 环境与部署范围

| 场景 | 需要准备 |
| --- | --- |
| 从源码首次安装 | Git、Node.js 22、Docker Desktop（Linux 容器、Compose V2）；首次构建需联网 |
| 导入已有完整迁移包 | Windows x64、Docker Desktop（Linux / amd64）；无需宿主机 Python、Node.js 或 Git |
| 开发后端 / 运行检查 | 另装 Python 3.12、开发依赖；数据库与浏览器回归使用独立测试库 |
| 恢复已有 Funnel 公网副本 | 迁移包中的副本数据和配置、Tailscale、PowerShell 7；重新登录及启用 Funnel |

建议 16 GB 内存。磁盘应同时容纳镜像、模型缓存、业务数据和备份；导出迁移包还会额外保存一份镜像与数据。Docker 标准 CPU 路径不要求独立显卡。

本机栈固定使用 Compose 项目名 `computer-course-rag`；已有公网副本使用 `rag-funnel`。命令中显式保留项目名，避免移动文件夹后意外创建另一套空数据库。

## 2. 从源码首次安装

### Windows

按 [README 第 5 节](../README.md#5-从源码部署一套新系统)克隆、创建 `.env` 并生成独立 `AUTH_SECRET`，随后在项目根目录执行：

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
docker compose -p computer-course-rag up --build -d
docker compose -p computer-course-rag ps
```

`frontend/dist` 被 Git 排除，必须先构建。首次 API 镜像构建会安装 Python、CPU 向量模型运行库等依赖，耗时取决于网络。启动命令自动执行 Alembic 数据库升级，随后再启动 API。

### Linux x64 从源码安装

准备 Git、Node.js 22、Docker Engine 与 Compose V2 后：

```bash
git clone https://github.com/zheliang717/computer-course-rag.git
cd computer-course-rag
cp .env.example .env
```

编辑 `.env` 中的 `AUTH_SECRET` 为这套安装独立生成的长随机值，然后执行：

```bash
npm ci --prefix frontend
npm run build --prefix frontend
docker compose -p computer-course-rag up --build -d
```

这是从源码新建系统的路径，不会自动恢复其他电脑的数据。Windows 双击迁移包不能直接用于 Linux；ARM 主机也需另外验证基础镜像与 CPU 模型依赖，未提供跨架构整包恢复承诺。

### 确认服务就绪

```powershell
docker compose -p computer-course-rag ps
docker compose -p computer-course-rag logs --tail 100 api
docker compose -p computer-course-rag exec -T api alembic current
```

- 平台：`http://127.0.0.1:5173/`
- 健康检查：`http://127.0.0.1:5173/health`，应返回 `status: ok`。
- API 调试文档：`http://127.0.0.1:8000/docs`。

Web 容器代理同站点 `/api/v1/` 与 `/health`，浏览器访问同一页面入口即可。三个主机端口默认仅监听 `127.0.0.1`；这不是局域网广播服务。

## 3. 启用语义检索与在线 AI

两种模型各司其职：**向量模型**在本机将问题与资料转成向量，**生成模型**通过已配置的在线接口组织回答。仅填写在线 API Key 不会自动安装向量模型。

### 3.1 首次准备本地向量模型

默认示例为 `EMBEDDING_PROVIDER=hashing`，只用于功能启动。下面步骤适用于**新系统、尚未导入资料**；恢复已有知识库时应直接保留旧模型与缓存。

在已完成镜像构建的项目目录执行一次下载：

```powershell
docker compose -p computer-course-rag run --rm --no-deps -e HF_HUB_OFFLINE=0 api python -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_folder='/app/models-cache', device='cpu'); print(m.get_sentence_embedding_dimension())"
```

缓存写入宿主机 `models-cache/`。下载成功后，在 `.env` 修改以下三项并重建 API 容器配置：

```dotenv
EMBEDDING_PROVIDER=bge
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIMENSIONS=512
```

```powershell
docker compose -p computer-course-rag up -d --no-build api web
```

这里 `bge` 是 Sentence Transformers 适配器名称；该多语种模型原始输出 384 维，适配器补零至当前数据库的 512 维。Compose 正常运行时设置 `HF_HUB_OFFLINE=1`，因此必须预先准备缓存，不能指望首次提问时自动下载。

已有资料的系统更换向量模型时，应先备份、暂停写入，在隔离恢复库完成全量向量重建与检索评估，再同步模型配置及索引。仓库有 `scripts/reembed_chunks.py`，但它会更新存量向量，不是首次启动或普通换机时要运行的命令。仅仅维度相同不能保证新旧向量相容。

### 3.2 配置在线生成模型

推荐管理员登录后，在模型与检索配置中填写服务类型、兼容 API 地址、模型名、API Key 和超时，检查连接后确认保存。配置存入数据库，API Key 加密保存；学生和教师端不配置模型凭据。

也可以在**首次、尚未保存管理端配置时**通过 `.env` 提供默认值：

```dotenv
LLM_PROVIDER=compatible
LLM_API_BASE=https://你的服务地址/v1
LLM_API_KEY=你自己的服务密钥
LLM_MODEL=服务支持的模型标识
LLM_TIMEOUT_SECONDS=60
LLM_FALLBACK_OFFLINE=true
```

保存后执行 `docker compose -p computer-course-rag up -d --no-build api web`。管理端已保存的在线配置优先于 `.env` 默认值，改 `.env` 不会覆盖它；以后切换生成模型应在管理端操作。

不要把示例地址当作实际可调用地址。Token 额度与费用以所用服务账号为准；复制系统不会复制一份新的服务额度。离线回退只提供明确标记的证据内容，不是在线模型讲解。

## 4. 建立课程与知识库

1. 管理员建立课程、分配教师与学生，维护学期等基础信息。
2. 建立或选择课程资料库，将其与课程绑定。上传含可提取文字的 PDF，或通过登记的选读导入工具添加文字资料。
3. 在资料处理列表等待解析及索引完成；错误时查看原因，使用重试或取消。资料显示名称使用书名或正式资料名。
4. 设置资料发布状态与在线模型片段使用范围。模型配置有效并不代表每份资料都已允许外发。
5. 教师编辑课程概览、章节、知识点和对应阅读页，保存草稿并预览确认发布。
6. 学生选择课程提问，核对答案、来源标题、页码及引用片段；再验证练习、作业和成绩反馈。

`materials/` 保存资料文件、固定选读与来源登记，不会在 `docker compose up` 时自动导入数据库。各类导入脚本的参数与操作范围不同，不要为了补数据批量执行所有种子或审计脚本。迁移当前完整系统无需重新导入教材或重新生成测试业务数据。

## 5. 保留现有数据换电脑

### 推荐：Windows 完整迁移包

详细步骤见[简便迁移手册](simple-migration.md)。操作顺序为：

1. 旧电脑保持 Docker 与当前栈运行，双击根目录 `Export.cmd`。
2. 把项目目录旁生成的 `zhixue-migration-packages/zhixue-日期时间-编号/` **整个目录**复制到新电脑，放在准备长期保留的位置。
3. 新电脑安装并启动 Docker Desktop，使用 Linux 容器；双击包根目录的 `Import.cmd`。
4. 等待恢复后，用原账号在 `5173` 登录；若包中包含独立公网副本，再核对 `18080`。

此工具针对当前已运行、已完成模型配置的 Windows x64 系统，包含实际运行镜像，不依赖新电脑重新编译。导出前会核对镜像标签与正在运行的镜像是否一致；已保存加密凭据却缺少配对密钥时停止。仅使用 `.env` 凭据且未生成密钥的安装会按实际状态登记，无需新建密钥。

导入前会验证文件校验值、架构、已有项目容器、数据卷和端口；目标上已有安装则停止。失败后保留现场，不自动删除数据卷或覆盖数据库。包内 `project/` 是恢复后实际使用的程序和配置目录，应长期保留；不要在导入成功后把整个迁移包目录删掉。

迁移包不复制 `.git`、虚拟环境、`node_modules`、历史报告或旧备份。只运行系统无需这些开发文件；继续开发时可另外克隆仓库，按需要重新安装开发依赖。

### 完整恢复需要哪些内容

| 内容 | 本机位置 / 容器资源 | 为什么需要 |
| --- | --- | --- |
| 业务数据库 | `computer-course-rag_postgres_data`；副本为 `rag-funnel_preview_postgres` | 用户、课程、资料正文与向量、历史、题目、作业、成绩、课表及已保存配置 |
| 模型配置加密密钥 | `computer-course-rag_config_data`；副本为 `rag-funnel_preview_config` 中的 `model-config.key` | 解密数据库内保存的模型凭据，必须与对应数据库配对 |
| 环境配置 | `.env`；副本为 `.private/funnel/stack.env` 及相关状态文件 | 登录签名、数据库连接、镜像标签、模型名称及副本状态 |
| 向量模型缓存 | `models-cache/` | 导出当前使用的本地模型；避免恢复后无法检索，不重复带未使用模型 |
| 程序与资料文件 | 源码、构建产物、Compose、迁移、`materials/` | 恢复相同程序及磁盘资料 |
| 运行镜像 | 新包为 `images.tar.gz`，兼容旧包 `images.tar` | 在新电脑导入实际运行版本，压缩前后完整性核对 |

单独做 `pg_dump` 只备份数据库，不包含上述全部内容。手动跨系统迁移也应逐项准备，先在空库恢复、放回配对密钥与同一模型缓存，再启动 API 执行迁移；不要对正在使用的库直接执行覆盖恢复。

迁移是快照，不做双机同步。正式切换时停止旧系统新增写入，做最终导出，核对新设备数据后再停用旧入口。尚未提交的浏览器内容不会进入数据库快照。工具已有校验及防覆盖验证，但另一台物理电脑的整包恢复仍需实际验收。

## 6. 启停、备份与升级

在实际运行目录操作，本机栈始终指定项目名：

```powershell
docker compose -p computer-course-rag ps
docker compose -p computer-course-rag stop
docker compose -p computer-course-rag start
docker compose -p computer-course-rag logs --tail 100 api
```

`stop` 保留容器和数据，日常重启无需再导入。不要用 `down -v` 清理系统；它会删除命名数据卷。完整换机包也可作为升级前的整套备份，应另存到独立磁盘。

Git 工作副本升级时，先备份并核对数据库迁移，再执行：

```powershell
git pull --ff-only
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
docker compose -p computer-course-rag up --build -d
```

前端源码变更要重新构建 `dist` 与 Web 镜像。普通升级保留 `.env`、数据卷、模型缓存和加密密钥。

迁移包的 `project/` 没有 Git 历史，不能直接 `git pull`。需要升级时，在另一个目录获取新源码，保留并配对原配置、缓存和数据卷，核对构建及挂载路径后切换。独立 Funnel 副本使用自己的固定镜像标签与配置，不能用本机栈的更新命令代替；也不要运行历史教程里的旧镜像构建动作作为当前版本升级。

## 7. 让其他设备访问

### 使用浏览器访问现有主机

访问设备只需要浏览器，项目继续运行在主机。`127.0.0.1` 不能直接供手机访问；要么配置同一局域网入口，要么提供 HTTPS 网址。

- **局域网**：需有针对性地修改 Web 端口绑定，并配置主机防火墙，只开放网页入口。后端和数据库继续保持私有。长期使用建议配 HTTPS，避免直接开放开发服务。
- **HTTPS 入口**：使用反向代理或 Funnel 转发到网页代理，保留流式响应与 `Set-Cookie`。公开入口使用适当的 HTTPS Cookie 配置；独立副本已通过 `PUBLIC_PREVIEW=true` 启用。不要把数据库、API 调试端口或整个项目目录公开。

### 换机后恢复已有 Funnel 副本

以下仅适用于**完整迁移包已恢复副本**，不是从空库初始化的步骤：

1. 在新电脑安装 Tailscale 与 PowerShell 7，登录自己的 Tailscale 账号并授权设备。运行 `tailscale status` 确认已连接。
2. 在迁移包的 `project/` 目录用 PowerShell 7 执行：

```powershell
pwsh -NoProfile -File .\scripts\funnel.ps1 -Action LocalStart
pwsh -NoProfile -File .\scripts\funnel.ps1 -Action Start
pwsh -NoProfile -File .\scripts\funnel.ps1 -Action Status
```

3. 首次需要账号侧启用 Funnel 时，按 Tailscale 实际提示完成授权，然后再执行 `Start`。
4. 使用命令实际输出的 HTTPS 网址，在另一台设备登录并核对。新电脑的设备身份与网址需重新确认。

恢复完成后**不需要执行 `Prepare`、重新复制种子库或重设副本密码，也不需要执行 `Build` 才能启动**。已有服务使用包中镜像。关闭公开入口可执行 `pwsh -NoProfile -File .\scripts\funnel.ps1 -Action Stop`；停止副本容器可另执行 `-Action LocalStop`，两者作用不同。

首次从源码建立独立公网副本，请按 [Funnel 部署说明](tailscale-funnel-guide.md)操作。镜像标签指本机构建结果，未提供公共镜像仓库。建立副本后，其数据和账号凭据独立于本机栈。

主机、Docker 与网络要持续在线；休眠、关机或 Funnel 停止时，其他设备无法访问。服务器长期部署还需实际验证容量、备份恢复及运维流程。

## 8. 常见问题

| 现象 | 核对与处理 |
| --- | --- |
| `5173` 拒绝连接 | 确认 Docker 已运行，查看指定项目的 `ps`；确认 Web 容器存在且已启动。 |
| 网页返回 502 | 查看 API 日志，等待数据库迁移及 API 启动完成，再检查 `/health`。 |
| Web 构建找不到 `dist` | 先在 `frontend/` 执行 `npm ci`、`npm run build`，再构建容器。 |
| 换文件夹后数据像丢了 | 核对是否误用了另一个 Compose 项目名；用 `-p computer-course-rag` 查看原项目，不要继续往新空库填数据。 |
| 模型配置解密失败 | 核对模型密钥卷与恢复的数据库是否配对；不要生成新密钥覆盖旧文件。 |
| 问答回退离线 | 检查管理端的有效服务地址、模型名、Key、额度与连接状态，以及资料是否允许在线使用。 |
| 向量模型加载失败 | 核对 `.env` 的完整模型名与缓存；正常容器离线运行，缺缓存时需先下载。 |
| 资料检索异常 | 检查课程绑定、资料发布/处理状态以及模型是否与索引一致，再运行固定评测。 |
| PDF 无可提取文字 | 当前主要支持文字型 PDF；扫描件需先另行 OCR，不应当作正常文字资料直接导入。 |
| 导入提示已有安装或端口占用 | 保留目标已有数据与错误信息；先确认部署范围，不要强制清卷覆盖。 |
| 手机访问主机地址失败 | `127.0.0.1` 指向手机自身；应使用配置好的网页入口或 HTTPS 网址。 |

## 9. 检查与验收范围

[GitHub Actions](https://github.com/zheliang717/computer-course-rag/actions) 按 [CI 配置](../.github/workflows/ci.yml)执行后端、真实 PostgreSQL/pgvector、迁移、前端构建及浏览器工作流。测试库、账号和端口均独立；不要把自动写入检查接到现用系统上。

工程回归、数据库恢复、检索精度、AI 教学正确性、物理设备与生产验收分别核对。工具在当前主机通过校验和防覆盖检查，不代表已经在目标电脑完成恢复；模拟手机布局通过也不代表所有真实手机键盘、网络和性能场景已验收。
