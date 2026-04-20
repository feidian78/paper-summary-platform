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
    """从 URL 中提取文本，增强对 PubMed 的抓取鲁棒性"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    try:
        # 使用 allow_redirects=True 确保处理所有重定向
        response = requests.get(url, headers=headers, timeout=25, stream=True, allow_redirects=True)
        response.raise_for_status()
        
        # 检查是否为 PDF 文件
        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
            pdf_content = io.BytesIO(response.content)
            return extract_text_from_pdf(pdf_content)
        
        # 针对 PubMed 的增强抓取逻辑
        if "pubmed.ncbi.nlm.nih.gov" in url or "PubMed" in response.text:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. 提取标题 (尝试多种可能的选择器)
            title_text = ""
            title_selectors = ['h1.heading-title', 'h1.title', 'div.article-page h1']
            for selector in title_selectors:
                title_node = soup.select_one(selector)
                if title_node:
                    title_text = title_node.get_text(strip=True)
                    break
            
            # 2. 提取摘要 (尝试多种可能的选择器)
            abstract_text = ""
            abstract_selectors = [
                'div#abstract', 
                'div.abstract-content', 
                'div.abstract', 
                'section.abstract',
                'div#enc-abstract'
            ]
            for selector in abstract_selectors:
                abstract_node = soup.select_one(selector)
                if abstract_node:
                    # 清理：移除内部的小标题如 "Abstract", "Background" 等
                    for label in abstract_node.select('strong.sub-title, b, strong'):
                        # 如果文本太短，通常是小标题，我们保留文本但增加换行
                        label.insert_before('\n')
                        label.insert_after(' ')
                    
                    abstract_text = abstract_node.get_text(separator=' ', strip=True)
                    if len(abstract_text) > 50: # 确保抓到的是有意义的内容
                        break
            
            # 3. 提取作者和期刊信息（可选，增加上下文）
            journal_node = soup.select_one('button#full-view-journal-trigger')
            journal_text = journal_node.get_text(strip=True) if journal_node else ""
            
            if title_text or abstract_text:
                combined_content = f"Title: {title_text}\n"
                if journal_text:
                    combined_content += f"Journal: {journal_text}\n"
                combined_content += f"\nAbstract/Content:\n{abstract_text}"
                
                # 如果抓取的内容太少，可能是遇到了反爬或重定向页
                if len(combined_content) < 100:
                    st.warning("抓取到的内容过短，可能是遇到了网页重定向。")
                else:
                    return combined_content

        # 兜底方案 1: 使用 trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text and len(text) > 200:
                return text
        
        # 兜底方案 2: 使用 BeautifulSoup 提取所有正文文本
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # 针对 PubMed 的重定向提示页特殊处理
        if "redirect" in response.text.lower() and "click here" in response.text.lower():
            st.error("检测到网页重定向提示，请尝试直接复制论文摘要文本到此处总结。")
            return None
            
        text = soup.get_text(separator='\n', strip=True)
        return text if len(text) > 50 else None
        
    except Exception as e:
        st.error(f"提取内容失败: {e}")
        return None

def summarize_paper(text, api_key):
    """调用阿里云 DashScope API 总结论文内容"""
    if not api_key:
        st.warning("请输入有效的阿里云 API Key。您可以在侧边栏输入。")
        return None

    if not text or len(text.strip()) < 50:
        st.error("提取到的文本内容太少，无法进行总结。请检查链接是否有效，或者尝试直接上传 PDF。")
        return None
    
    # 进一步检查内容是否像是重定向提示
    redirection_keywords = ["redirect", "click here", "browser", "javascript"]
    if any(kw in text.lower() for kw in redirection_keywords) and len(text) < 300:
        st.warning("提取的内容可能包含重定向信息。如果总结结果不理想，请尝试直接复制摘要文本。")

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
    show_debug = st.checkbox("显示抓取原文 (调试用)", value=False)
    st.info("本平台使用阿里云 Qwen 模型进行文本分析。")

# 主界面布局
tab1, tab2 = st.tabs(["🔗 输入网址", "📁 上传文件"])

with tab1:
    url_input = st.text_input("请输入论文网址 (URL)", placeholder="https://example.com/paper.pdf")
    if st.button("从网址总结", key="url_btn"):
        if url_input:
            content = extract_text_from_url(url_input)
            if content:
                if show_debug:
                    with st.expander("抓取到的原文内容"):
                        st.text(content[:2000] + "...")
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
