import glob
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import warnings
from dataclasses import dataclass
from tkinter import filedialog, messagebox

import customtkinter as ctk
import yt_dlp

warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")
ARIA2C_PATH = os.path.join(BASE_DIR, "aria2c.exe")
GEMINI_MODEL = "gemini-2.5-flash"
USE_ARIA2 = False


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


@dataclass
class SegmentFile:
    index: int
    path: str


class CancelledError(Exception):
    pass


class SoopLocalSummarizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SOOP Local Summarizer V2")
        self.geometry("980x900")
        self.minsize(980, 900)

        self.api_key = ctk.StringVar()
        self.save_dir = ctk.StringVar()
        self.url_var = ctk.StringVar()
        self.language_var = ctk.StringVar(value="ko")
        self.segment_minutes_var = ctk.StringVar(value="60")
        self.model_size_var = ctk.StringVar(value="medium")
        self.device_var = ctk.StringVar(value="cpu")
        self.compute_type_var = ctk.StringVar(value="int8")
        self.status_var = ctk.StringVar(value="Idle")

        self.worker_thread = None
        self.cancel_event = threading.Event()
        self.ui_queue = queue.Queue()
        self.current_job_folder = None

        self._build_ui()
        self._load_config()
        self.after(150, self._drain_ui_queue)

    def _build_ui(self):
        header = ctk.CTkLabel(
            self,
            text="SOOP Local STT + Gemini Summary",
            font=("Arial", 24, "bold"),
        )
        header.pack(pady=(16, 10))

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(top, text="Gemini API Key").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        ctk.CTkEntry(top, textvariable=self.api_key, show="*", width=320).grid(
            row=0, column=1, sticky="w", padx=10, pady=8
        )
        ctk.CTkLabel(top, text="Save Folder").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ctk.CTkEntry(top, textvariable=self.save_dir, width=520).grid(
            row=1, column=1, sticky="we", padx=10, pady=8
        )
        ctk.CTkButton(top, text="Browse", width=90, command=self._choose_dir).grid(
            row=1, column=2, padx=10, pady=8
        )
        top.grid_columnconfigure(1, weight=1)

        url_frame = ctk.CTkFrame(self)
        url_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(url_frame, text="VOD URL").pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkEntry(
            url_frame,
            textvariable=self.url_var,
            placeholder_text="https://...",
            height=38,
        ).pack(fill="x", padx=10, pady=(6, 10))

        options = ctk.CTkFrame(self)
        options.pack(fill="x", padx=20, pady=8)

        self._build_option_menu(options, "Language", self.language_var, ["ko", "auto", "en"], 0)
        self._build_option_menu(options, "Chunk Minutes", self.segment_minutes_var, ["60", "30", "15"], 1)
        self._build_option_menu(options, "Whisper Model", self.model_size_var, ["medium", "small", "large-v3"], 2)
        self._build_option_menu(options, "Device", self.device_var, ["cpu", "auto", "cuda"], 3)
        self._build_option_menu(options, "Compute", self.compute_type_var, ["int8", "int8_float16", "float16"], 4)

        actions = ctk.CTkFrame(self)
        actions.pack(fill="x", padx=20, pady=8)
        self.start_button = ctk.CTkButton(
            actions,
            text="Run Pipeline",
            height=42,
            fg_color="#14853B",
            hover_color="#106B2F",
            command=self._start_pipeline,
        )
        self.start_button.pack(side="left", fill="x", expand=True, padx=(10, 6), pady=10)
        self.cancel_button = ctk.CTkButton(
            actions,
            text="Cancel",
            height=42,
            fg_color="#9E2A2B",
            hover_color="#7F1F20",
            state="disabled",
            command=self._cancel_pipeline,
        )
        self.cancel_button.pack(side="left", fill="x", expand=True, padx=(6, 10), pady=10)

        self.progress = ctk.CTkProgressBar(self, width=900)
        self.progress.pack(padx=20, pady=(6, 2))
        self.progress.set(0)

        ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            font=("Consolas", 12),
            text_color="#F4C542",
            wraplength=900,
        ).pack(padx=20, pady=(0, 8))

        self.log_box = ctk.CTkTextbox(self, font=("Consolas", 12))
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    def _build_option_menu(self, parent, label, variable, values, column):
        box = ctk.CTkFrame(parent)
        box.grid(row=0, column=column, sticky="nsew", padx=6, pady=10)
        ctk.CTkLabel(box, text=label).pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkOptionMenu(box, values=values, variable=variable, width=150).pack(
            padx=10, pady=(6, 10)
        )
        parent.grid_columnconfigure(column, weight=1)

    def _choose_dir(self):
        selected = filedialog.askdirectory()
        if selected:
            self.save_dir.set(selected)
            self._save_config()

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            self.save_dir.set(BASE_DIR)
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            self.save_dir.set(BASE_DIR)
            return

        self.api_key.set(data.get("api_key", ""))
        self.save_dir.set(data.get("save_dir", BASE_DIR))
        self.language_var.set(data.get("stt_language", "ko"))
        self.segment_minutes_var.set(str(data.get("segment_minutes", "60")))
        self.model_size_var.set(data.get("stt_model_size", "medium"))
        self.device_var.set(data.get("stt_device", "cpu"))
        self.compute_type_var.set(data.get("stt_compute_type", "int8"))

    def _save_config(self):
        data = {
            "api_key": self.api_key.get().strip(),
            "save_dir": self.save_dir.get().strip() or BASE_DIR,
            "stt_language": self.language_var.get().strip(),
            "segment_minutes": self.segment_minutes_var.get().strip(),
            "stt_model_size": self.model_size_var.get().strip(),
            "stt_device": self.device_var.get().strip(),
            "stt_compute_type": self.compute_type_var.get().strip(),
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def _start_pipeline(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if not self.url_var.get().strip():
            messagebox.showwarning("Missing URL", "Enter a SOOP VOD URL first.")
            return
        if not self.save_dir.get().strip():
            messagebox.showwarning("Missing folder", "Choose a save folder first.")
            return
        if not os.path.exists(FFMPEG_PATH):
            messagebox.showerror("Missing ffmpeg", f"ffmpeg.exe not found:\n{FFMPEG_PATH}")
            return
        if WhisperModel is None:
            messagebox.showerror(
                "Missing dependency",
                "faster-whisper is not installed. Install it before running this app.",
            )
            return
        if genai is None:
            messagebox.showerror(
                "Missing dependency",
                "google-generativeai is not installed. Install it before running this app.",
            )
            return
        if not self.api_key.get().strip():
            messagebox.showwarning("Missing API key", "Enter a Gemini API key first.")
            return

        self._save_config()
        self.cancel_event.clear()
        self.progress.set(0)
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._log("Pipeline started.")

        self.worker_thread = threading.Thread(target=self._run_pipeline, daemon=True)
        self.worker_thread.start()

    def _cancel_pipeline(self):
        self.cancel_event.set()
        self.status_var.set("Cancelling...")
        self._log("Cancel requested.")

    def _run_pipeline(self):
        try:
            folder, title, merged_audio = self._download_and_prepare_audio()
            self.current_job_folder = folder
            segments = self._split_audio(merged_audio, folder)
            transcript_files = self._run_local_stt(folder, segments)
            self._run_gemini_summary(folder, title, transcript_files)
            self._emit("status", "Completed")
            self._emit("progress", 1.0)
            self._emit("log", f"Done. Output folder: {folder}")
            self._emit("open_folder", folder)
        except CancelledError:
            self._emit("status", "Cancelled")
            self._emit("log", "Pipeline cancelled.")
        except Exception as exc:
            self._emit("status", "Failed")
            self._emit("log", f"Error: {exc}")
        finally:
            self._emit("controls", {"start": "normal", "cancel": "disabled"})

    def _download_and_prepare_audio(self):
        self._check_cancelled()
        self._emit("status", "Reading VOD metadata...")
        self._emit("progress", 0.03)

        output_root = self.save_dir.get().strip()
        os.makedirs(output_root, exist_ok=True)

        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as probe:
            info = probe.extract_info(self.url_var.get().strip(), download=False)

        title = info.get("title") or "SOOP_VOD"
        safe_title = self._safe_name(title, max_length=80)
        folder = os.path.join(output_root, safe_title)
        os.makedirs(folder, exist_ok=True)

        self._emit("log", f"Job folder: {folder}")
        self._emit("status", "Downloading low bitrate audio...")

        ydl_opts = {
            "paths": {"home": folder},
            "format": "worstaudio/worst",
            "outtmpl": "%(autonumber)s_%(title)s.%(ext)s",
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": BASE_DIR,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "48",
                }
            ],
            "postprocessor_args": [
                "-ac",
                "1",
                "-ar",
                "16000",
                "-map_metadata",
                "-1",
            ],
        }
        if USE_ARIA2 and os.path.exists(ARIA2C_PATH):
            ydl_opts["external_downloader"] = ARIA2C_PATH
            ydl_opts["external_downloader_args"] = ["-x", "8", "-k", "1M"]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([self.url_var.get().strip()])

        self._check_cancelled()
        self._emit("progress", 0.18)

        mp3_files = [
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if name.lower().endswith(".mp3") and "_merged.mp3" not in name.lower()
        ]
        if not mp3_files:
            raise RuntimeError("No MP3 file was created by yt-dlp.")

        merged_audio = os.path.join(folder, "merged.mp3")
        if len(mp3_files) == 1:
            source = max(mp3_files, key=os.path.getmtime)
            if os.path.abspath(source) != os.path.abspath(merged_audio):
                shutil.move(source, merged_audio)
        else:
            self._emit("status", "Merging playlist audio...")
            self._merge_audio_files(sorted(mp3_files), merged_audio, folder)

        return folder, safe_title, merged_audio

    def _split_audio(self, audio_path, folder):
        self._check_cancelled()
        minutes = max(5, int(self.segment_minutes_var.get().strip() or "60"))
        segment_seconds = minutes * 60
        self._emit("status", f"Splitting audio every {minutes} minutes...")

        pattern = os.path.join(folder, "part%03d.mp3")
        command = [
            FFMPEG_PATH,
            "-y",
            "-i",
            audio_path,
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-c",
            "copy",
            "-reset_timestamps",
            "1",
            pattern,
        ]
        self._run_subprocess(command)

        segment_paths = sorted(glob.glob(os.path.join(folder, "part*.mp3")))
        if not segment_paths:
            raise RuntimeError("Audio split failed. No segment file was produced.")

        self._emit("progress", 0.28)
        self._emit("log", f"Split complete: {len(segment_paths)} segment(s)")
        return [SegmentFile(index=index, path=path) for index, path in enumerate(segment_paths)]

    def _run_local_stt(self, folder, segments):
        self._check_cancelled()
        self._emit("status", "Loading local Whisper model...")

        device = self.device_var.get().strip()
        if device == "auto":
            device = "cpu"
        compute_type = self.compute_type_var.get().strip()
        model_size = self.model_size_var.get().strip()

        try:
            model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as exc:
            if device != "cpu":
                self._emit("log", f"Whisper init failed on device={device}. Falling back to CPU int8. ({exc})")
                model = WhisperModel(model_size, device="cpu", compute_type="int8")
            else:
                raise
        language = self.language_var.get().strip()
        transcript_files = []

        total = len(segments)
        for offset, segment in enumerate(segments, start=1):
            self._check_cancelled()
            segment_label = f"{offset}/{total}"
            self._emit("status", f"Local STT {segment_label}")
            self._emit("log", f"Transcribing: {os.path.basename(segment.path)}")

            transcribe_kwargs = {
                "beam_size": 1,
                "best_of": 1,
                "vad_filter": True,
                "condition_on_previous_text": False,
                "word_timestamps": False,
                "temperature": 0.0,
            }
            if language != "auto":
                transcribe_kwargs["language"] = language

            stt_start = time.time()
            segments_iter, info = model.transcribe(segment.path, **transcribe_kwargs)
            transcript_segments = []
            for piece in segments_iter:
                transcript_segments.append(
                    {
                        "start": round(piece.start, 2),
                        "end": round(piece.end, 2),
                        "text": piece.text.strip(),
                    }
                )
            elapsed = time.time() - stt_start
            self._emit(
                "log",
                f"STT complete: {segment_label} in {elapsed:.1f}s, language={getattr(info, 'language', 'unknown')}",
            )

            text_path = os.path.join(folder, f"part_{segment.index:03d}_transcript.txt")
            json_path = os.path.join(folder, f"part_{segment.index:03d}_segments.json")
            with open(text_path, "w", encoding="utf-8") as file:
                file.write(self._segments_to_text(transcript_segments))
            with open(json_path, "w", encoding="utf-8") as file:
                json.dump(transcript_segments, file, ensure_ascii=False, indent=2)

            transcript_files.append({"segment": segment, "text_path": text_path, "json_path": json_path})
            progress = 0.28 + (0.44 * (offset / max(1, total)))
            self._emit("progress", progress)

        return transcript_files

    def _run_gemini_summary(self, folder, title, transcript_files):
        self._check_cancelled()
        self._emit("status", "Running Gemini summary...")
        genai.configure(api_key=self.api_key.get().strip())
        model = genai.GenerativeModel(GEMINI_MODEL)

        per_part_summaries = []
        full_transcript_blocks = []
        total = len(transcript_files)

        for offset, item in enumerate(transcript_files, start=1):
            self._check_cancelled()
            with open(item["text_path"], "r", encoding="utf-8") as file:
                transcript_text = file.read().strip()

            if not transcript_text:
                summary_text = "(empty transcript)"
            else:
                prompt = self._build_part_summary_prompt(title, item["segment"].index, transcript_text)
                response = model.generate_content(prompt)
                summary_text = (response.text or "").strip() or "(no summary)"

            out_path = os.path.join(folder, f"part_{item['segment'].index:03d}_summary.txt")
            with open(out_path, "w", encoding="utf-8") as file:
                file.write(summary_text)

            per_part_summaries.append(f"[Part {item['segment'].index:03d}]\n{summary_text}")
            full_transcript_blocks.append(f"[Part {item['segment'].index:03d}]\n{transcript_text}")

            progress = 0.72 + (0.18 * (offset / max(1, total)))
            self._emit("progress", progress)
            self._emit("log", f"Gemini summary complete: {offset}/{total}")

        combined_summary_text = "\n\n".join(per_part_summaries)
        combined_summary_path = os.path.join(folder, "combined_part_summaries.txt")
        with open(combined_summary_path, "w", encoding="utf-8") as file:
            file.write(combined_summary_text)

        final_prompt = self._build_final_summary_prompt(title, combined_summary_text)
        final_response = model.generate_content(final_prompt)
        final_text = (final_response.text or "").strip() or "(no final summary)"

        with open(os.path.join(folder, "final_summary.txt"), "w", encoding="utf-8") as file:
            file.write(final_text)
        with open(os.path.join(folder, "full_transcript.txt"), "w", encoding="utf-8") as file:
            file.write("\n\n".join(full_transcript_blocks))

    def _build_part_summary_prompt(self, title, part_index, transcript_text):
        clipped = transcript_text[:18000]
        return f"""
You summarize Korean livestream transcripts.

Title: {title}
Part index: {part_index}

Write in Korean.
Goals:
1. Summarize the flow of this part in bullet points.
2. Extract notable moments with timestamps from the transcript.
3. Keep names, games, events, and decisions when they appear.
4. Do not invent anything that is not grounded in the transcript.

Transcript:
{clipped}
"""

    def _build_final_summary_prompt(self, title, combined_summary_text):
        clipped = combined_summary_text[:22000]
        return f"""
You are creating a final Korean recap for one SOOP VOD.

Title: {title}

Using the part summaries below, produce:
1. A short overall summary.
2. A timeline section with timestamps when possible.
3. Key highlights.
4. A short list of topics that dominated the stream.

Part summaries:
{clipped}
"""

    def _merge_audio_files(self, files, output_path, folder):
        list_file = os.path.join(folder, "merge_list.txt")
        with open(list_file, "w", encoding="utf-8") as file:
            for path in files:
                normalized = path.replace("\\", "/").replace("'", "'\\''")
                file.write(f"file '{normalized}'\n")

        command = [
            FFMPEG_PATH,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c",
            "copy",
            output_path,
        ]
        self._run_subprocess(command)

        try:
            os.remove(list_file)
            for path in files:
                if os.path.exists(path):
                    os.remove(path)
        except OSError:
            pass

    def _run_subprocess(self, command):
        self._check_cancelled()
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        while True:
            if self.cancel_event.is_set():
                process.kill()
                raise CancelledError()
            code = process.poll()
            if code is not None:
                break
            time.sleep(0.2)

        stdout, stderr = process.communicate()
        stdout_text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else (stdout or "")
        stderr_text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else (stderr or "")
        if code != 0:
            detail = stderr_text.strip() or stdout_text.strip() or "subprocess failed"
            raise RuntimeError(detail)

    def _segments_to_text(self, transcript_segments):
        lines = []
        for item in transcript_segments:
            ts = self._format_seconds(item["start"])
            text = item["text"].strip()
            if text:
                lines.append(f"[{ts}] {text}")
        return "\n".join(lines)

    def _format_seconds(self, value):
        total = int(value)
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _safe_name(self, value, max_length=120):
        cleaned = re.sub(r'[\\/*?:"<>|]+', "", value).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length].rstrip()
        return cleaned or "SOOP_VOD"

    def _check_cancelled(self):
        if self.cancel_event.is_set():
            raise CancelledError()

    def _emit(self, kind, value):
        self.ui_queue.put((kind, value))

    def _log(self, text):
        self.log_box.insert("end", f"{text}\n")
        self.log_box.see("end")

    def _drain_ui_queue(self):
        while True:
            try:
                kind, value = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._log(value)
            elif kind == "status":
                self.status_var.set(value)
            elif kind == "progress":
                self.progress.set(value)
            elif kind == "controls":
                self.start_button.configure(state=value["start"])
                self.cancel_button.configure(state=value["cancel"])
            elif kind == "open_folder":
                try:
                    os.startfile(value)
                except OSError:
                    pass

        self.after(150, self._drain_ui_queue)


if __name__ == "__main__":
    app = SoopLocalSummarizerApp()
    app.mainloop()
