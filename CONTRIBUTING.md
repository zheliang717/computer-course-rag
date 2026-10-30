# 参与开发

代码按 AGPL-3.0-only 发布；提交前请阅读 LICENSE 和 THIRD_PARTY_NOTICES.md。所有示例使用合成账号与原创夹具，避免提交个人部署的数据、Key、模型缓存或未经处理的教材原文。

后端使用 Python 3.12：`pip install -e ".[dev]"` 后，在项目根目录执行 `python -m pytest -q`。完整数据库及浏览器检查的步骤见 `.github/workflows/ci.yml`，其数据库、端口和账号必须保持隔离。可选外部 PDF 的哈希检查在未提供材料时明确跳过；核心 PDF 解析测试使用临时生成的原创四页文档。

前端使用 Node.js 22，在 frontend 中执行 `npm ci`、`npm run build`。浏览器工作流必须指向配置要求的专用 18086 入口，不能指向正在使用的 5173 或 18080。

修改数据库结构需新增 Alembic 迁移，核对空库与独立备份恢复。修改 AI 功能应使用 stub 和固定证据覆盖流程，再单独评估实际模型质量；不要在 CI 中使用个人服务密钥。
