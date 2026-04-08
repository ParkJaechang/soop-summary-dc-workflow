from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import os

def save_vod_source():
    streamer_id = input("\nVOD 목록을 확인할 스트리머 ID를 입력하세요: ")
    if not streamer_id: return

    print("브라우저를 실행합니다...")
    
    options = Options()
    # 봇 탐지 우회 (필수)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # 자바스크립트 위장
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    try:
        # VOD 페이지로 직행
        url = f"https://www.sooplive.co.kr/station/{streamer_id}/vods"
        print(f"접속 중: {url}")
        driver.get(url)
        
        print("페이지 로딩 대기 중 (5초)...")
        time.sleep(5) 
        
        # 소스코드 가져오기
        page_source = driver.page_source
        
        # 파일로 저장
        filename = f"VOD_PAGE_{streamer_id}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(page_source)
            
        print(f"✅ 저장 완료! 파일명: {filename}")
        print("이 파일을 업로드해주시면, VOD를 100% 잡아내는 코드를 드릴게요!")
        
    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    save_vod_source()