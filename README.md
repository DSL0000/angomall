# AngoMall V19 原版还原

当前首页直接使用用户上传的 `AngoMall_V19.html`，逐字节保留原始 HTML、CSS、JavaScript、文案、布局和交互。未插入新样式或后端适配脚本。

- 首页文件：`static/index.html`
- 只读对照文件：`static/original.html`
- 两者 SHA-256：`4bd6d520497305827bf6704e98aee74d887fd91618a7ca7eca1deb52fe0db4de`
- 上一版自行设计的前端脚本和样式已移除。

## 本次还原的边界

原文件本身是 localStorage 演示原型。本次原样还原也保留了这套演示逻辑；首页账号、角色切换、购物车、订单及管理操作尚未调用 Python 后端接口，不能当作真实商城使用。原有 FastAPI 后端仍保留，其测试通过不代表 V19 页面已与后端打通。后续对接必须以保持这个原版界面为前提。

原页面引用的外部商品图片仍来自原网址，实际显示取决于第三方资源可用性。不同浏览器、屏幕、已有 localStorage 数据也可能影响运行时显示。

## 运行与部署

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 即为原版首页。直接打开 `static/index.html` 也可运行原文件自带的演示。

仓库的 Dockerfile 和 Render Blueprint 继续保留。Render 部署仓库 main 分支后将提供此原版首页；Blueprint 使用付费服务及持久磁盘，部署前请查看平台价格。

FastAPI 接口文档位于 `/docs`。上一版后端说明保存在 [docs/backend-preview.md](docs/backend-preview.md)，其中针对重设计前端的说明属于历史版本，不适用于当前原版首页。

## 验证

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

还原测试验证首页文件与上传文件的固定 SHA-256、对照文件完全相同，并验证 `/` 的实际响应字节也相同。另有原后端的交易与并发测试。

本次校验结果：三组测试通过；原文件 11 段内联脚本通过 Node 语法检查。浏览器测试尝试因环境缺少 Playwright Chromium 可执行文件而未完成，因此未声称已做视觉截图对比。
