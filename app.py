import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
import time

# 필터링 대상 도메인 및 키워드
EXCLUDED_DOMAINS = [
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com",
    "google.com", "whatsapp.com", "telegram.org", "pinterest.com", "snapchat.com", "reddit.com",
    "bet", "casino", "gamble", "lotto"
]
EXCLUDED_EXTENSIONS = [
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".exe", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".txt"
]
EXCLUDED_SCHEMES = ["mailto:"]  # 메일 링크 제외
EXCLUDED_KEYWORDS = ["guideline", "terms", "policy", "privacy", "cookies"]

# 사용자 에이전트 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Mobile Safari/537.36"
}

# URL 유효성 검사 함수
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc) and bool(parsed.scheme)
    except:
        return False

# 링크를 수집하는 함수
def collect_links(base_url):
    visited = set()
    links_to_visit = [base_url]
    collected_links = []
    failed_links = []

    while links_to_visit:
        url = links_to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            response = requests.get(url, headers=HEADERS, timeout=1)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
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
        except Exception as e:
            failed_links.append({"url": url, "error": "HTML 파싱 오류"})

    return collected_links, failed_links

# 멀티스레딩을 이용한 내용 크롤링 함수
def crawl_content_multithread(links):
    content_data = []
    failed_links = []

    def fetch_and_parse(link):
        try:
            response = requests.get(link, headers=HEADERS, timeout=1)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(separator="\n").strip()
            return {"url": link, "content": text}
        except Exception as e:
            failed_links.append({"url": link, "error": str(e)})
            return None

    max_threads = os.cpu_count() or 4
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(fetch_and_parse, link): link for link in links}

        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    content_data.append(result)
            except Exception as e:
                failed_links.append({"url": futures[future], "error": str(e)})

    return content_data, failed_links

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
    except:
        return None

# Streamlit 앱
st.title("크롤링 사이트")
st.write("중단 없이 안정적인 크롤링을 제공합니다.")

# 입력 필드
url_input = st.text_input("크롤링할 사이트 URL을 입력하세요:", placeholder="https://example.com")
file_format = st.radio("저장할 파일 형식 선택:", ["json", "csv"])
start_button = st.button("크롤링 시작")

if start_button and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
    else:
        with st.spinner("링크를 수집 중입니다..."):
            links, failed_links = collect_links(url_input)

        if links:
            st.success(f"수집된 링크 수: {len(links)}")
            st.warning(f"수집 실패한 링크 수: {len(failed_links)}")

            with st.spinner("내용을 크롤링 중입니다..."):
                content, failed_content_links = crawl_content_multithread(links)

            if content:
                file_path = save_data(content, file_format)
                if file_path:
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"크롤링 결과 다운로드 ({file_format.upper()})",
                            data=f,
                            file_name=file_path,
                            mime="application/json" if file_format == "json" else "text/csv"
                        )
                else:
                    st.error("파일 저장 중 오류가 발생했습니다.")
            else:
                st.error("내용 크롤링 중 오류가 발생했습니다.")
        else:
            st.error("수집된 링크가 없습니다. 다시 시도해주세요.")