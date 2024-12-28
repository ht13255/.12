import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
import random

# 필터링 대상
EXCLUDED_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com",
    "google.com", "whatsapp.com", "telegram.org", "pinterest.com", "snapchat.com", "reddit.com",
    "bet", "casino", "gamble", "lotto"
]
EXCLUDED_EXTENSIONS = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".exe", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".txt"]
EXCLUDED_SCHEMES = ["mailto:"]  # 메일 링크 제외
EXCLUDED_KEYWORDS = ["guideline", "terms", "policy", "privacy", "cookies"]

# User-Agent 리스트
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1",
]

# HTTP 헤더 다양화
def random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

# URL 유효성 검사 함수
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc) and bool(parsed.scheme)
    except Exception:
        return False

# 링크를 수집하는 함수
def collect_links(base_url, progress_placeholder):
    visited = set()
    links_to_visit = [base_url]
    collected_links = []
    failed_links = []
    total_links = 1  # 시작 링크 포함

    while links_to_visit:
        url = links_to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            headers = random_headers()
            response = requests.get(url, headers=headers, timeout=3)
            response.raise_for_status()
        except requests.RequestException as e:
            failed_links.append({"url": url, "error": str(e)})
            continue

        try:
            soup = BeautifulSoup(response.text, "html.parser")
            collected_links.append(url)

            for tag in soup.find_all("a", href=True):
                href = urljoin(url, tag["href"])
                parsed_href = urlparse(href)

                if any(domain in parsed_href.netloc for domain in EXCLUDED_DOMAINS):
                    continue
                if any(href.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
                    continue
                if any(keyword in href.lower() for keyword in EXCLUDED_KEYWORDS):
                    continue
                if parsed_href.scheme in EXCLUDED_SCHEMES:
                    continue
                if href not in visited and href not in links_to_visit:
                    links_to_visit.append(href)
                    total_links += 1

            # 진행률 업데이트
            progress_placeholder.progress(len(visited) / total_links)

        except Exception as e:
            failed_links.append({"url": url, "error": f"HTML 파싱 오류: {e}"})

    return collected_links, failed_links

# 멀티스레딩을 이용한 내용 크롤링 함수
def crawl_content_multithread(links, progress_placeholder):
    content_data = []
    total_links = len(links)
    completed = 0

    def fetch_and_parse(link):
        nonlocal completed
        try:
            headers = random_headers()
            response = requests.get(link, headers=headers, timeout=3)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(separator="\n").strip()
            result = {"url": link, "content": text}
        except Exception as e:
            result = {"url": link, "content": f"HTML 가져오기 실패: {e}"}
        finally:
            completed += 1
            progress_placeholder.progress(completed / total_links)
        return result

    max_threads = os.cpu_count() or 4
    with ThreadPoolExecutor(max_workers=max_threads * 2) as executor:  # 멀티스레드 최대로 확장
        content_data.extend(executor.map(fetch_and_parse, links))

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
        return file_path
    except Exception as e:
        st.error(f"파일 저장 중 오류 발생: {e}")
        return None

# Streamlit 앱
st.title("크롤링 사이트")
st.write("오류를 최대한 방지한 안정적인 고속 크롤러입니다.")

# 입력 필드
url_input = st.text_input("크롤링할 사이트 URL을 입력하세요:", placeholder="https://example.com")
file_format = st.radio("저장할 파일 형식 선택:", ["json", "csv"])
start_button = st.button("크롤링 시작")

# 세션 상태에서 파일 경로 유지
if "file_path" not in st.session_state:
    st.session_state.file_path = None

if start_button and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
    else:
        progress_placeholder = st.empty()
        progress_bar = st.progress(0)

        with st.spinner("링크를 수집 중입니다..."):
            try:
                links, failed_links = collect_links(url_input, progress_bar)
                st.success("1단계 완료: 링크 수집 완료")
            except Exception as e:
                st.error(f"링크 수집 중 오류 발생: {e}")
                links, failed_links = [], []

        if links:
            st.success(f"수집된 링크 수: {len(links)}")
            if failed_links:
                st.warning(f"수집 실패한 링크 수: {len(failed_links)}")

            with st.spinner("내용을 크롤링 중입니다..."):
                try:
                    content = crawl_content_multithread(links, progress_bar)
                    st.success("2단계 완료: 내용 크롤링 완료")
                except Exception as e:
                    st.error(f"크롤링 중 오류 발생: {e}")
                    content = []

            if content:
                file_path = save_data(content, file_format)
                if file_path:
                    st.session_state.file_path = file_path
                    st.success("3단계 완료: 데이터 저장 완료")
                else:
                    st.error("파일 저장 중 오류가 발생했습니다.")

if st.session_state.file_path:
    with open(st.session_state.file_path, "rb") as f:
        st.download_button(
            label="크롤링 결과 다운로드",
            data=f,
            file_name=st.session_state.file_path,
            mime="application/json" if st.session_state.file_path.endswith("json") else "text/csv"
        )