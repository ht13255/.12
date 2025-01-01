import streamlit as st
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
import os
import random

# 필터링 대상
EXCLUDED_DOMAINS = ["facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com"]
EXCLUDED_EXTENSIONS = [".pdf", ".docx", ".zip", ".exe", ".png", ".jpg", ".jpeg"]
EXCLUDED_SCHEMES = ["mailto:"]
EXCLUDED_KEYWORDS = ["guideline", "privacy", "cookies"]

# User-Agent 리스트
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6) AppleWebKit/605.1.15",
]

# HTTP 헤더 생성
def random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

# URL 유효성 검사 함수
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        if not parsed.netloc or not parsed.scheme:
            return False
        if any(parsed.path.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
            return False
        if any(keyword in url.lower() for keyword in EXCLUDED_KEYWORDS):
            return False
        if parsed.scheme not in ["http", "https"]:
            return False
        return True
    except Exception:
        return False

# 비동기 요청 함수
async def fetch_url(session, url):
    try:
        async with session.get(url, headers=random_headers(), timeout=10) as response:
            response.raise_for_status()
            return await response.text()
    except Exception as e:
        return None

# 비동기 링크 수집 함수
async def collect_links(base_url):
    visited = set()
    links_to_visit = [base_url]
    collected_links = []
    failed_links = []

    async with aiohttp.ClientSession() as session:
        while links_to_visit:
            url = links_to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            html = await fetch_url(session, url)
            if not html:
                failed_links.append({"url": url, "error": "요청 실패"})
                continue

            try:
                soup = BeautifulSoup(html, "html.parser")
                collected_links.append(url)

                for tag in soup.find_all("a", href=True):
                    href = urljoin(url, tag["href"]).strip()
                    if not is_valid_url(href) or href in visited or href in links_to_visit:
                        continue
                    if any(domain in urlparse(href).netloc for domain in EXCLUDED_DOMAINS):
                        continue

                    links_to_visit.append(href)
            except Exception as e:
                failed_links.append({"url": url, "error": f"HTML 파싱 오류: {e}"})

    return collected_links, failed_links

# 비동기 크롤링 함수
async def crawl_content(links):
    content_data = []
    async with aiohttp.ClientSession() as session:
        for link in links:
            html = await fetch_url(session, link)
            if not html:
                content_data.append({"url": link, "content": "요청 실패"})
                continue
            try:
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator="\n").strip()
                content_data.append({"url": link, "content": text})
            except Exception as e:
                content_data.append({"url": link, "content": f"HTML 파싱 오류: {e}"})

    return content_data

# 데이터 저장 함수
def save_data(data, file_format):
    try:
        file_path = f"crawled_content.{file_format}"
        if file_format == "json":
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        elif file_format == "csv":
            pd.DataFrame(data).to_csv(file_path, index=False, encoding="utf-8")
        elif file_format == "txt":
            with open(file_path, "w", encoding="utf-8") as f:
                for entry in data:
                    f.write(f"URL: {entry['url']}\n")
                    f.write(f"Content:\n{entry['content']}\n")
                    f.write("=" * 80 + "\n")
        return file_path
    except Exception as e:
        st.error(f"파일 저장 중 오류 발생: {e}")
        return None

# Streamlit 앱
st.title("크롤링 사이트")

# 세션 상태 초기화
if "step" not in st.session_state:
    st.session_state.step = 0
if "file_path" not in st.session_state:
    st.session_state.file_path = None
if "links" not in st.session_state:
    st.session_state.links = []
if "failed_links" not in st.session_state:
    st.session_state.failed_links = []
if "content" not in st.session_state:
    st.session_state.content = []

# 입력 필드
url_input = st.text_input("크롤링할 사이트 URL을 입력하세요:", placeholder="https://example.com")
file_format = st.radio("저장할 파일 형식 선택:", ["json", "csv", "txt"])
start_button = st.button("크롤링 시작")

# 크롤링 작업 실행
if start_button and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
    else:
        async def run_crawl():
            st.session_state.step = 1
            with st.spinner("링크를 수집 중입니다..."):
                collected_links, failed_links = await collect_links(url_input)
                st.session_state.links = collected_links
                st.session_state.failed_links = failed_links
                st.success("1단계 완료: 링크 수집 완료")

            st.session_state.step = 2
            with st.spinner("내용을 크롤링 중입니다..."):
                content = await crawl_content(st.session_state.links)
                st.session_state.content = content
                st.success("2단계 완료: 내용 크롤링 완료")

            st.session_state.step = 3
            with st.spinner("데이터를 저장 중입니다..."):
                file_path = save_data(st.session_state.content, file_format)
                st.session_state.file_path = file_path
                st.success("3단계 완료: 데이터 저장 완료")

        asyncio.run(run_crawl())

# 다운로드 버튼 유지
if st.session_state.step == 3 and st.session_state.file_path:
    with open(st.session_state.file_path, "rb") as f:
        st.download_button(
            label="크롤링 결과 다운로드",
            data=f,
            file_name=st.session_state.file_path,
            mime="application/json" if st.session_state.file_path.endswith("json") else
                 "text/csv" if st.session_state.file_path.endswith("csv") else
                 "text/plain",
        )
