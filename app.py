import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import re
import time
from datetime import datetime, timedelta

# 기본 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}
MAX_THREADS = max(5, multiprocessing.cpu_count() * 5)

# URL 유효성 검사
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc) and bool(parsed.scheme)
    except Exception as e:
        st.error(f"URL 유효성 검사 중 오류 발생: {e}")
        return False

# 크롤링할 링크 수집
def collect_links(base_url):
    try:
        visited = set()
        failed_links = set()
        links_to_visit = [base_url]
        collected_links = []

        while links_to_visit:
            url = links_to_visit.pop()
            if url in visited or url in failed_links:
                continue
            visited.add(url)

            try:
                response = requests.get(url, headers=HEADERS, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                collected_links.append(url)

                for tag in soup.find_all('a', href=True):
                    href = urljoin(base_url, tag['href'])
                    if urlparse(href).netloc == urlparse(base_url).netloc:
                        if href not in visited and href not in links_to_visit and href not in failed_links:
                            links_to_visit.append(href)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    st.warning(f"404 오류: URL을 찾을 수 없습니다. ({url})")
                else:
                    st.warning(f"HTTP 오류: {e} ({url})")
                failed_links.add(url)
            except requests.RequestException as e:
                st.warning(f"요청 실패: {e} ({url})")
                failed_links.add(url)

        return collected_links, list(failed_links)
    except Exception as e:
        st.error(f"링크 수집 중 오류 발생: {e}")
        return [], []

# 크롤링 작업 수행
def fetch_content(link):
    try:
        response = requests.get(link, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return {"url": link, "content": soup.get_text(separator="\n").strip()}
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return {"url": link, "content": "Error: 404 Not Found"}
        return {"url": link, "content": f"HTTP Error: {e}"}
    except Exception as e:
        return {"url": link, "content": f"Error fetching content: {e}"}

# 멀티스레딩으로 크롤링
def crawl_content(links):
    try:
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            results = list(executor.map(fetch_content, links))
        return results
    except Exception as e:
        st.error(f"크롤링 중 오류 발생: {e}")
        return []

# 데이터 저장
def save_data(data, file_format):
    try:
        if not data:
            st.error("저장할 데이터가 없습니다.")
            return None

        if file_format == "json":
            file_path = "crawled_content.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        elif file_format == "csv":
            file_path = "crawled_content.csv"
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False, encoding="utf-8")
        else:
            st.error("지원되지 않는 파일 형식입니다.")
            return None

        return file_path
    except Exception as e:
        st.error(f"데이터 저장 중 오류 발생: {e}")
        return None

# Streamlit 앱
st.title("크롤링 사이트")
url_input = st.text_input("크롤링할 사이트 URL 입력", placeholder="https://example.com")
file_format = st.selectbox("저장할 파일 형식 선택", ["json", "csv"])
start_crawl = st.button("크롤링 시작")

if start_crawl and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
    else:
        with st.spinner("링크 수집 중..."):
            links, failed_links = collect_links(url_input)

        if links:
            st.success(f"수집된 링크 수: {len(links)}")
            st.warning(f"수집 실패한 링크 수: {len(failed_links)}")

            with st.spinner("내용 크롤링 중..."):
                content = crawl_content(links)

            if content:
                st.success("크롤링 완료!")
                file_path = save_data(content, file_format)

                if file_path:
                    st.info(f"다운로드 가능: {file_path}")
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"{file_format.upper()} 파일 다운로드",
                            data=f,
                            file_name=file_path,
                            mime="application/json" if file_format == "json" else "text/csv"
                        )
            else:
                st.error("크롤링된 내용이 없습니다.")
        else:
            st.error("링크를 수집할 수 없습니다.")
