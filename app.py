import streamlit as st
import dashscope
from dashscope import Generation
from pypdf import PdfReader
import requests
from bs4 import BeautifulSoup
import trafilatura
import io
import os
from http import HTTPStatus
from urllib.parse import urlparse
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    st.error("缺失依赖库: python-dotenv。请运行 'pip install python-dotenv' 安装。")

# 设置页面配置
st.set_page_config(page_title="论文核心观点总结平台", page_icon="📚", layout="wide")

# 初始化 Session State
if 'summary' not in st.session_state:
    st.session_state.summary = None

def extract_text_from_pdf(file):
    """从 PDF 文件中提取文本"""
    try:
        pdf_reader = PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"解析 PDF 失败: {e}")
        return None

def extract_text_from_url(url):
    """从 URL 中提取文本，支持直接 PDF 链接 - 增强版，针对云端优化"""
    try:
        # 1. 定义完整的浏览器请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        # 2. 针对常见学术网站设置 Referer
        parsed_url = urlparse(url)
        if 'ncbi.nlm.nih.gov' in parsed_url.netloc:
            headers['Referer'] = 'https://www.ncbi.nlm.nih.gov/'
        elif 'arxiv.org' in parsed_url.netloc:
            headers['Referer'] = 'https://arxiv.org/'
        elif 'nature.com' in parsed_url.netloc:
            headers['Referer'] = 'https://www.nature.com/'
        elif 'science.org' in parsed_url.netloc:
            headers['Referer'] = 'https://www.science.org/'
        elif 'springer.com' in parsed_url.netloc or 'link.springer.com' in parsed_url.netloc:
            headers['Referer'] = 'https://link.springer.com/'
        elif 'ieee.org' in parsed_url.netloc or 'ieeexplore.ieee.org' in parsed_url.netloc:
            headers['Referer'] = 'https://ieeexplore.ieee.org/'
        
        # 3. 检查是否为 PDF 文件
        if url.lower().endswith('.pdf'):
            response = requests.get(url, headers=headers, timeout=15, stream=True)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                pdf_content = io.BytesIO(response.content)
                return extract_text_from_pdf(pdf_content)
        
        # 4. 首先尝试使用 trafilatura 提取（针对HTML页面）
        downloaded = trafilatura.fetch_url(url, headers=headers, timeout=15)
        if downloaded:
            text = trafilatura.extract(
                downloaded,
                include_links=False,
                include_tables=False,
                no_fallback=False
            )
            if text and len(text.strip()) > 200:  # 确保提取到足够长的文本
                return text
        
        # 5. 如果 trafilatura 失败，使用 requests + BeautifulSoup
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 移除脚本、样式等无关元素
        for script in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            script.decompose()
        
        # 尝试提取文章正文
        article_content = ""
        
        # 常见学术网站的正文选择器
        article_selectors = [
            'article', 
            '.article-content', 
            '.article-body',
            '.main-content',
            '#content', 
            '.content',
            '.pdf-viewer',
            '.abstract',
            '.fulltext',
            '[role="main"]',
            'main',
            '.document',
            '.entry-content'
        ]
        
        for selector in article_selectors:
            elements = soup.select(selector)
            if elements:
                for element in elements:
                    article_content += element.get_text(separator='\n', strip=True) + "\n"
        
        # 如果没找到特定元素，获取整个页面文本
        if not article_content or len(article_content.strip()) < 200:
            article_content = soup.get_text(separator='\n', strip=True)
        
        # 清理文本：移除过多空行
        lines = [line.strip() for line in article_content.split('\n') if line.strip()]
        cleaned_text = '\n'.join(lines)
        
        return cleaned_text if cleaned_text else None
        
    except Exception as e:
        st.error(f"提取内容失败: {e}")
        # 打印详细错误信息到控制台
        import traceback
        st.error(f"详细错误: {traceback.format_exc()}")
        return None

def summarize_paper(text, api_key):
    """调用阿里云 DashScope API 总结论文内容"""
    if not api_key:
        st.warning("请输入有效的阿里云 API Key。您可以在侧边栏输入。")
        return None

    dashscope.api_key = api_key
    
    # 截断文本，防止超过模型限制
    max_text_length = 12000
    if len(text) > max_text_length:
        text = text[:max_text_length]
        st.info(f"文本过长，已截断前{max_text_length}个字符进行总结。")
    
    prompt = f"""
    你是一个专业的学术论文助手。请对以下论文内容进行核心观点总结。
    
    要求：
    1. 如果论文是英文的：
      - 输出英文题目 (Original Title)
      - 输出中文翻译后的题目 (Chinese Title)
      - 用中文总结论文的核心观点、研究方法和主要结论。
    2. 如果论文是中文的：
      - 直接输出题目
      - 用中文总结论文的核心观点、研究方法和主要结论。
    
    输出格式：
    - 核心观点：...
    - 研究方法：...
    - 主要结论：...
    - 创新点：...
    - 研究意义：...
    
    待总结内容：
    {text}
    """

    try:
        with st.spinner("正在生成总结，请稍候..."):
            response = Generation.call(
                model='qwen-max',
                prompt=prompt,
                result_format='message'
            )
            
            if response.status_code == HTTPStatus.OK:
                return response.output.choices[0].message.content
            else:
                st.error(f"API 调用失败: {response.code} - {response.message}")
                return None
    except Exception as e:
        st.error(f"发生错误: {e}")
        return None

# UI 界面
st.title("📚 简易论文核心观点总结平台")
st.markdown("快速获取论文精髓，支持 PDF 文件上传和网页链接提取。")

# 侧边栏配置
with st.sidebar:
    st.header("配置项")
    # 优先从环境变量 (.env 文件) 加载，如果没有则为空
    env_api_key = os.getenv("DASHSCOPE_API_KEY")
    default_api_key = env_api_key if env_api_key else ""
    
    api_key = st.text_input(
        "阿里云 API Key", 
        value=default_api_key, 
        type="password", 
        help="在阿里云百炼控制台获取 API Key"
    )
    
    # 添加抓取选项
    st.markdown("---")
    st.header("抓取设置")
    timeout = st.slider("请求超时时间(秒)", 10, 30, 15)
    enable_debug = st.checkbox("启用调试模式", value=False)
    
    st.markdown("---")
    st.info("本平台使用阿里云 Qwen 模型进行文本分析。")
    
    # 显示当前配置状态
    if env_api_key:
        st.success("✅ API Key 已从环境变量加载")
    elif api_key and len(api_key) > 10:
        st.success("✅ API Key 已从侧边栏输入")

# 主界面布局
tab1, tab2 = st.tabs(["🔗 输入网址", "📁 上传文件"])

with tab1:
    st.markdown("### 从网页链接抓取")
    st.markdown("支持 PubMed, arXiv, Nature, Science, Springer, IEEE 等学术网站")
    
    # 示例链接
    with st.expander("点击查看示例链接"):
        st.markdown("""
        - PubMed Central: `https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9662541/`
        - arXiv: `https://arxiv.org/abs/2303.08774`
        - Nature: `https://www.nature.com/articles/s41586-023-06499-2`
        - 普通新闻: `https://news.sciencenet.cn/htmlnews/2023/10/511023.shtm`
        """)
    
    url_input = st.text_input("请输入论文网址 (URL)", 
                             placeholder="https://example.com/paper.pdf 或 https://arxiv.org/abs/2303.08774")
    
    if st.button("从网址总结", key="url_btn", type="primary"):
        if url_input:
            with st.spinner(f"正在抓取 {url_input} 的内容..."):
                content = extract_text_from_url(url_input)
                if content:
                    st.success(f"✅ 成功抓取 {len(content)} 个字符")
                    
                    # 显示部分预览
                    with st.expander("预览抓取的内容"):
                        st.text(content[:1000] + "..." if len(content) > 1000 else content)
                    
                    st.session_state.summary = summarize_paper(content, api_key)
                else:
                    st.error("❌ 无法从该网址提取有效内容，请检查网址或尝试其他链接。")
        else:
            st.warning("请输入有效的网址")

with tab2:
    st.markdown("### 上传PDF文件")
    uploaded_file = st.file_uploader("请选择 PDF 论文文件", type=["pdf"])
    
    if st.button("从文件总结", key="file_btn", type="primary"):
        if uploaded_file:
            with st.spinner(f"正在解析 {uploaded_file.name}..."):
                content = extract_text_from_pdf(uploaded_file)
                if content:
                    st.success(f"✅ 成功解析 {len(content)} 个字符")
                    st.session_state.summary = summarize_paper(content, api_key)
                else:
                    st.error("❌ 无法解析PDF文件，请检查文件格式。")
        else:
            st.warning("请先上传 PDF 文件")

# 显示结果
if st.session_state.summary:
    st.markdown("---")
    st.subheader("📄 论文总结结果")
    
    # 美化显示
    st.markdown("### 📋 总结内容")
    st.markdown(st.session_state.summary)
    
    # 提供下载功能
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 下载总结内容 (Markdown)",
            data=st.session_state.summary,
            file_name="paper_summary.md",
            mime="text/markdown"
        )
    with col2:
        st.download_button(
            label="📥 下载总结内容 (TXT)",
            data=st.session_state.summary,
            file_name="paper_summary.txt",
            mime="text/plain"
        )
    
    # 重置按钮
    if st.button("🔄 重新开始"):
        st.session_state.summary = None
        st.rerun()
