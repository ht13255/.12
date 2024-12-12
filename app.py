import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from threading import Thread
from io import BytesIO
import time

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

# 세션 상태 초기화
if "task_status" not in st.session_state:
    st.session_state.task_status = "idle"  # idle, running, completed
if "collected_data" not in st.session_state:
    st.session_state.collected_data = None  # 작업 완료된 데이터
if "error_logs" not in st.session_state:
    st.session_state.error_logs = []

# 링크 수집 함수
def collect_links(base_url, exclude_external=False):
    base_domain = urlparse(base_url).netloc
    visited = set()
    links_to_visit = [base_url]
    collected_links = []
    failed_links = []  # 수집 실패한 링크 기록

    while links_to_visit:
        url = links_to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
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

# 데이터 저장 함수
def save_data_to_memory(data, file_format):
    buffer = BytesIO()
    if file_format == "json":
        json.dump(data, buffer, ensure_ascii=False, indent=4)
        mime_type = "application/json"
    elif file_format == "csv":
        df = pd.DataFrame(data)
        df.to_csv(buffer, index=False, encoding="utf-8")
        mime_type = "text/csv"
    buffer.seek(0)
    return buffer, mime_type

# 백그라운드 작업 함수
def run_crawling_task(base_url, exclude_external, max_threads):
    st.session_state.task_status = "running"
    try:
        collected_links, failed_links = collect_links(base_url, exclude_external)
        st.session_state.collected_data = {"links": collected_links, "failed": failed_links}
        st.session_state.task_status = "completed"
    except Exception as e:
        st.session_state.error_logs.append(str(e))
        st.session_state.task_status = "idle"

# UI
st.title("크롤링 사이트")
st.markdown("**백그라운드에서 안전하게 크롤링 작업을 수행합니다.**")

# 입력 UI
url_input = st.text_input("크롤링할 URL", placeholder="https://example.com")
exclude_external = st.checkbox("외부 링크 제외", value=False)
max_threads = st.slider("멀티스레드 개수 (최대 100)", 5, 100, 20, step=1)
file_format = st.selectbox("저장할 파일 형식", ["json", "csv"])

# 작업 상태 표시
if st.session_state.task_status == "idle":
    st.info("작업 대기 중")
elif st.session_state.task_status == "running":
    st.warning("작업 진행 중... 창을 닫아도 작업은 계속됩니다.")
elif st.session_state.task_status == "completed":
    st.success("작업 완료! 데이터를 다운로드하세요.")

# 작업 시작 버튼
if st.button("작업 시작"):
    if not url_input:
        st.error("크롤링할 URL을 입력하세요.")
    elif st.session_state.task_status == "running":
        st.warning("이미 작업이 진행 중입니다.")
    else:
        thread = Thread(target=run_crawling_task, args=(url_input, exclude_external, max_threads), daemon=True)
        thread.start()

# 작업 결과 다운로드
if st.session_state.task_status == "completed" and st.session_state.collected_data:
    memory_buffer, mime_type = save_data_to_memory(st.session_state.collected_data, file_format)
    st.download_button(
        label=f"결과 다운로드 ({file_format.upper()})",
        data=memory_buffer,
        file_name=f"crawled_content.{file_format}",
        mime=mime_type
    )