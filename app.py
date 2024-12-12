import streamlit as st
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import pandas as pd
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# 설정
SNS_DOMAINS = ["facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com"]
EXCLUDED_KEYWORDS = ["login", "signin", "signup", "auth", "oauth", "account", "register"]
GOOGLE_DOMAINS = ["google.com"]
EXCLUDED_FILE_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".zip", ".rar", ".tar", ".gz"]
EXCLUDED_PLATFORMS = ["whatsapp.com", "telegram.org", "messenger.com"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}

# 비동기 요청 (링크 수집 및 컨텐츠 다운로드)
async def fetch(session, url):
    try:
        async with session.get(url, timeout=10) as response:
            response.raise_for_status()
            return await response.text()
    except Exception as e:
        return f"Error fetching {url}: {e}"

# 링크를 수집하는 함수
async def collect_links(base_url, exclude_external=False):
    base_domain = urlparse(base_url).netloc
    visited = set()
    links_to_visit = [base_url]
    collected_links = []
    failed_links = []

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        while links_to_visit:
            url = links_to_visit.pop()
            if url in visited:
                continue
            visited.add(url)

            try:
                html = await fetch(session, url)
                if "Error fetching" in html:
                    failed_links.append(url)
                    continue

                soup = BeautifulSoup(html, 'html.parser')
                collected_links.append(url)

                for tag in soup.find_all('a', href=True):
                    href = urljoin(url, tag['href'])
                    parsed_href = urlparse(href)

                    # 필터링: Google, SNS, 제외 플랫폼, 파일, 외부 링크
                    if any(domain in parsed_href.netloc for domain in GOOGLE_DOMAINS + SNS_DOMAINS + EXCLUDED_PLATFORMS):
                        continue
                    if href.startswith("mailto:") or any(href.endswith(ext) for ext in EXCLUDED_FILE_EXTENSIONS):
                        continue
                    if exclude_external and parsed_href.netloc != base_domain:
                        continue
                    if not parsed_href.scheme in ["http", "https"]:
                        continue
                    if any(keyword in parsed_href.path.lower() for keyword in EXCLUDED_KEYWORDS):
                        continue
                    if href not in visited and href not in links_to_visit:
                        links_to_visit.append(href)
            except Exception as e:
                failed_links.append(url)
                continue

    return collected_links, failed_links

# 비동기 컨텐츠 다운로드
async def crawl_content(links):
    content_data = []

    async def fetch_and_parse_content(session, link):
        try:
            html = await fetch(session, link)
            if "Error fetching" in html:
                return {"url": link, "content": f"Error fetching content: {html}"}

            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text(separator="\n")
            text = clean_text(text)
            return {"url": link, "content": text}
        except Exception as e:
            return {"url": link, "content": f"Error parsing content: {e}"}

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [fetch_and_parse_content(session, link) for link in links]
        content_data = await asyncio.gather(*tasks)

    return content_data

# 텍스트 정리 함수
def clean_text(text):
    try:
        text = text.strip()
        text_lines = text.splitlines()

        keywords_to_remove = ["cookie", "Cookie", "privacy", "Privacy", "terms", "Terms"]
        cleaned_lines = [
            line for line in text_lines
            if not any(keyword.lower() in line.lower() for keyword in keywords_to_remove)
        ]
        cleaned_text = "\n".join(cleaned_lines)
        return cleaned_text
    except Exception as e:
        return f"Error cleaning text: {e}"

# 데이터 저장 함수
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

# URL 유효성 검사
def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

# Streamlit 앱
st.title("크롤링 사이트")
st.sidebar.title("옵션 설정")
url_input = st.text_input("크롤링할 사이트 URL을 입력하세요", placeholder="https://example.com")
exclude_external = st.sidebar.checkbox("외부 링크 제외", value=False)
file_format = st.sidebar.selectbox("저장할 파일 형식 선택", ["json", "csv"])
start_crawl = st.button("크롤링 시작")

if start_crawl and url_input:
    if not is_valid_url(url_input):
        st.error("유효한 URL을 입력하세요.")
        st.stop()

    with st.spinner("링크를 수집 중입니다..."):
        collected_links, failed_links = asyncio.run(collect_links(url_input, exclude_external))

    if collected_links:
        st.success(f"수집된 링크 수: {len(collected_links)}")
        st.warning(f"수집 실패한 링크 수: {len(failed_links)}")
        st.write(collected_links)

        with st.spinner("내용을 크롤링 중입니다..."):
            content_data = asyncio.run(crawl_content(collected_links))

        if content_data:
            st.success("크롤링 완료! 학습용 데이터를 저장합니다.")
            file_path = save_data(content_data, file_format)

            if file_path:
                expire_time = datetime.now() + timedelta(hours=1)
                while datetime.now() < expire_time:
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"크롤링 결과 다운로드 ({file_format.upper()})",
                            data=f,
                            file_name=file_path,
                            mime="application/json" if file_format == "json" else "text/csv"
                        )
                        time.sleep(60)
    else:
        st.error("링크를 수집할 수 없습니다. URL을 확인하세요.")