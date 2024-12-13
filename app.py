import streamlit as st
import threading
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from io import BytesIO

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
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "result_data" not in st.session_state:
    st.session_state.result_data = None

# 링크를 수집하는 함수
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

# 요청 및 컨텐츠 가져오기 함수
def fetch_content(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        return None

# 멀티스레드 크롤링 함수
def crawl_content_multithread(links):
    content_data = []

    def fetch_and_parse_content(link):
        html = fetch_content(link)
        if html:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                text = soup.get_text(separator="\n").strip()
                return {"url": link, "content": text}
            except Exception:
                return {"url": link, "content": "Error parsing content"}
        else:
            return {"url": link, "content": "Error fetching content"}

    content_data = [fetch_and_parse_content(link) for link in links]
    return content_data

# 백그라운드에서 실행될 함수
def background_task(url, exclude_external):
    st.session_state.is_running = True
    links, failed_links = collect_links(url, exclude_external)
    if links:
        result = crawl_content_multithread(links)
        st.session_state.result_data = result
    else:
        st.session_state.result_data = []
    st.session_state.is_running = False

# UI
st.title("크롤링 사이트")
st.markdown("**백그라운드 모드 또는 실시간 모드를 선택하여 작업을 수행하세요.**")

# 옵션 선택
mode = st.radio("작업 모드 선택", ["온라인 모드 (실시간 진행)", "백그라운드 모드"])
url_input = st.text_input("크롤링할 사이트 URL", placeholder="https://example.com")
exclude_external = st.checkbox("외부 링크 제외", value=False)
max_threads = st.slider("스레드 개수 설정 (최대 100)", min_value=5, max_value=100, value=20, step=1)
start_crawl = st.button("크롤링 시작")

# 온라인 모드
if mode == "온라인 모드 (실시간 진행)" and start_crawl and url_input:
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
        with st.spinner("내용을 크롤링 중입니다..."):
            content = crawl_content_multithread(links)

        if content:
            st.success("크롤링 완료! 데이터를 다운로드하세요.")
            file_format = st.selectbox("저장할 파일 형식 선택", ["json", "csv"])
            buffer = BytesIO()
            if file_format == "json":
                json.dump(content, buffer, ensure_ascii=False, indent=4)
                buffer.seek(0)
                st.download_button(
                    label="JSON 파일 다운로드",
                    data=buffer,
                    file_name="crawled_content.json",
                    mime="application/json"
                )
            elif file_format == "csv":
                df = pd.DataFrame(content)
                df.to_csv(buffer, index=False, encoding="utf-8")
                buffer.seek(0)
                st.download_button(
                    label="CSV 파일 다운로드",
                    data=buffer,
                    file_name="crawled_content.csv",
                    mime="text/csv"
                )

# 백그라운드 모드
elif mode == "백그라운드 모드" and start_crawl and url_input:
    if not st.session_state.is_running:
        thread = threading.Thread(target=background_task, args=(url_input, exclude_external))
        thread.start()
        st.success("백그라운드 작업이 시작되었습니다. 완료되면 데이터를 다운로드할 수 있습니다.")
    else:
        st.warning("이미 작업이 실행 중입니다. 완료를 기다려주세요.")

# 백그라운드 작업 상태 표시
if mode == "백그라운드 모드":
    if st.session_state.is_running:
        st.info("작업이 실행 중입니다. 잠시만 기다려주세요...")
    elif st.session_state.result_data is not None:
        st.success("백그라운드 작업이 완료되었습니다! 데이터를 다운로드하세요.")
        file_format = st.selectbox("저장할 파일 형식 선택", ["json", "csv"])
        buffer = BytesIO()
        if file_format == "json":
            json.dump(st.session_state.result_data, buffer, ensure_ascii=False, indent=4)
            buffer.seek(0)
            st.download_button(
                label="JSON 파일 다운로드",
                data=buffer,
                file_name="crawled_content.json",
                mime="application/json"
            )
        elif file_format == "csv":
            df = pd.DataFrame(st.session_state.result_data)
            df.to_csv(buffer, index=False, encoding="utf-8")
            buffer.seek(0)
            st.download_button(
                label="CSV 파일 다운로드",
                data=buffer,
                file_name="crawled_content.csv",
                mime="text/csv"
            )