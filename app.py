import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import os
import random
import time

# 필터링 대상
EXCLUDED_DOMAINS = ["facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com"]
EXCLUDED_EXTENSIONS = [".pdf", ".docx", ".zip", ".exe"]
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
        return bool(parsed.netloc) and bool(parsed.scheme)
    except Exception:
        return False

# 세션 상태 초기화 함수
def initialize_session_state():
    """Ensure all session state variables are initialized."""
    if "step" not in st.session_state:
        st.session_state.step = 0  # 현재 단계
    if "file_path" not in st.session_state:
        st.session_state.file_path = None  # 파일 경로
    if "links" not in st.session_state:
        st.session_state.links = []  # 수집된 링크
    if "failed_links" not in st.session_state:
        st.session_state.failed_links = []  # 실패한 링크
    if "content" not in st.session_state:
        st.session_state.content = []  # 크롤링된 내용

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
initialize_session_state()

# 입력 필드
url_input = st.text_input("크롤링할 사이트 URL을 입력하세요:", placeholder="https://example.com")
file_format = st.radio("저장할 파일 형식 선택:", ["json", "csv", "txt"])
start_button = st.button("크롤링 시작")

# 단계별 작업 처리
if start_button and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
    else:
        # 진행 상황을 업데이트하는 UI
        progress_placeholder = st.empty()
        progress_bar = st.progress(0)

        # 단계별 작업 처리
        if st.session_state.step == 0:
            with st.spinner("링크를 수집 중입니다..."):
                try:
                    # 예제: 링크 수집 작업
                    st.session_state.links = ["https://example.com/page1", "https://example.com/page2"]
                    st.session_state.failed_links = []
                    st.session_state.step = 1
                    st.success("1단계 완료: 링크 수집 완료")
                except Exception as e:
                    st.error(f"링크 수집 중 오류 발생: {e}")

        if st.session_state.step == 1:
            with st.spinner("내용을 크롤링 중입니다..."):
                try:
                    # 예제: 크롤링 작업
                    st.session_state.content = [
                        {"url": "https://example.com/page1", "content": "Page 1 content"},
                        {"url": "https://example.com/page2", "content": "Page 2 content"},
                    ]
                    st.session_state.step = 2
                    st.success("2단계 완료: 내용 크롤링 완료")
                except Exception as e:
                    st.error(f"내용 크롤링 중 오류 발생: {e}")

        if st.session_state.step == 2:
            with st.spinner("데이터를 저장 중입니다..."):
                try:
                    file_path = save_data(st.session_state.content, file_format)
                    st.session_state.file_path = file_path
                    st.session_state.step = 3
                    st.success("3단계 완료: 데이터 저장 완료")
                except Exception as e:
                    st.error(f"데이터 저장 중 오류 발생: {e}")

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
