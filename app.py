import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import random
import time

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

# URL 유효성 검사
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        # URL 길이 제한 (2048자 이하) 및 스키마 검사
        if len(url) > 2048 or not parsed.scheme in ["http", "https"]:
            return False
        # 유효한 netloc 확인
        if not parsed.netloc or not parsed.path:
            return False
        return True
    except Exception:
        return False

# 링크 수집 함수
def collect_links(base_url, progress_placeholder):
    visited = set()
    links_to_visit = [base_url]
    collected_links = []
    failed_links = []
    total_links = 1

    while links_to_visit:
        url = links_to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            headers = random_headers()
            response = requests.get(url, headers=headers, timeout=5)
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

                # URL 유효성 검사
                if not is_valid_url(href):
                    failed_links.append({"url": href, "error": "유효하지 않은 URL"})
                    continue
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

# Streamlit 앱
st.title("크롤링 사이트")

# 세션 상태 초기화
if "step" not in st.session_state:
    st.session_state.step = 0
if "links" not in st.session_state:
    st.session_state.links = []
if "failed_links" not in st.session_state:
    st.session_state.failed_links = []

# 입력 필드
url_input = st.text_input("크롤링할 사이트 URL을 입력하세요:", placeholder="https://example.com")
start_button = st.button("크롤링 시작")

# 링크 수집 처리
if start_button and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
    else:
        progress_placeholder = st.empty()
        progress_bar = st.progress(0)

        if st.session_state.step == 0:
            with st.spinner("링크를 수집 중입니다..."):
                try:
                    links, failed_links = collect_links(url_input, progress_bar)
                    st.session_state.links = links
                    st.session_state.failed_links = failed_links
                    st.session_state.step = 1
                    st.success(f"1단계 완료: {len(links)}개의 링크를 수집했습니다.")
                except Exception as e:
                    st.error(f"링크 수집 중 오류 발생: {e}")

# 수집된 링크 및 실패한 링크 표시
if st.session_state.step > 0:
    st.write("### 수집된 링크:")
    st.write(st.session_state.links)

    st.write("### 실패한 링크:")
    st.write(st.session_state.failed_links)
