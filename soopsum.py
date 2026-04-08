import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import yt_dlp
import os
import sys
import threading
import json
import time
import google.generativeai as genai

# === 설정 파일 이름 ===
CONFIG_FILE = "config.json"

class SoopApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SOOP 방송 자동 요약기 (AI Powered)")
        self.root.geometry("600x550")
        self.root.resizable(False, False)

        # 설정 변수 초기화
        self.api_key = tk.StringVar()
        self.save_dir = tk.StringVar()
        self.url_var = tk.StringVar()
        
        # UI 그리기
        self.create_widgets()
        
        # 저장된 설정 불러오기
        self.load_config()

    def create_widgets(self):
        # 1. API 키 입력
        tk.Label(self.root, text="Gemini API Key:").pack(pady=(10, 0))
        self.entry_api = tk.Entry(self.root, textvariable=self.api_key, show="*", width=70)
        self.entry_api.pack(pady=5)

        # 2. 저장 폴더 설정
        tk.Label(self.root, text="저장 폴더:").pack(pady=(10, 0))
        frame_dir = tk.Frame(self.root)
        frame_dir.pack(pady=5)
        
        entry_dir = tk.Entry(frame_dir, textvariable=self.save_dir, width=55, state='readonly')
        entry_dir.pack(side=tk.LEFT, padx=5)
        
        btn_dir = tk.Button(frame_dir, text="폴더 변경", command=self.choose_directory)
        btn_dir.pack(side=tk.LEFT)

        # 3. URL 입력
        tk.Label(self.root, text="SOOP 다시보기 URL:").pack(pady=(15, 0))
        self.entry_url = tk.Entry(self.root, textvariable=self.url_var, width=70)
        self.entry_url.pack(pady=5)

        # 4. 실행 버튼
        self.btn_start = tk.Button(self.root, text="요약 시작 (Start)", command=self.start_thread, 
                                   bg="#0078D7", fg="white", font=("Arial", 12, "bold"), height=2, width=20)
        self.btn_start.pack(pady=20)

        # 5. 로그 창 (진행상황 표시)
        self.log_area = scrolledtext.ScrolledText(self.root, width=80, height=15, state='disabled')
        self.log_area.pack(pady=10, padx=10)

        # 하단 저작권 표시
        tk.Label(self.root, text="Powered by Gemini 1.5 Flash & yt-dlp", fg="gray").pack(side=tk.BOTTOM, pady=5)

    def log(self, message):
        """로그 창에 글을 쓰는 함수"""
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END) # 스크롤을 항상 아래로
        self.log_area.config(state='disabled')

    def choose_directory(self):
        path = filedialog.askdirectory()
        if path:
            self.save_dir.set(path)
            self.save_config() # 변경 즉시 저장

    def load_config(self):
        """설정 파일(json)에서 키와 경로를 불러옴"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.api_key.set(data.get("api_key", ""))
                    self.save_dir.set(data.get("save_dir", ""))
            except:
                pass

    def save_config(self):
        """현재 설정을 파일로 저장"""
        data = {
            "api_key": self.api_key.get(),
            "save_dir": self.save_dir.get()
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def get_script_directory(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def get_best_model(self, api_key):
        """사용 가능한 모델 자동 감지"""
        try:
            genai.configure(api_key=api_key, transport='rest')
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            
            # Flash 모델 우선 검색
            for model_name in available_models:
                if 'flash' in model_name:
                    return model_name
            # 없으면 첫 번째 모델
            return available_models[0] if available_models else None
        except Exception as e:
            self.log(f"❌ 모델 검색 오류: {e}")
            return None

    def start_thread(self):
        """버튼을 누르면 별도 스레드에서 작업을 시작 (앱이 멈추지 않게 함)"""
        # 입력값 검증
        if not self.api_key.get().strip():
            messagebox.showwarning("경고", "API 키를 입력해주세요.")
            return
        if not self.save_dir.get().strip():
            messagebox.showwarning("경고", "저장 폴더를 설정해주세요.")
            return
        if not self.url_var.get().strip():
            messagebox.showwarning("경고", "URL을 입력해주세요.")
            return

        self.save_config() # 시작 전 설정 저장
        self.btn_start.config(state='disabled', text="작업 진행 중...") # 버튼 비활성화
        
        # 스레드 시작
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        """실제 작업 로직"""
        try:
            url = self.url_var.get().strip()
            save_path = self.save_dir.get()
            safe_key = self.api_key.get().strip()
            
            script_dir = self.get_script_directory()
            ffmpeg_path = os.path.join(script_dir, "ffmpeg.exe")

            if not os.path.exists(ffmpeg_path):
                self.log("🚨 [오류] ffmpeg.exe를 찾을 수 없습니다!")
                self.reset_button()
                return

            # 1. 모델 감지
            self.log("📡 AI 모델 연결 중...")
            model_name = self.get_best_model(safe_key)
            if not model_name:
                self.log("❌ AI 모델을 찾을 수 없습니다. 키를 확인하세요.")
                self.reset_button()
                return
            self.log(f"✅ 모델 연결 성공: {model_name}")

            # 2. 다운로드 (메타데이터 포함)
            self.log("🚀 다운로드 시작 (방송인/제목/날짜 자동 추출)...")
            
            # 파일명 템플릿: 방송인_방송제목_날짜.mp3
            # yt-dlp는 파일명에 쓸 수 없는 특수문자를 알아서 걸러줍니다.
            output_template = os.path.join(save_path, "%(uploader)s_%(title)s_%(upload_date)s.%(ext)s")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
                'ffmpeg_location': script_dir,
                'quiet': True,
                'no_warnings': True,
            }

            mp3_filename = ""
            
            # 메타데이터를 얻기 위해 다운로드 실행
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # 다운로드된 실제 파일명 찾기
                filename = ydl.prepare_filename(info)
                mp3_filename = os.path.splitext(filename)[0] + ".mp3"

            self.log(f"✅ 다운로드 완료: {os.path.basename(mp3_filename)}")
            
            # 3. AI 요약
            self.log("⚡ AI에게 요약 요청 중... (잠시만 기다려주세요)")
            
            genai.configure(api_key=safe_key, transport='rest')
            audio_file = genai.upload_file(path=mp3_filename)
            
            while audio_file.state.name == "PROCESSING":
                time.sleep(2)
                audio_file = genai.get_file(audio_file.name)
            
            if audio_file.state.name == "FAILED":
                self.log("❌ AI 업로드 실패")
                self.reset_button()
                return

            model = genai.GenerativeModel(model_name)
            prompt = """
            이 파일은 인터넷 방송(SOOP)의 오디오야. 전문 편집자 관점에서 아래 내용을 정리해줘.
            1. [방송 3줄 요약]
            2. [상세 타임라인] (시간대별 주제)
            3. [유튜브 각(하이라이트)] (재미있는 구간 3곳 추천)
            4. [주요 멘트]
            """
            
            response = model.generate_content([prompt, audio_file])
            
            # 4. 결과 저장
            txt_filename = mp3_filename.replace(".mp3", "_요약.txt")
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(response.text)
            
            self.log("="*30)
            self.log("🎉 작업 완료!")
            self.log(f"📄 요약본: {os.path.basename(txt_filename)}")
            
            os.startfile(txt_filename) # 요약본 자동 실행

        except Exception as e:
            self.log(f"❌ 오류 발생: {e}")
        finally:
            self.reset_button()

    def reset_button(self):
        self.btn_start.config(state='normal', text="요약 시작 (Start)")

if __name__ == "__main__":
    root = tk.Tk()
    app = SoopApp(root)
    root.mainloop()