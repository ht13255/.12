import streamlit as st
import requests
from bs4 import BeautifulSoup
import pdfkit
import os

def is_social_media_link(link):
    """SNS 링크인지 확인하는 함수"""
    social_keywords = ["facebook", "twitter", "instagram", "linkedin", "youtube", "tiktok"]
    return any(keyword in link for keyword in social_keywords)

def get_links_from_website(url):
    """웹사이트에서 링크를 수집"""
    try:
        response = requests.get(url)
        response.raise_for_status()  # HTTP 오류 확인
        soup = BeautifulSoup(response.content, "html.parser")
        links = [
            a['href'] for a in soup.find_all('a', href=True)
            if not is_social_media_link(a['href'])  # SNS 링크 제외
        ]
        # 상대 경로를 절대 경로로 변환
        links = [link if link.startswith("http") else requests.compat.urljoin(url, link) for link in links]
        return links
    except Exception as e:
        st.error(f"Error fetching links: {e}")
        return []

def save_page_as_pdf(url, output_folder, pdfkit_config):
    """페이지를 PDF로 저장"""
    try:
        pdf_path = os.path.join(output_folder, f"{url.replace('https://', '').replace('/', '_')}.pdf")
        pdfkit.from_url(url, pdf_path, configuration=pdfkit_config)  # pdfkit을 사용하여 URL을 PDF로 변환
        return True
    except Exception as e:
        st.error(f"Error saving {url} as PDF: {e}")
        return False

def main():
    st.title("웹사이트 링크를 PDF로 저장")

    # 사용자 입력 URL
    url = st.text_input("웹사이트 URL을 입력하세요", "https://example.com")
    output_folder = "saved_pdfs"
    os.makedirs(output_folder, exist_ok=True)  # 출력 폴더 생성

    # wkhtmltopdf 경로 설정
    wkhtmltopdf_path = "/usr/local/bin/wkhtmltopdf"  # Linux/MacOS용 기본 경로
    # Windows의 경우: wkhtmltopdf_path = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    pdfkit_config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

    if st.button("PDF 저장 시작"):
        st.info("링크를 수집 중입니다...")
        links = get_links_from_website(url)

        if links:
            st.success(f"{len(links)}개의 링크를 발견했습니다!")
            st.info("PDF로 저장 중...")

            saved_count = 0
            for link in links:
                if save_page_as_pdf(link, output_folder, pdfkit_config):
                    saved_count += 1

            st.success(f"{saved_count}/{len(links)} 페이지를 PDF로 저장했습니다.")
        else:
            st.warning("링크를 찾을 수 없습니다.")

    st.info(f"PDF는 '{output_folder}' 폴더에 저장됩니다.")

if __name__ == "__main__":
    main()