# 📚 简易论文核心观点总结平台

这是一个基于 Python 和 Streamlit 开发的简易平台，旨在帮助研究人员快速总结学术论文的核心观点。

## 功能特点

- **多端输入**：支持通过论文网址 (URL) 或直接上传 PDF 文件。
- **智能总结**：调用阿里云 DashScope (Qwen-Max) API 进行深度内容分析。
- **中英支持**：
  - 英文论文：输出英文题目、中文翻译题目、中文总结。
  - 中文论文：输出题目、中文总结。
- **一键下载**：支持将生成的总结内容导出为 Markdown 文件。

## 安装步骤

1.  **克隆或下载本项目**到本地。
2.  **安装依赖项**：
    建议在虚拟环境中运行：
    ```bash
    pip install -r requirements.txt
    ```
3.  **获取阿里云 API Key**：
    - 登录[阿里云百炼控制台](https://bailian.console.aliyun.com/)。
    - 获取并复制你的 API Key。

## 运行方式

在终端（Terminal）中执行以下命令启动应用：

```powershell
streamlit run app.py
```

> **注意**：如果您在 PowerShell 中遇到 `&` 相关的错误，请确保您是在直接输入命令，而不是粘贴带有多余符号的代码块。

## 环境变量配置

我们已在 `.env` 文件中配置了您的 API Key：
```text
DASHSCOPE_API_KEY=sk-aa260b75cee24d0795f1da729a991c99
```
程序启动后会自动加载此 Key。

1.  启动应用后，在侧边栏输入你的**阿里云 API Key**。
2.  选择“输入网址”或“上传文件”标签页。
3.  输入网址或上传 PDF 文件，点击对应的总结按钮。
4.  等待系统处理完成后，即可查看论文的核心观点总结，并支持下载。

## 技术栈

- **前端/框架**：[Streamlit](https://streamlit.io/)
- **大模型 API**：[阿里云 DashScope (Qwen-Max)](https://help.aliyun.com/zh/dashscope/)
- **PDF 解析**：[pypdf](https://pypi.org/project/pypdf/)
- **网页提取**：[trafilatura](https://pypi.org/project/trafilatura/)
