import customtkinter as ctk
from tkinter import filedialog, messagebox
import yt_dlp
import os
import sys
import threading
import json
import time
import re
import warnings
import subprocess
import glob
import shutil
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# 경고 무시
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore")

try:
    import google.generativeai as genai
except ImportError:
    messagebox.showerror("오류", "google-generativeai 라이브러리가 없습니다.")
    sys.exit()

# === 설정 ===
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")
ARIA2C_PATH = os.path.join(BASE_DIR, "aria2c.exe")

GEMINI_MODEL = "gemini-2.5-flash"

class SoopProApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"SOOP Pro Analyst (Visual Status V75)")
        self.geometry("950x950")
        self.resizable(False, False)

        self.api_key = ctk.StringVar()
        self.save_dir = ctk.StringVar()
        self.url_var = ctk.StringVar()
        self.status_var = ctk.StringVar(value="대기 중")
        
        self.full_audio_path = None 
        self.split_files = [] 
        self.video_title = "Unknown"
        self.streamer_name = "Unknown"
        self.current_vod_folder = None
        self.is_running = False
        
        self.create_ui()
        self.load_config()

        if len(sys.argv) > 1:
            auto_url = sys.argv[1]
            self.url_var.set(auto_url)
            self.after(1500, self.start_prep)

    def create_ui(self):
        ctk.CTkLabel(self, text=f"SOOP 방송 정밀 분석기 ({GEMINI_MODEL})", font=("Arial", 20, "bold")).pack(pady=15)

        frame_conf = ctk.CTkFrame(self)
        frame_conf.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(frame_conf, text="API Key:").pack(side="left", padx=10)
        ctk.CTkEntry(frame_conf, textvariable=self.api_key, width=250, show="*").pack(side="left", padx=5)
        ctk.CTkButton(frame_conf, text="저장 루트", width=80, command=self.choose_dir).pack(side="right", padx=10)

        # Step 1
        frame_step1 = ctk.CTkFrame(self)
        frame_step1.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_step1, text="[Step 1] 영상 준비", font=("Arial", 14, "bold"), text_color="#00AA00").pack(anchor="w", padx=10, pady=5)
        
        self.entry_url = ctk.CTkEntry(frame_step1, textvariable=self.url_var, placeholder_text="VOD 링크")
        self.entry_url.pack(fill="x", padx=10, pady=5)
        
        btn_frame = ctk.CTkFrame(frame_step1, fg_color="transparent")
        btn_frame.pack(fill="x", padx=5, pady=5)
        self.btn_prep = ctk.CTkButton(btn_frame, text="▶ 시작 (다운로드+분할)", command=self.start_prep, fg_color="#00AA00", height=35)
        self.btn_prep.pack(side="left", fill="x", expand=True, padx=5)
        
        self.btn_load = ctk.CTkButton(btn_frame, text="📂 통합본(.mp3) 불러오기", command=self.load_local_file_thread, fg_color="#1F6AA5", height=35)
        self.btn_load.pack(side="left", fill="x", expand=True, padx=5)
        
        self.btn_manual = ctk.CTkButton(btn_frame, text="📂 파트 파일(002 등) 넣기", command=self.load_manual_part, fg_color="#E59100", height=35)
        self.btn_manual.pack(side="left", fill="x", expand=True, padx=5)
        
        self.btn_stop = ctk.CTkButton(btn_frame, text="■ 중단", command=self.stop_process, fg_color="#AA0000", hover_color="#880000", height=35, state="disabled")
        self.btn_stop.pack(side="right", fill="x", padx=5)

        self.progress = ctk.CTkProgressBar(self, width=800)
        self.progress.pack(pady=5)
        self.progress.set(0)
        
        self.lbl_status = ctk.CTkLabel(self, textvariable=self.status_var, font=("Consolas", 12), text_color="#FFAA00", wraplength=800)
        self.lbl_status.pack(pady=5)

        # Step 2
        frame_step2 = ctk.CTkFrame(self)
        frame_step2.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_step2, text=f"[Step 2] 2단계 정밀 분석 (STT -> 요약)", font=("Arial", 14, "bold"), text_color="#1F6AA5").pack(anchor="w", padx=10, pady=5)

        btn_box = ctk.CTkFrame(frame_step2, fg_color="transparent")
        btn_box.pack(fill="x", padx=5, pady=5)

        self.btn_detail = ctk.CTkButton(btn_box, text="📜 STT 변환 후 정밀 요약 (진행 상황 표시)", command=lambda: self.run_contextual_analysis("detail"), 
                                        fg_color="#5500AA", hover_color="#440088", state="disabled", width=300, height=50, font=("Arial", 15, "bold"))
        self.btn_detail.pack(side="left", padx=10, expand=True)

        self.btn_timeline = ctk.CTkButton(btn_box, text="⏰ 타임라인 Only", command=lambda: self.run_contextual_analysis("timeline"), 
                                          fg_color="#E59100", hover_color="#B37400", state="disabled", width=300, height=50, font=("Arial", 15, "bold"))
        self.btn_timeline.pack(side="right", padx=10, expand=True)

        self.txt_result = ctk.CTkTextbox(self, font=("Consolas", 11))
        self.txt_result.pack(fill="both", expand=True, padx=20, pady=10)

    def choose_dir(self):
        d = filedialog.askdirectory()
        if d: self.save_dir.set(d); self.save_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.api_key.set(data.get("api_key", ""))
                    self.save_dir.set(data.get("save_dir", BASE_DIR))
            except: pass
        else: self.save_dir.set(BASE_DIR)

    def save_config(self):
        data = {"api_key": self.api_key.get(), "save_dir": self.save_dir.get()}
        with open(CONFIG_FILE, "w") as f: json.dump(data, f)

    def log(self, msg):
        self.txt_result.insert("end", f"{msg}\n")
        self.txt_result.see("end")

    def remove_ansi_codes(self, text):
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
        return ansi_escape.sub('', text)

    def correct_timestamps(self, text, part_index):
        lines = text.split('\n')
        corrected_lines = []
        pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]')
        for line in lines:
            def replace_match(match):
                g1, g2, g3 = match.groups()
                if g3: h, m, s = int(g1), int(g2), int(g3)
                else: h, m, s = 0, int(g1), int(g2)
                real_h = h + part_index
                return f"[{real_h:02d}:{m:02d}:{s:02d}]"
            new_line = pattern.sub(replace_match, line)
            corrected_lines.append(new_line)
        return '\n'.join(corrected_lines)

    def progress_hook(self, d):
        if not self.is_running: raise Exception("사용자 중단")
        if d['status'] == 'downloading':
            percent = self.remove_ansi_codes(d.get('_percent_str', '0%'))
            eta = self.remove_ansi_codes(d.get('_eta_str', '?'))
            speed = self.remove_ansi_codes(d.get('_speed_str', '?'))
            msg = f"⬇️ 다운 중: {percent} | 🚀 {speed} | ⏳ {eta}"
            self.status_var.set(msg)
            try:
                p = float(percent.replace('%','')) / 100
                self.progress.set(p * 0.4) 
            except: pass
        elif d['status'] == 'finished':
            self.status_var.set("🔨 저장 완료.")

    def prepare_vod_folder(self, title):
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
        if not safe_title: safe_title = "Unknown_VOD"
        vod_path = os.path.join(self.save_dir.get(), safe_title)
        os.makedirs(vod_path, exist_ok=True)
        self.current_vod_folder = vod_path
        self.video_title = safe_title
        return vod_path

    def stop_process(self):
        if self.is_running:
            self.is_running = False
            self.status_var.set("⛔ 작업 중단됨")
            self.log("\n⛔ [사용자 중단] 작업이 취소되었습니다.")
            self.btn_prep.configure(state="normal")
            self.btn_load.configure(state="normal")
            self.btn_manual.configure(state="normal")
            self.btn_stop.configure(state="disabled")

    def start_prep(self):
        url = self.url_var.get().strip()
        key = self.api_key.get().strip()
        if not url or not key: return messagebox.showwarning("오류", "입력 확인")
        self.is_running = True
        self.btn_prep.configure(state="disabled")
        self.btn_load.configure(state="disabled")
        self.btn_manual.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.save_config()
        threading.Thread(target=self.thread_prep, args=(url, key), daemon=True).start()

    def thread_prep(self, url, api_key):
        try:
            genai.configure(api_key=api_key)
            self.log(f"▶ [1단계] 시작: {url}")
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                self.streamer_name = info.get('uploader') or info.get('uploader_id') or "알 수 없는 방송인"
                title = info.get('title') or (info['entries'][0]['title'] if 'entries' in info else 'VOD')
            
            self.log(f"👤 방송인: {self.streamer_name}")
            vod_folder = self.prepare_vod_folder(title)
            self.log(f"📂 폴더 생성: {self.video_title}")

            if not self.is_running: return

            ydl_opts = {
                'paths': {'home': vod_folder},
                'format': 'bestaudio/worst',
                'outtmpl': '%(autonumber)s_%(title)s.%(ext)s',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}],
                'ffmpeg_location': BASE_DIR, 
                'noplaylist': False, 'quiet': True, 'no_warnings': True,
                'progress_hooks': [self.progress_hook],
                'external_downloader': ARIA2C_PATH if os.path.exists(ARIA2C_PATH) else None,
                'external_downloader_args': ['-x', '8', '-k', '1M'] if os.path.exists(ARIA2C_PATH) else None
            }
            final_mp3 = os.path.join(vod_folder, f"{self.video_title}_통합본.mp3")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if 'entries' in info:
                    self.log(f"📢 다중 파트 감지")
                    ydl.download([url])
                    if not self.is_running: return
                    time.sleep(2)
                    files = sorted([os.path.join(vod_folder, f) for f in os.listdir(vod_folder) if f.endswith(".mp3") and "통합본" not in f])
                    if len(files) > 1:
                        self.status_var.set("🔄 [병합] 파일 합치는 중...")
                        self.merge_audios(files, final_mp3)
                    elif files: os.rename(files[0], final_mp3)
                else:
                    ydl.download([url])
                    files = glob.glob(os.path.join(vod_folder, "*.mp3"))
                    if files: os.rename(max(files, key=os.path.getmtime), final_mp3)

            if not self.is_running: return
            self.full_audio_path = final_mp3
            self.log("✅ 통합본 생성 완료")
            self.split_files = self.split_audio(final_mp3, vod_folder)
            self.log(f"✂️ {len(self.split_files)}개 파트 분할 완료")
            self.status_var.set(f"준비 완료! ({len(self.split_files)}개 파트)")
            self.progress.set(1.0)
            self.enable_analysis_buttons()
        except Exception as e:
            if str(e) == "사용자 중단": self.log("⛔ 다운로드 중단됨")
            else: self.log(f"❌ 오류: {e}")
            self.btn_prep.configure(state="normal")
            self.btn_load.configure(state="normal")
            self.btn_manual.configure(state="normal")
            self.btn_stop.configure(state="disabled")

    def merge_audios(self, files, output):
        list_txt = os.path.join(self.current_vod_folder, "merge_list.txt")
        with open(list_txt, "w", encoding="utf-8") as f:
            for p in files: f.write(f"file '{p}'\n")
        subprocess.run([FFMPEG_PATH, "-f", "concat", "-safe", "0", "-i", list_txt, "-c", "copy", "-y", output], 
                       check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try: os.remove(list_txt); [os.remove(p) for p in files]
        except: pass

    def split_audio(self, path, folder):
        self.status_var.set("✂️ [분할] 1시간 단위 자르는 중... (시간 소요)")
        out = os.path.join(folder, f"{self.video_title}_Part%03d.mp3")
        subprocess.run([FFMPEG_PATH, "-i", path, "-f", "segment", "-segment_time", "3600", "-c", "copy", "-reset_timestamps", "1", out],
                       check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        all_files = sorted(os.listdir(folder))
        prefix = f"{self.video_title}_Part"
        file_list = []
        idx = 0
        for f in all_files:
            if f.startswith(prefix) and f.endswith(".mp3"):
                file_list.append((idx, os.path.join(folder, f)))
                idx += 1
        return file_list

    def load_local_file_thread(self):
        key = self.api_key.get().strip()
        if not key: return messagebox.showwarning("경고", "API Key 입력")
        f = filedialog.askopenfilename(initialdir=self.save_dir.get(), title="통합 MP3 선택", filetypes=[("Audio", "*.mp3")])
        if f:
            self.btn_load.configure(state="disabled")
            self.btn_prep.configure(state="disabled")
            threading.Thread(target=self._process_local_file, args=(f,), daemon=True).start()

    def _process_local_file(self, f):
        try:
            self.streamer_name = "알 수 없는 방송인"
            title = os.path.splitext(os.path.basename(f))[0].replace("_통합본", "")
            folder = self.prepare_vod_folder(title)
            new_path = os.path.join(folder, os.path.basename(f))
            self.status_var.set("📂 파일 이동 및 준비 중...")
            if os.path.abspath(f) != os.path.abspath(new_path): shutil.move(f, new_path)
            self.full_audio_path = new_path
            self.log(f"📂 파일 로드: {title}")
            self.split_files = self.split_audio(new_path, folder)
            self.log(f"✅ {len(self.split_files)}개 파트 분할됨")
            self.status_var.set(f"준비 완료! ({len(self.split_files)}개 파트)")
            self.enable_analysis_buttons()
        except Exception as e:
            self.log(f"❌ 오류: {e}")
            self.btn_load.configure(state="normal")
            self.btn_prep.configure(state="normal")

    def load_manual_part(self):
        key = self.api_key.get().strip()
        if not key: return messagebox.showwarning("경고", "API Key 입력")
        f = filedialog.askopenfilename(initialdir=self.save_dir.get(), title="파트 파일(002 등) 선택", filetypes=[("Audio", "*.mp3")])
        if f:
            self.streamer_name = "수동 로드"
            filename = os.path.basename(f)
            self.current_vod_folder = os.path.dirname(f)
            self.video_title = filename.split("_Part")[0]
            try: part_idx = int(re.search(r'Part(\d+)', filename).group(1))
            except: part_idx = 0; self.log("⚠️ 파트 번호 인식 실패 -> 0번(1부) 간주")
            self.split_files = [(part_idx, f)]
            self.log(f"📂 수동 로드: {filename}")
            self.enable_analysis_buttons()

    def enable_analysis_buttons(self):
        self.btn_detail.configure(state="normal")
        self.btn_timeline.configure(state="normal")
        self.btn_prep.configure(text="✅ 완료")
        self.btn_load.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def run_contextual_analysis(self, mode):
        if not self.split_files: return
        self.is_running = True
        self.btn_stop.configure(state="normal")
        threading.Thread(target=self.thread_context_analyze, args=(mode,), daemon=True).start()

    def thread_context_analyze(self, mode):
        try:
            genai.configure(api_key=self.api_key.get().strip())
            model = genai.GenerativeModel(GEMINI_MODEL)
            safety = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            self.log(f"\n{'='*40}\n🚀 2단계 분석 시작 (STT -> Summary)\n{'='*40}")
            
            accumulated_context = "이전 내용 없음."
            full_text_buffer = "" 
            total_parts = len(self.split_files)
            
            start_time = time.time()
            avg_time = 0

            for i, (real_idx, file_path) in enumerate(self.split_files):
                if not self.is_running: break
                part_start = time.time()
                part_display = real_idx 
                
                eta_msg = ""
                if i > 0:
                    remain = total_parts - i
                    est = int(avg_time * remain)
                    eta_msg = f" | 남은 시간: 약 {est//60}분 {est%60}초"

                # [상태 1] 업로드 중
                self.status_var.set(f"☁️ [Part {part_display}] 파일 업로드 중... (서버 전송) {eta_msg}")
                audio = genai.upload_file(path=file_path)
                
                # [상태 2] 처리 대기 중
                while audio.state.name == "PROCESSING":
                    self.status_var.set(f"⚙️ [Part {part_display}] 구글 서버 처리 대기 중... {eta_msg}")
                    time.sleep(1)
                
                # --- Step 1: STT (대본 작성) ---
                self.status_var.set(f"✍️ [Part {part_display}] AI가 받아쓰기(STT) 중... {eta_msg}")
                
                stt_prompt = f"""
                당신은 전문 속기사입니다.
                이 오디오 파일(방송 Part {part_display})을 듣고 **들리는 그대로 받아쓰기(Transcript)**하세요.
                
                [주의사항]
                1. 요약하지 마세요. 대화 내용을 있는 그대로 적으세요.
                2. 화자를 구분하여 적으세요 (예: 화자1, 화자2).
                3. 노래 가사나 팝송이 나오면 가사를 적지 말고 **(음악 감상 중)** 이라고만 적으세요. (저작권 보호)
                4. 언어는 한국어로 적되, 영어가 들리면 한국어 발음이나 의미로 적으세요.
                """
                
                script_text = ""
                success_stt = False
                
                for attempt in range(3):
                    if not self.is_running: break
                    try:
                        res = model.generate_content([stt_prompt, audio], safety_settings=safety)
                        if not res.text: script_text = "(내용 없음 - 차단됨)"
                        else: script_text = res.text
                        success_stt = True
                        break
                    except Exception as e:
                        if "429" in str(e): 
                            self.status_var.set(f"⚠️ 용량 초과! 30초 대기 후 재시도 ({attempt+1}/3)")
                            time.sleep(30)
                        else: time.sleep(5)
                
                if not success_stt:
                    self.log(f"⛔ Part {part_display} STT 실패. 중단.")
                    self.is_running = False
                    break

                script_fname = f"{self.video_title}_Part{part_display:03d}_script.txt"
                with open(os.path.join(self.current_vod_folder, script_fname), "w", encoding="utf-8") as f:
                    f.write(script_text)
                
                # --- Step 2: Summary (요약 정리) ---
                if mode == "detail":
                    self.status_var.set(f"📝 [Part {part_display}] 요약 정리 및 분석 중... {eta_msg}")
                    
                    summary_prompt = f"""
                    당신은 전문 방송 에디터입니다.
                    아래는 방송(Part {part_display})의 **녹취록(Script)**입니다.
                    이 내용을 바탕으로 **깔끔한 요약 정리본**을 작성하세요.

                    [이전 문맥]: {accumulated_context[:2000]}

                    [녹취록 내용]:
                    {script_text[:15000]} (너무 길면 일부 생략)

                    [지시사항]
                    1. 녹취록을 읽고 핵심 흐름, 주요 주제, 재미있는 에피소드를 정리하세요.
                    2. 문장은 자연스러운 줄글로 다듬으세요.
                    3. 타임스탬프는 적지 마세요.
                    """
                    
                    final_result = ""
                    try:
                        res_sum = model.generate_content(summary_prompt)
                        final_result = res_sum.text
                    except: final_result = "요약 생성 실패"

                    summary_fname = f"{self.video_title}_Part{part_display:03d}_summary.txt"
                    with open(os.path.join(self.current_vod_folder, summary_fname), "w", encoding="utf-8") as f:
                        f.write(final_result)
                    
                    full_text_buffer += f"\n\n[Part {part_display}]\n{final_result}"
                    accumulated_context = final_result[:2000]

                elif mode == "timeline":
                    pass 

                try: genai.delete_file(audio.name)
                except: pass
                
                dur = time.time() - part_start
                if i==0: avg_time = dur + 20
                else: avg_time = (avg_time + dur + 20) / 2

                self.log(f"✅ Part {part_display} 완료 (STT+요약)")
                
                if i < total_parts - 1:
                    if not self.is_running: break
                    self.status_var.set(f"💤 쿨타임 대기 중... (20초)")
                    time.sleep(20)

            if self.is_running and mode == "detail":
                self.log("\n🔨 [최종] 통합 요약본 생성 중...")
                full_path = os.path.join(self.current_vod_folder, f"{self.video_title}_전체_요약.txt")
                with open(full_path, "w", encoding="utf-8") as f: f.write(full_text_buffer)
                self.status_var.set("모든 작업 완료!")
                os.startfile(self.current_vod_folder)
            else:
                self.log("⛔ 작업이 중단되었습니다.")

        except Exception as e:
            self.log(f"❌ 오류: {e}")
            self.status_var.set("분석 오류")
        finally:
            self.btn_stop.configure(state="disabled")
            self.btn_prep.configure(state="normal")
            self.btn_load.configure(state="normal")
            self.btn_manual.configure(state="normal")

    def send_chat(self, event=None): pass

if __name__ == "__main__":
    app = SoopProApp()
    app.mainloop()