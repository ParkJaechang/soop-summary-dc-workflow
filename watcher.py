from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pickle
import time
import os
import datetime

# ==========================================
# 🎯 [설정] 감시할 스트리머 아이디 입력
# 예: 방송국 주소가 https://ch.sooplive.co.kr/godan123 이라면 'godan123' 입력
TARGET_ID = "kaksjak0730" 
# ==========================================

class SoopWatcher:
    def __init__(self, target_id):
        self.target_id = target_id
        self.station_url = f"https://ch.sooplive.co.kr/{target_id}"
        self.vod_url = f"https://ch.sooplive.co.kr/{target_id}/vods"
        self.driver = None
        self.is_live_previously = True # 이전 상태 기억용

    def setup_driver(self):
        """크롬 브라우저 설정 (화면 안 보이는 Headless 모드)"""
        chrome_options = Options()
        # 미니 PC 부하를 줄이기 위해 화면 없이 실행 (테스트할 땐 아래 줄 주석 처리하면 화면 보임)
        chrome_options.add_argument("--headless") 
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--log-level=3") # 불필요한 로그 숨기기
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    def load_cookies(self):
        """저장해둔 쿠키 불러오기 (로그인 상태 만들기)"""
        if not os.path.exists("cookies_soop.pkl"):
            print("❌ 'cookies_soop.pkl' 파일이 없습니다! login_saver.py를 먼저 실행하세요.")
            return False

        print("🍪 쿠키 로딩 중...")
        # 도메인 설정을 위해 먼저 SOOP 접속
        self.driver.get("https://www.sooplive.co.kr")
        
        with open("cookies_soop.pkl", "rb") as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass
        
        print("✅ 로그인 정보 적용 완료!")
        return True

    def check_live_status(self):
        """방송 상태 확인"""
        try:
            self.driver.get(self.station_url)
            time.sleep(3) # 로딩 대기

            # '생방송' 배지가 있는지 확인 (SOOP 방송국 구조 기반)
            # 보통 방송 중이면 상단 플레이어나 프로필 쪽에 'ON AIR' 또는 '생방송' 표시가 뜸
            # 가장 확실한 건 페이지 소스에 "on_air" 관련 클래스가 있는지 보는 것
            page_source = self.driver.page_source
            
            # 간단한 판단 로직: "ON AIR" 텍스트나 특정 클래스 찾기
            # (SOOP 구조에 따라 클래스명은 다를 수 있으나, 보통 onair, broadcasting 등으로 표시됨)
            if "onair" in page_source or "생방송 중" in page_source:
                return True
            
            # 더 정밀한 확인: 방송 플레이어 요소가 활성화되어 있는지
            try:
                # 방송 중일 때만 뜨는 플레이어 영역 체크
                self.driver.find_element(By.CLASS_NAME, "player_area") 
                # 또는 구체적인 'ON' 배지 요소
                return True
            except:
                return False

        except Exception as e:
            print(f"⚠️ 확인 중 오류: {e}")
            return False

    def get_latest_vod(self):
        """방송 종료 후 가장 최신 VOD 링크 가져오기"""
        print("🔍 최신 VOD 찾는 중...")
        try:
            self.driver.get(self.vod_url)
            time.sleep(3)
            
            # VOD 목록에서 첫 번째 썸네일이나 링크 찾기
            # SOOP VOD 리스트의 첫 번째 항목 = 방금 끝난 방송
            vod_elements = self.driver.find_elements(By.CSS_SELECTOR, "a.thumb")
            
            if vod_elements:
                latest_url = vod_elements[0].get_attribute("href")
                title = vod_elements[0].get_attribute("title")
                return latest_url, title
            else:
                return None, None
        except Exception as e:
            print(f"❌ VOD 찾기 실패: {e}")
            return None, None

    def start_monitoring(self):
        self.setup_driver()
        if not self.load_cookies():
            return

        print(f"👀 [{self.target_id}] 방송 감시 시작... (Ctrl+C로 종료)")
        
        try:
            while True:
                current_time = datetime.datetime.now().strftime("%H:%M:%S")
                is_live_now = self.check_live_status()

                if is_live_now:
                    print(f"[{current_time}] 🔴 방송 중입니다!")
                    self.is_live_previously = True
                else:
                    print(f"[{current_time}] ⚫ 오프라인 (방송 안 킴)")
                    
                    # [핵심 로직] 방금 전까지 방송 중이었다가(True) -> 지금 꺼짐(False) = "방종!"
                    if self.is_live_previously == True:
                        print("\n" + "="*40)
                        print("🚀 방송 종료 감지! VOD 추출을 시도합니다.")
                        print("="*40)
                        
                        # SOOP이 VOD를 생성하는 데 시간이 조금 걸릴 수 있음 (30초 대기)
                        time.sleep(30) 
                        
                        vod_link, title = self.get_latest_vod()
                        if vod_link:
                            print(f"✅ VOD 발견: {title}")
                            print(f"🔗 링크: {vod_link}")
                            
                            # 여기에 나중에 '자동 요약기'를 실행하는 코드를 넣으면 됩니다!
                            # 예: run_summary_bot(vod_link)
                            
                        else:
                            print("❌ VOD를 아직 찾지 못했습니다. (삭제됐거나 생성 지연)")
                        
                        # 상태 초기화
                        self.is_live_previously = False 

                # 60초마다 확인 (미니 PC 과부하 방지)
                time.sleep(60)

        except KeyboardInterrupt:
            print("\n👋 감시를 종료합니다.")
            self.driver.quit()

if __name__ == "__main__":
    # 여기에 감시할 스트리머 아이디를 넣으세요
    # 예: 고단씨 아이디가 'godan'이라면 "godan"
    bot = SoopWatcher(TARGET_ID) 
    bot.start_monitoring()