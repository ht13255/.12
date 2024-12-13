import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import os

# 제외할 도메인, 키워드 및 파일 확장자
EXCLUDED_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com",
    "whatsapp.com", "telegram.org", "messenger.com", "pinterest.com", "reddit.com",
    "youtube.com", "snapchat.com", "weibo.com", "wechat.com", "line.me"
]
EXCLUDED_KEYWORDS = ["login", "signin", "signup", "auth", "oauth", "account", "register"]
EXCLUDED_FILE_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".zip", ".rar", ".tar", ".gz"]
EXCLUDED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".svg"]

# 사용자 에이전트 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}

# 링크를 수집하는 함수
def collect_links(base_url, exclude_external=False):
    base_domain = urlparse(base_url).netloc
    visited = set()
    links_to_visit = [base_url]
    collected_links = []
    failed_links = []  # 수집 실패한 링크 기록

    with requests.Session() as session:
        session.headers.update(HEADERS)
        while links_to_visit:
            url = links_to_visit.pop()
            if url in visited:
                continue
            visited.add(url)

            try:
                response = session.get(url, timeout=10)
                response.raise_for_status()
            except requests.exceptions.RequestException:
                failed_links.append(url)
                continue

            try:
                soup = BeautifulSoup(response.text, 'html.parser')
                collected_links.append(url)

                for tag in soup.find_all('a', href=True):
                    href = urljoin(url, tag['href'])
                    parsed_href = urlparse(href)

                    if any(domain in parsed_href.netloc for domain in EXCLUDED_DOMAINS):
                        continue
                    if exclude_external and parsed_href.netloc != base_domain:
                        continue
                    if href.startswith("mailto:") or any(href.endswith(ext) for ext in EXCLUDED_FILE_EXTENSIONS + EXCLUDED_IMAGE_EXTENSIONS):
                        continue
                    if not parsed_href.scheme in ["http", "https"]:
                        continue
                    if any(keyword in parsed_href.path.lower() for keyword in EXCLUDED_KEYWORDS):
                        continue
                    if href not in visited and href not in links_to_visit:
                        links_to_visit.append(href)
            except Exception:
                failed_links.append(url)
    return collected_links, failed_links

# 요청 및 컨텐츠 가져오기 함수
def fetch_content(url, session, retries=3):
    for _ in range(retries):
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            continue
    return None

# 멀티스레딩을 이용한 내용 크롤링 함수
def crawl_content_multithread(links, max_threads=100, progress_bar=None):
    content_data = []

    def fetch_and_parse_content(link, session):
        html = fetch_content(link, session)
        if html:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                text = soup.get_text(separator="\n").strip()
                return {"url": link, "content": text}
            except Exception:
                return {"url": link, "content": "Error parsing content"}
        else:
            return {"url": link, "content": "Error fetching content"}

    total_links = len(links)
    with requests.Session() as session:
        session.headers.update(HEADERS)
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = {executor.submit(fetch_and_parse_content, link, session): link for link in links}
            for idx, future in enumerate(as_completed(futures)):
                try:
                    content_data.append(future.result())
                except Exception as e:
                    content_data.append({"url": futures[future], "content": f"Error: {e}"})
                if progress_bar:
                    progress_bar.progress((idx + 1) / total_links)

    return content_data

# 데이터 저장 함수 (JSON 및 CSV)
def save_data_to_memory(data, file_format):
    try:
        buffer = BytesIO()
        if file_format == "json":
            json.dump(data, buffer, ensure_ascii=False, indent=4)
            buffer.seek(0)
            return buffer, "application/json"
        elif file_format == "csv":
            df = pd.DataFrame(data)
            df.to_csv(buffer, index=False, encoding="utf-8")
            buffer.seek(0)
            return buffer, "text/csv"
    except Exception as e:
        st.error(f"데이터 저장 중 오류 발생: {e}")
        return None, None

# URL 유효성 검사 함수
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc) and bool(parsed.scheme)
    except Exception:
        return False

# Streamlit 앱
st.title("크롤링 사이트")
st.markdown("**웹사이트 링크를 크롤링하고 결과를 JSON 또는 CSV 형식으로 저장할 수 있습니다.**")

with st.sidebar:
    st.header("옵션 설정")
    url_input = st.text_input("크롤링할 사이트 URL", placeholder="https://example.com")
    exclude_external = st.checkbox("외부 링크 제외", value=False)
    max_threads = st.slider("스레드 개수 설정 (최대 500)", min_value=5, max_value=500, value=os.cpu_count() * 2, step=1)
    file_format = st.selectbox("저장할 파일 형식 선택", ["json", "csv"])
    start_crawl = st.button("크롤링 시작")

if start_crawl and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
        st.stop()

    with st.spinner("링크를 수집 중입니다..."):
        links, failed_links = collect_links(url_input, exclude_external)

    with st.expander("수집된 링크 보기"):
        if links:
            st.write(f"**수집된 링크 수**: {len(links)}")
            st.write(links)
        if failed_links:
            st.write(f"**수집 실패한 링크 수**: {len(failed_links)}")
            st.write(failed_links)

    if links:
        st.write("### 내용 크롤링 진행 상황")
        progress_bar = st.progress(0)  # 진행 상태 표시
        with st.spinner("내용을 크롤링 중입니다..."):
            content = crawl_content_multithread(links, max_threads=max_threads, progress_bar=progress_bar)

        if content:
            st.success("크롤링 완료! 데이터를 다운로드하세요.")
            memory_buffer, mime_type = save_data_to_memory(content, file_format)
            if memory_buffer:
                st.download_button(
                    label=f"크롤링 결과 다운로드 ({file_format.upper()})",
                    data=memory_buffer,
                    file_name=f"crawled_content.{file_format}",
                    mime=mime_type
                )