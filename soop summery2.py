import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import yt_dlp
import os
import sys
import threading
import json
import time
import re
import google.generativeai as genai

# === 설정 파일 이름 ===
CONFIG_FILE = "config.json"

class SoopApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SOOP 방송 요약기 (댓글 타임라인 최적화)")
        self.root.geometry("600x650")
        self.root.resizable(False, False)

        # 변수 초기화
        self.api_key = tk.StringVar()
        self.save_dir = tk.StringVar()
        self.url_var = tk.StringVar()
        self.auto_delete = tk.BooleanVar(value=True) # 오디오 자동 삭제 기본값 ON
        
        # UI 구성
        self.create_widgets()
        self.load_config()

    def create_widgets(self):
        # 1. API 키
        tk.Label(self.root, text="Gemini API Key:").pack(pady=(10, 0))
        self.entry_api = tk.Entry(self.root, textvariable=self.api_key, show="*", width=70)
        self.entry_api.pack(pady=5)

        # 2. 저장 폴더
        tk.Label(self.root, text="저장 폴더 (미리 지정):").pack(pady=(10, 0))
        frame_dir = tk.Frame(self.root)
        frame_dir.pack(pady=5)
        entry_dir = tk.Entry(frame_dir, textvariable=self.save_dir, width=55, state='readonly')
        entry_dir.pack(side=tk.LEFT, padx=5)
        tk.Button(frame_dir, text="폴더 선택", command=self.choose_directory).pack(side=tk.LEFT)

        # 3. URL 입력
        tk.Label(self.root, text="SOOP 다시보기 URL:").pack(pady=(15, 0))
        self.entry_url = tk.Entry(self.root, textvariable=self.url_var, width=70)
        self.entry_url.pack(pady=5)

        # 4. 옵션 (자동 삭제 체크박스)
        tk.Checkbutton(self.root, text="요약 완료 후 오디오 파일 자동 삭제 (용량 절약)", 
                       variable=self.auto_delete).pack(pady=5)

        # 5. 실행 버튼
        self.btn_start = tk.Button(self.root, text="요약 및 타임라인 생성 시작", command=self.start_thread, 
                                   bg="#0078D7", fg="white", font=("맑은 고딕", 12, "bold"), height=2, width=30)
        self.btn_start.pack(pady=15)

        # 6. 로그 창
        self.log_area = scrolledtext.ScrolledText(self.root, width=80, height=18, state='disabled', font=("맑은 고딕", 9))
        self.log_area.pack(pady=10, padx=10)

        tk.Label(self.root, text="Gemini 1.5 Flash 모델 사용 | 오디오 전용 추출", fg="gray").pack(side=tk.BOTTOM, pady=5)

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def choose_directory(self):
        path = filedialog.askdirectory()
        if path:
            self.save_dir.set(path)
            self.save_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.api_key.set(data.get("api_key", ""))
                    self.save_dir.set(data.get("save_dir", ""))
            except: pass

    def save_config(self):
        data = { "api_key": self.api_key.get(), "save_dir": self.save_dir.get() }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def get_best_model(self, api_key):
        try:
            genai.configure(api_key=api_key, transport='rest')
            models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            for m in models: 
                if 'flash' in m: return m
            return models[0] if models else None
        except Exception as e:
            self.log(f"❌ 모델 검색 오류: {e}")
            return None

    def start_thread(self):
        if not self.api_key.get().strip() or not self.save_dir.get().strip() or not self.url_var.get().strip():
            messagebox.showwarning("알림", "API 키, 저장 폴더, URL을 모두 확인해주세요.")
            return
        self.save_config()
        self.btn_start.config(state='disabled', text="작업 진행 중...")
        threading.Thread(target=self.run_process, daemon=True).start()

    def clean_text_for_comments(self, text):
        """AI가 만든 텍스트에서 마크다운(**) 제거 및 형식 다듬기"""
        # 1. **굵게** 표시 제거
        text = text.replace("**", "")
        text = text.replace("##", "")
        # 2. 불필요한 공백 정리
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    def run_process(self):
        try:
            url = self.url_var.get().strip()
            save_path = self.save_dir.get()
            safe_key = self.api_key.get().strip()
            
            # ffmpeg 위치 확인
            if getattr(sys, 'frozen', False): script_dir = os.path.dirname(sys.executable)
            else: script_dir = os.path.dirname(os.path.abspath(__file__))
            
            ffmpeg_path = os.path.join(script_dir, "ffmpeg.exe")
            if not os.path.exists(ffmpeg_path):
                self.log("🚨 [오류] ffmpeg.exe 없음. 실행 파일과 같은 폴더에 넣어주세요.")
                self.reset_button()
                return

            # 1. 모델 연결
            self.log("📡 AI 모델 연결 확인 중...")
            model_name = self.get_best_model(safe_key)
            if not model_name:
                self.log("❌ AI 모델 연결 실패. API 키를 확인하세요.")
                self.reset_button()
                return
            
            # 2. 다운로드 (오디오 전용, 128k 압축)
            self.log("🚀 오디오 추출 시작 (시간 절약을 위해 영상은 받지 않습니다)...")
            
            # 파일명 규칙: 방송인_제목_날짜.mp3
            output_template = os.path.join(save_path, "%(uploader)s_%(title)s_%(upload_date)s.%(ext)s")
            
            ydl_opts = {
                'format': 'bestaudio/best', # 오디오만 다운로드
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128', # 192k -> 128k (용량/속도 최적화, 음성인식엔 충분)
                }],
                'ffmpeg_location': script_dir,
                'quiet': True,
                'no_warnings': True,
            }

            mp3_filename = ""
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                mp3_filename = os.path.splitext(filename)[0] + ".mp3"

            file_size_mb = os.path.getsize(mp3_filename) / (1024 * 1024)
            self.log(f"✅ 다운로드 완료 ({file_size_mb:.1f} MB)")
            
            # 3. AI 분석 및 요약
            self.log("⚡ Gemini AI 분석 시작 (최대 1~3분 소요)...")
            
            genai.configure(api_key=safe_key, transport='rest')
            audio_file = genai.upload_file(path=mp3_filename)
            
            while audio_file.state.name == "PROCESSING":
                time.sleep(2)
                audio_file = genai.get_file(audio_file.name)
            
            if audio_file.state.name == "FAILED":
                self.log("❌ AI 파일 처리 실패")
                self.reset_button()
                return

            # === [핵심] 댓글 양식 맞춤 프롬프트 ===
            prompt = """
            너는 인터넷 방송 요약 전문가야. 이 오디오 파일을 분석해서 아래 양식대로 정리해줘.
            
            [제약 사항 - 매우 중요]
            1. 텍스트에 볼드체(**), 헤더(##) 등 마크다운 문법을 절대 쓰지 마.
            2. 타임라인은 반드시 `[HH:MM:SS] 내용` 형식을 지켜. (댓글용 링크 기능 때문이야)
            3. 설명은 간결하고 명확하게 작성해.

            [작성 양식]
            【 📋 3줄 요약 】
            - 내용 1
            - 내용 2
            - 내용 3

            【 🕒 상세 타임라인 】
            [00:00:00] 방송 시작
            (주제가 바뀌는 모든 중요 구간을 [HH:MM:SS] 형식으로 작성)

            【 ⭐ 하이라이트/유튜브각 】
            [HH:MM:SS] 제목 (이유 간략히)
            
            【 💬 주요 멘트/어록 】
            [HH:MM:SS] "멘트 내용"
            """
            
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([prompt, audio_file])
            
            # 4. 결과 저장 및 후처리
            final_text = self.clean_text_for_comments(response.text) # 특수문자 청소
            
            txt_filename = mp3_filename.replace(".mp3", "_요약.txt")
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(final_text)
            
            self.log("="*30)
            self.log("🎉 작업 완료!")
            self.log(f"📄 요약본 생성됨: {os.path.basename(txt_filename)}")
            
            # 요약본 자동 실행
            os.startfile(txt_filename)

            # 5. 오디오 파일 자동 삭제
            if self.auto_delete.get():
                try:
                    # AI가 파일 처리를 확실히 끝냈는지 확인 후 삭제
                    genai.delete_file(audio_file.name) # 구글 클라우드에서 삭제
                    os.remove(mp3_filename) # 내 컴퓨터에서 삭제
                    self.log(f"🗑️ 용량 확보: 오디오 파일이 자동 삭제되었습니다.")
                except Exception as e:
                    self.log(f"⚠️ 파일 삭제 중 경고: {e}")

        except Exception as e:
            self.log(f"❌ 오류 발생: {e}")
        finally:
            self.reset_button()

    def reset_button(self):
        self.btn_start.config(state='normal', text="요약 및 타임라인 생성 시작")

if __name__ == "__main__":
    root = tk.Tk()
    app = SoopApp(root)
    root.mainloop()