# 파일 경로: app.py

import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import math
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

# SNS 도메인 목록
SNS_DOMAINS = ["facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com"]

# 링크를 수집하는 함수
def collect_links(base_url):
    visited = set()
    links_to_visit = [base_url]
    collected_links = []

    while links_to_visit:
        url = links_to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            st.warning(f"링크 수집 중 오류 발생: {url} ({e})")
            continue

        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            collected_links.append(url)

            # 내부 링크를 수집
            for tag in soup.find_all('a', href=True):
                href = urljoin(base_url, tag['href'])
                parsed_href = urlparse(href)

                # SNS 링크 필터링
                if any(domain in parsed_href.netloc for domain in SNS_DOMAINS):
                    continue

                if urlparse(base_url).netloc == parsed_href.netloc:  # 같은 도메인만
                    if href not in visited and href not in links_to_visit:
                        links_to_visit.append(href)
        except Exception as e:
            st.warning(f"HTML 파싱 중 오류 발생: {url} ({e})")
    
    return collected_links

# 멀티스레딩을 이용한 내용 크롤링 함수
def crawl_content_multithread(links):
    content_data = []

    def fetch_content(link):
        try:
            response = requests.get(link, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text(separator="\n")
            text = clean_text(text)
            return {"url": link, "content": text}
        except requests.RequestException as e:
            return {"url": link, "content": f"Error: Unable to fetch content ({e})"}
        except Exception as e:
            return {"url": link, "content": f"Unexpected error occurred: {e}"}

    try:
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(fetch_content, links))
            content_data.extend(results)
    except Exception as e:
        st.error(f"멀티스레딩 크롤링 중 오류 발생: {e}")
    
    return content_data

# 텍스트 정리 함수
def clean_text(text):
    try:
        # 공백 및 불필요한 줄바꿈 제거
        text = text.strip()
        text = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
        return text
    except Exception as e:
        st.warning(f"텍스트 정리 중 오류 발생: {e}")
        return ""

# 데이터 저장 함수 (JSON 및 CSV)
def save_data(data, file_format):
    try:
        if file_format == "json":
            file_path = "crawled_content.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return file_path
        elif file_format == "csv":
            file_path = "crawled_content.csv"
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False, encoding="utf-8")
            return file_path
    except Exception as e:
        st.error(f"데이터 저장 중 오류 발생: {e}")
    return None

# 페이징 처리 함수
def display_paginated_results(data, page, results_per_page):
    try:
        start = (page - 1) * results_per_page
        end = start + results_per_page
        for item in data[start:end]:
            st.subheader(item["url"])
            st.text(item["content"][:1000])  # 긴 텍스트를 줄여 표시

        total_pages = math.ceil(len(data) / results_per_page)
        return total_pages
    except Exception as e:
        st.error(f"페이징 처리 중 오류 발생: {e}")
        return 0

# URL 유효성 검사 함수
def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc) and bool(parsed.scheme)
    except Exception as e:
        st.error(f"URL 유효성 검사 중 오류 발생: {e}")
        return False

# Streamlit 앱
st.title("오류 방지 웹 크롤러 및 학습 데이터 생성기")
url_input = st.text_input("사이트 URL을 입력하세요", placeholder="https://example.com")
RESULTS_PER_PAGE = 5
file_format = st.selectbox("저장할 파일 형식을 선택하세요", ["json", "csv"])
start_crawl = st.button("크롤링 시작")

if start_crawl and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
        st.stop()

    with st.spinner("링크를 수집 중입니다..."):
        try:
            links = collect_links(url_input)
        except Exception as e:
            st.error(f"링크 수집 중 치명적인 오류 발생: {e}")
            links = []

    if links:
        st.success(f"수집된 링크 수: {len(links)}")
        st.write(links)

        with st.spinner("내용을 크롤링 중입니다..."):
            try:
                content = crawl_content_multithread(links)
            except Exception as e:
                st.error(f"크롤링 중 치명적인 오류 발생: {e}")
                content = []

        if content:
            st.success("크롤링 완료! 학습용 데이터를 저장합니다.")
            file_path = save_data(content, file_format)

            if file_path:
                try:
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"크롤링 결과 다운로드 ({file_format.upper()})",
                            data=f,
                            file_name=file_path,
                            mime="application/json" if file_format == "json" else "text/csv"
                        )
                except Exception as e:
                    st.error(f"파일 다운로드 중 오류 발생: {e}")
    else:
        st.error("링크를 수집할 수 없습니다. URL을 확인하세요.")