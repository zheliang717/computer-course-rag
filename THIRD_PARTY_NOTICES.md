# 第三方组件与资料说明

智学助手原创项目代码版权归 © 2026 zheliang717 所有，按根目录 LICENSE 的 GNU AGPL v3（AGPL-3.0-only）发布。许可证不改变第三方组件、教材、模型及服务各自的授权。

## 主要直接依赖

| 组件 | 上游许可 | 来源 |
| --- | --- | --- |
| PyMuPDF / MuPDF | AGPL-3.0，另有上游商业授权选项 | https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright |
| FastAPI、SQLAlchemy、Alembic、Pydantic、Pydantic Settings、pgvector Python 客户端 | MIT | 各安装包的发行元数据与许可证文件 |
| Psycopg | LGPL-3.0-only | https://www.psycopg.org/psycopg3/docs/basic/install.html |
| Pillow | MIT-CMU | https://github.com/python-pillow/Pillow |
| HTTPX | BSD-3-Clause | https://github.com/encode/httpx |
| cryptography | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography |
| Sentence Transformers | Apache-2.0 | https://github.com/huggingface/sentence-transformers |
| Vue、KaTeX、Marked | MIT | 对应 npm 包中的 LICENSE |
| DOMPurify | Apache-2.0 OR MPL-2.0 | https://github.com/cure53/DOMPurify |

本表按当前依赖元数据整理，不代替随各发行包提供的完整许可证。间接依赖、系统组件、Docker 基础镜像及其 NOTICE/COPYING 文件仍适用各自条款；更新版本时应一并核对。

## 课程资料和模型

- 第三方教材、PDF、网页原文、选读摘编和模型权重不适用本项目代码许可证。
- 公开源码库保留资料来源登记与导入工具，不捆绑第三方教材原文。使用者应自行取得适当资料并按其条件使用。
- 本项目自行编写的最小演示文本与测试夹具按项目许可证发布；演示用户、作答与成绩是合成样例。
- 私有交付包中的资料、模型与原有署名、许可说明沿用对应来源条件。私有访问权限不改变上游授权。
- 默认多语种向量模型来源：https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 。模型许可与模型卡以具体下载版本为准。

源码与部署说明：https://github.com/zheliang717/computer-course-rag 。网络部署者应按 AGPL 的适用条件向用户提供相应源码，并保留版权与第三方声明。
