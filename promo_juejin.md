# 我做了一个 AI 代码检测工具：输入 GitHub 链接，一键识别 AI 生成的"屎山"

## 起因

最近 GitHub 上出现大量 AI 生成的仓库——README 写得很唬人，号称"生产就绪""企业级"，点进去一看：

- 整个项目只有 2 次提交就把所有代码塞完
- 变量名全是 `data`、`temp`、`result`
- `// increment i` 这种废话注释满天飞
- 0 个测试文件，README 却说"well-tested"
- import 了一些根本不存在的包

我把这些特征整理了 9 个指标，做了一个工具自动检测。

## 怎么用

三步：

```bash
git clone https://github.com/Leo-Ayh-Oday/slop-detector
pip install -r requirements.txt
python server.py
```

然后把 `extension/` 文件夹拖进 Chrome/Edge 扩展管理页面，完事。

之后浏览任意 GitHub 仓库，点一下扩展图标就能看到分析报告：

![分析报告](https://raw.githubusercontent.com/Leo-Ayh-Oday/slop-detector/main/images/screenshot.png)

## 检测什么

| 指标 | 检测逻辑 |
|------|---------|
| 提交炸弹 | 所有代码 1-2 次提交塞完，逐步开发的痕迹为零 |
| 命名质量 | 变量名是否大量使用 data/temp/foo/result 等泛词 |
| 废话注释 | `// set the value` 这种注释占比是否超 40% |
| 测试覆盖 | 有测试文件吗？README 是不是在吹牛？ |
| 幽灵依赖 | import 的包在 PyPI/npm 上真的存在吗？ |
| 贡献者分布 | 整个仓库是不是只有一个人？ |
| 模板残留 | 文件结构是不是脚手架模板原封不动？ |
| 分支管理 | 分支名是否全是 fix/update/wip 这种东西？ |
| 占位符密度 | TODO/pass/NotImplementedError 是不是太多了？ |

每个指标 0-10 分，加权计算总分 0-100。分数越低越可疑。

## 实际效果

拿"slop-detector"这个仓库自己测了一下：**42 分，可疑。** 哈哈，诚实。

测了几个真人工写的高 star 项目基本都是 85+。

## 技术栈

- **后端**：Python FastAPI + tree-sitter AST 解析 + gitpython
- **前端**：原生 JS Chrome/Edge 扩展（Manifest V3）
- **评分**：9 个启发式检测器，纯本地计算，不调 API

代码 100% 本地运行，数据不出电脑。不需要任何 API Key。

## 价格

- 免费 3 次完整分析
- 无限次：**¥35 永久买断**
- 觉得有用再付，觉得没用白嫖 3 次也不亏

加微信 **f01290724**，转账后发激活码，粘贴解锁。

---

GitHub: [https://github.com/Leo-Ayh-Oday/slop-detector](https://github.com/Leo-Ayh-Oday/slop-detector)

欢迎试用，拍砖，提 issue。
