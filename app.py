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
    """从 URL 中提取文本，支持直接 PDF 链接和 PubMed 专门解析"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
    }
    try:
        response = requests.get(url, headers=headers, timeout=20, stream=True)
        response.raise_for_status()
        
        # 检查是否为 PDF 文件
        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
            pdf_content = io.BytesIO(response.content)
            return extract_text_from_pdf(pdf_content)
        
        # 针对 PubMed 的专门逻辑
        if "pubmed.ncbi.nlm.nih.gov" in url:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取标题
            title = soup.find('h1', class_='heading-title')
            title_text = title.get_text(strip=True) if title else ""
            
            # 提取摘要
            abstract_div = soup.find('div', id='abstract')
            if not abstract_div:
                abstract_div = soup.find('div', class_='abstract-content')
            
            abstract_text = ""
            if abstract_div:
                # 移除可能存在的 "Abstract" 标签
                for label in abstract_div.find_all('strong', class_='sub-title'):
                    label.decompose()
                abstract_text = abstract_div.get_text(separator='\n', strip=True)
            
            if title_text or abstract_text:
                return f"Title: {title_text}\n\nAbstract: {abstract_text}"

        # 否则尝试使用 trafilatura 提取网页文本
        # 注意：trafilatura 也可以接受自定义 headers，但它的 API 略有不同
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text:
                return text
        
        # 如果 trafilatura 失败，使用 BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        return soup.get_text(separator='\n', strip=True)
    except Exception as e:
        st.error(f"提取内容失败: {e}")
        return None

def summarize_paper(text, api_key):
    """调用阿里云 DashScope API 总结论文内容"""
    if not api_key:
        st.warning("请输入有效的阿里云 API Key。您可以在侧边栏输入。")
        return None

    dashscope.api_key = api_key
    
    prompt = f"""
    你是一个专业的学术论文助手。请对以下提供的论文内容（可能是全文、摘要或标题）进行核心观点总结。
    
    要求：
    1. 识别论文语言。如果是英文论文：
       - 输出英文题目 (Original Title)
       - 输出中文翻译后的题目 (Chinese Title)
       - 用中文详细总结论文的核心观点、研究背景、研究方法和主要结论。
    2. 如果论文是中文的：
       - 直接输出题目
       - 用中文详细总结论文的核心观点、研究背景、研究方法和主要结论。
    3. 如果提供的内容仅包含摘要，请基于摘要信息进行最全面的总结。
    
    待总结内容：
    {text[:12000]} # 稍微增加长度限制，Qwen-Max 支持较长上下文
    """

    try:
        with st.spinner("正在生成总结，请稍候..."):
            response = Generation.call(
                model='qwen-max', # 使用 Qwen-Max 模型以获得更好的总结效果
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
    st.markdown("---")
    st.info("本平台使用阿里云 Qwen 模型进行文本分析。")

# 主界面布局
tab1, tab2 = st.tabs(["🔗 输入网址", "📁 上传文件"])

with tab1:
    url_input = st.text_input("请输入论文网址 (URL)", placeholder="https://example.com/paper.pdf")
    if st.button("从网址总结", key="url_btn"):
        if url_input:
            content = extract_text_from_url(url_input)
            if content:
                st.session_state.summary = summarize_paper(content, api_key)
        else:
            st.warning("请输入有效的网址")

with tab2:
    uploaded_file = st.file_uploader("请选择 PDF 论文文件", type=["pdf"])
    if st.button("从文件总结", key="file_btn"):
        if uploaded_file:
            content = extract_text_from_pdf(uploaded_file)
            if content:
                st.session_state.summary = summarize_paper(content, api_key)
        else:
            st.warning("请先上传 PDF 文件")

# 显示结果
if st.session_state.summary:
    st.markdown("---")
    st.subheader("论文总结结果")
    st.markdown(st.session_state.summary)
    
    # 提供下载功能
    st.download_button(
        label="下载总结内容",
        data=st.session_state.summary,
        file_name="paper_summary.md",
        mime="text/markdown"
    )
