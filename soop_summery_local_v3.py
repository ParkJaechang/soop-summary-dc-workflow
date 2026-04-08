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
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk
import yt_dlp

warnings.simplefilter("ignore", FutureWarning)

try:
    from faster_whisper import WhisperModel
    try:
        from faster_whisper import BatchedInferencePipeline
    except ImportError:
        BatchedInferencePipeline = None
except ImportError:
    WhisperModel = None
    BatchedInferencePipeline = None

try:
    import google.generativeai as legacy_genai
except ImportError:
    legacy_genai = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")
FFPROBE_PATH = os.path.join(BASE_DIR, "ffprobe.exe")
GEMINI_MODEL = "gemini-2.5-flash"
SUMMARY_CONTEXT_VERSION = "summary_job_context.v1"
SUMMARY_PAYLOAD_VERSION = "summary_payload.v1"


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


@dataclass
class SegmentFile:
    index: int
    path: str
    duration: float
    start_offset: float


class CancelledError(Exception):
    pass


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_soop_url(url):
    normalized = (url or "").strip()
    if re.match(r"^https?://vod\.sooplive\.com/", normalized, re.IGNORECASE):
        normalized = re.sub(
            r"^https?://vod\.sooplive\.com",
            "https://vod.sooplive.co.kr",
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


def read_json_file(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def read_text_file(path):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except Exception:
        return ""


def extract_soop_source_identity(source_url):
    canonical_source_url = normalize_soop_url(source_url)
    source_id = ""
    source_kind = ""

    patterns = [
        (r"vod\.sooplive\.co\.kr/player/(\d+)", "vod_player"),
        (r"sooplive\.co\.kr/station/([A-Za-z0-9_]+)", "station"),
        (r"ch\.sooplive\.co\.kr/([A-Za-z0-9_]+)", "channel"),
    ]
    for pattern, kind in patterns:
        match = re.search(pattern, canonical_source_url, re.IGNORECASE)
        if match:
            source_id = match.group(1)
            source_kind = kind
            break

    return {
        "platform": "soop",
        "content_type": "vod",
        "source_url": canonical_source_url,
        "canonical_source_url": canonical_source_url,
        "source_id": source_id,
        "source_kind": source_kind or ("unknown" if canonical_source_url else ""),
    }


def write_summary_job_context(folder, title, source_url="", info=None):
    info = info or {}
    context_path = os.path.join(folder, "summary_job_context.json")
    existing = read_json_file(context_path, default={})
    resolved_source_url = normalize_soop_url(source_url or existing.get("canonical_source_url") or existing.get("source_url") or "")
    source_identity = extract_soop_source_identity(resolved_source_url)
    saved_at = now_iso()

    raw_entry_count = info.get("entries")
    if isinstance(raw_entry_count, list):
        entry_count = len(raw_entry_count)
    elif raw_entry_count is None:
        entry_count = existing.get("entry_count")
    else:
        entry_count = raw_entry_count

    context = {
        "context_version": SUMMARY_CONTEXT_VERSION,
        "saved_at": saved_at,
        "downloaded_at": existing.get("downloaded_at") or saved_at,
        "title": (title or "").strip() or existing.get("title") or os.path.basename(folder),
        "original_title": info.get("title") or existing.get("original_title") or "",
        "source_url": resolved_source_url,
        "canonical_source_url": source_identity["canonical_source_url"],
        "source_id": info.get("id") or existing.get("source_id") or source_identity["source_id"],
        "source_kind": source_identity["source_kind"] or existing.get("source_kind") or "",
        "extractor": info.get("extractor") or existing.get("extractor") or "",
        "uploader": info.get("uploader") or info.get("channel") or existing.get("uploader") or "",
        "duration_seconds": info.get("duration") if info.get("duration") is not None else existing.get("duration_seconds"),
        "entry_count": entry_count,
    }
    with open(context_path, "w", encoding="utf-8") as file:
        json.dump(context, file, ensure_ascii=False, indent=2)
    return context_path, context


def build_summary_payload_artifact(folder, title="", source_url="", reference_notes="", summary_mode="full_transcript"):
    folder = os.path.abspath(folder)
    summaries_dir = os.path.join(folder, "summaries")
    transcripts_dir = os.path.join(folder, "transcripts")
    context_path = os.path.join(folder, "summary_job_context.json")
    context = read_json_file(context_path, default={})

    resolved_title = (title or "").strip() or context.get("title") or os.path.basename(folder)
    resolved_source_url = normalize_soop_url(source_url or context.get("canonical_source_url") or context.get("source_url") or "")
    resolved_reference_notes = (reference_notes or "").strip()
    source_identity = extract_soop_source_identity(resolved_source_url)

    final_summary_path = os.path.join(summaries_dir, "final_summary.txt")
    timeline_path = os.path.join(summaries_dir, "timeline.txt")
    cleaned_script_path = os.path.join(summaries_dir, "cleaned_full_script.txt")
    full_transcript_path = os.path.join(transcripts_dir, "full_transcript.txt")
    payload_path = os.path.join(summaries_dir, "summary_payload.json")

    body = read_text_file(final_summary_path) or read_text_file(timeline_path)
    if not body:
        raise RuntimeError("No final_summary.txt or timeline.txt was found for summary payload export.")

    transcript_part_count = len(glob.glob(os.path.join(transcripts_dir, "part_*_transcript.txt")))
    generated_at = now_iso()
    payload = {
        "contract_version": SUMMARY_PAYLOAD_VERSION,
        "producer": {
            "name": "soop_summery_local_v3.py",
            "generated_at": generated_at,
        },
        "title": resolved_title,
        "body": body,
        "metadata": {
            "source": source_identity,
            "summary": {
                "summary_mode": (summary_mode or "").strip() or "full_transcript",
                "body_format": "plain_text",
                "reference_notes": resolved_reference_notes,
                "reference_notes_present": bool(resolved_reference_notes),
                "generated_at": generated_at,
                "job_folder_name": os.path.basename(folder),
                "transcript_part_count": transcript_part_count,
            },
            "job_context": {
                "context_version": context.get("context_version") or "",
                "downloaded_at": context.get("downloaded_at") or "",
                "original_title": context.get("original_title") or "",
                "duration_seconds": context.get("duration_seconds"),
                "entry_count": context.get("entry_count"),
                "extractor": context.get("extractor") or "",
                "uploader": context.get("uploader") or "",
            },
            "artifacts": {
                "job_folder": folder,
                "full_transcript_path": full_transcript_path if os.path.exists(full_transcript_path) else "",
                "cleaned_full_script_path": cleaned_script_path if os.path.exists(cleaned_script_path) else "",
                "final_summary_path": final_summary_path if os.path.exists(final_summary_path) else "",
                "timeline_path": timeline_path if os.path.exists(timeline_path) else "",
                "payload_path": payload_path,
            },
        },
        "dedupe_basis": {
            "platform": "soop",
            "content_type": "vod",
            "canonical_source_url": source_identity["canonical_source_url"],
            "source_id": source_identity["source_id"],
            "source_kind": source_identity["source_kind"],
            "producer": "soop_summery_local_v3.py",
            "contract_version": SUMMARY_PAYLOAD_VERSION,
        },
    }

    os.makedirs(summaries_dir, exist_ok=True)
    with open(payload_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return payload_path, payload


class SoopLocalSummarizerV3(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SOOP Local Summarizer V3")
        self.geometry("1080x920")
        self.minsize(1080, 920)

        self.api_key = ctk.StringVar()
        self.save_dir = ctk.StringVar()
        self.url_var = ctk.StringVar()
        self.language_var = ctk.StringVar(value="ko")
        self.chunk_minutes_var = ctk.StringVar(value="15")
        self.model_var = ctk.StringVar(value="medium")
        self.compute_var = ctk.StringVar(value="int8")
        self.batch_var = ctk.StringVar(value="8")
        self.stt_profile_var = ctk.StringVar(value="balanced")
        self.summary_mode_var = ctk.StringVar(value="full_transcript")
        self.auto_summary_var = ctk.BooleanVar(value=False)
        self.status_var = ctk.StringVar(value="Idle")
        self.detail_var = ctk.StringVar(value="Ready")
        self.last_job_folder = None
        self.last_job_title = None
        self.last_transcript_paths = []
        self.last_pipeline_completed = False

        self.cancel_event = threading.Event()
        self.ui_queue = queue.Queue()
        self.worker_thread = None

        self._build_ui()
        self._load_config()
        self.after(120, self._drain_queue)

    def _build_ui(self):
        ctk.CTkLabel(
            self,
            text="SOOP Fast Local STT + Gemini Summary",
            font=("Arial", 24, "bold"),
        ).pack(pady=(14, 10))

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=18, pady=8)
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Gemini API Key").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        ctk.CTkEntry(top, textvariable=self.api_key, show="*", width=320).grid(
            row=0, column=1, sticky="we", padx=10, pady=8
        )
        ctk.CTkLabel(top, text="Save Folder").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ctk.CTkEntry(top, textvariable=self.save_dir, width=650).grid(
            row=1, column=1, sticky="we", padx=10, pady=8
        )
        ctk.CTkButton(top, text="Browse", width=90, command=self._choose_dir).grid(
            row=1, column=2, padx=10, pady=8
        )

        url_frame = ctk.CTkFrame(self)
        url_frame.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(url_frame, text="VOD URL").pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkEntry(url_frame, textvariable=self.url_var, height=38).pack(fill="x", padx=10, pady=(0, 10))

        notes_frame = ctk.CTkFrame(self)
        notes_frame.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(
            notes_frame,
            text="Gemini Reference Notes (names, nicknames, game titles, recurring words)",
        ).pack(anchor="w", padx=10, pady=(8, 2))
        self.reference_notes = ctk.CTkTextbox(notes_frame, height=92, font=("Consolas", 11))
        self.reference_notes.pack(fill="x", padx=10, pady=(0, 10))

        auto_frame = ctk.CTkFrame(self)
        auto_frame.pack(fill="x", padx=18, pady=8)
        ctk.CTkCheckBox(
            auto_frame,
            text="Auto run Gemini processing after Local STT",
            variable=self.auto_summary_var,
            onvalue=True,
            offvalue=False,
        ).pack(anchor="w", padx=12, pady=10)

        options = ctk.CTkFrame(self)
        options.pack(fill="x", padx=18, pady=8)
        for col in range(6):
            options.grid_columnconfigure(col, weight=1)

        self._add_option(options, "Language", self.language_var, ["ko", "auto", "en"], 0)
        self._add_option(options, "Chunk Minutes", self.chunk_minutes_var, ["10", "15", "20", "30"], 1)
        self._add_option(options, "Whisper Model", self.model_var, ["medium", "small", "base"], 2)
        self._add_option(options, "Compute", self.compute_var, ["int8", "int8_float16", "float16"], 3)
        self._add_option(options, "Batch Size", self.batch_var, ["8", "4", "2", "1"], 4)
        self._add_option(options, "STT Profile", self.stt_profile_var, ["balanced", "accurate"], 5)

        action = ctk.CTkFrame(self)
        action.pack(fill="x", padx=18, pady=8)
        self.run_button = ctk.CTkButton(
            action,
            text="Run Local STT",
            height=42,
            fg_color="#1A8F3E",
            hover_color="#156F31",
            command=self._start,
        )
        self.run_button.pack(side="left", fill="x", expand=True, padx=(10, 6), pady=10)
        self.summary_button = ctk.CTkButton(
            action,
            text="Run Gemini Summary",
            height=42,
            state="normal",
            fg_color="#235B9F",
            hover_color="#1B4A80",
            command=self._start_summary_only,
        )
        self.summary_button.pack(side="left", fill="x", expand=True, padx=(6, 6), pady=10)
        self.cancel_button = ctk.CTkButton(
            action,
            text="Cancel",
            height=42,
            state="disabled",
            fg_color="#9B2C2C",
            hover_color="#7D2323",
            command=self._cancel,
        )
        self.cancel_button.pack(side="left", fill="x", expand=True, padx=(6, 10), pady=10)

        self.total_progress = ctk.CTkProgressBar(self, width=1020)
        self.total_progress.pack(padx=18, pady=(6, 2))
        self.total_progress.set(0)

        self.stage_progress = ctk.CTkProgressBar(self, width=1020, progress_color="#E59C1F")
        self.stage_progress.pack(padx=18, pady=(2, 6))
        self.stage_progress.set(0)

        ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            font=("Consolas", 13, "bold"),
            text_color="#F3D45C",
            wraplength=1020,
        ).pack(padx=18, pady=(0, 2))
        ctk.CTkLabel(
            self,
            textvariable=self.detail_var,
            font=("Consolas", 12),
            text_color="#CFCFCF",
            wraplength=1020,
        ).pack(padx=18, pady=(0, 8))

        self.log_box = ctk.CTkTextbox(self, font=("Consolas", 12))
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def _add_option(self, parent, label, variable, values, column):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=column, sticky="nsew", padx=5, pady=10)
        ctk.CTkLabel(frame, text=label).pack(anchor="w", padx=10, pady=(8, 0))
        ctk.CTkOptionMenu(frame, variable=variable, values=values, width=145).pack(
            padx=10, pady=(6, 10)
        )

    def _choose_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.save_dir.set(path)
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

        if "api_key" in data:
            data.pop("api_key", None)
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as file:
                    json.dump(data, file, ensure_ascii=False, indent=2)
            except Exception:
                pass

        self.save_dir.set(data.get("save_dir", BASE_DIR))
        self.language_var.set(data.get("v3_language", data.get("stt_language", "ko")))
        self.chunk_minutes_var.set(str(data.get("v3_chunk_minutes", "15")))
        self.model_var.set(data.get("v3_model", "medium"))
        self.compute_var.set(data.get("v3_compute", "int8"))
        self.batch_var.set(str(data.get("v3_batch", "8")))
        self.stt_profile_var.set(data.get("v3_stt_profile", "balanced"))
        self.summary_mode_var.set(data.get("v3_summary_mode", "full_transcript"))
        self.auto_summary_var.set(bool(data.get("v3_auto_summary", False)))
        self.reference_notes.delete("1.0", "end")
        self.reference_notes.insert("1.0", data.get("v3_reference_notes", ""))

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            data = {}

        data.pop("api_key", None)

        data.update(
            {
                "save_dir": self.save_dir.get().strip() or BASE_DIR,
                "v3_language": self.language_var.get().strip(),
                "v3_chunk_minutes": self.chunk_minutes_var.get().strip(),
                "v3_model": self.model_var.get().strip(),
                "v3_compute": self.compute_var.get().strip(),
                "v3_batch": self.batch_var.get().strip(),
                "v3_stt_profile": self.stt_profile_var.get().strip(),
                "v3_summary_mode": "full_transcript",
                "v3_auto_summary": bool(self.auto_summary_var.get()),
                "v3_reference_notes": self.reference_notes.get("1.0", "end").strip(),
            }
        )
        with open(CONFIG_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def _start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if WhisperModel is None:
            messagebox.showerror("Missing dependency", "faster-whisper is not installed.")
            return
        if not os.path.exists(FFMPEG_PATH):
            messagebox.showerror("Missing ffmpeg", f"Missing file:\n{FFMPEG_PATH}")
            return
        if not os.path.exists(FFPROBE_PATH):
            messagebox.showerror("Missing ffprobe", f"Missing file:\n{FFPROBE_PATH}")
            return
        if not self.url_var.get().strip():
            messagebox.showwarning("Missing URL", "VOD URL is required.")
            return
        normalized_url = self._normalize_soop_url(self.url_var.get().strip())
        if normalized_url != self.url_var.get().strip():
            self.url_var.set(normalized_url)
            self._ui_log(f"Normalized SOOP URL: {normalized_url}")
        if self.auto_summary_var.get() and legacy_genai is None:
            messagebox.showerror(
                "Missing dependency",
                "google-generativeai is required only when auto Gemini summary is enabled.",
            )
            return
        if self.auto_summary_var.get() and not self.api_key.get().strip():
            messagebox.showwarning(
                "Missing API key",
                "Gemini API key is required only when auto Gemini summary is enabled.",
            )
            return

        self._save_config()
        self.cancel_event.clear()
        self.last_pipeline_completed = False
        self.total_progress.set(0)
        self.stage_progress.set(0)
        self.run_button.configure(state="disabled")
        self.summary_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._ui_log("Local STT pipeline started.")

        self.worker_thread = threading.Thread(target=self._run, daemon=True)
        self.worker_thread.start()

    def _start_summary_only(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if legacy_genai is None:
            messagebox.showerror("Missing dependency", "google-generativeai is not installed.")
            return
        if not self.api_key.get().strip():
            messagebox.showwarning("Missing API key", "Gemini API key is required.")
            return
        if not self.last_job_folder or not self.last_transcript_paths:
            selected = filedialog.askdirectory(
                initialdir=self.save_dir.get().strip() or BASE_DIR,
                title="Select an existing job folder",
            )
            if not selected:
                return

            transcript_paths = self._load_transcript_paths_from_folder(selected)
            if not transcript_paths:
                messagebox.showwarning(
                    "No transcript",
                    "The selected folder does not contain transcript files.",
                )
                return

            self.last_job_folder = selected
            self.last_job_title = os.path.basename(selected)
            self.last_transcript_paths = transcript_paths
            self.last_pipeline_completed = True
            self._emit("log", f"Loaded existing job folder: {selected}")

        self._save_config()
        self.cancel_event.clear()
        self.run_button.configure(state="disabled")
        self.summary_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._ui_log("Gemini summary started.")

        self.worker_thread = threading.Thread(target=self._run_summary_only, daemon=True)
        self.worker_thread.start()

    def _cancel(self):
        self.cancel_event.set()
        self.status_var.set("Cancelling...")
        self.detail_var.set("Stopping current task...")
        self._ui_log("Cancel requested.")

    def _run(self):
        started = time.time()
        try:
            folder, title, audio_path = self._download_audio()
            segments = self._split_audio(audio_path, folder)
            transcript_paths = self._transcribe(folder, segments)
            self._rebuild_full_transcript(folder, transcript_paths)
            self.last_job_folder = folder
            self.last_job_title = title
            self.last_transcript_paths = transcript_paths
            self.last_pipeline_completed = True
            if self.auto_summary_var.get():
                self._emit("log", "Auto Gemini processing is ON. Starting summary immediately.")
                self._summarize(folder, title, transcript_paths)
                self._emit("status", "Completed")
                self._emit("detail", f"Done in {self._fmt_eta(time.time() - started)}")
                self._emit("total_progress", 1.0)
                self._emit("stage_progress", 1.0)
                self._emit("log", f"Output folder: {folder}")
                self._emit("open_folder", folder)
                return
            elapsed = time.time() - started
            self._emit("status", "Local STT Completed")
            self._emit("detail", f"Done in {self._fmt_eta(elapsed)} | Run Gemini Summary when ready.")
            self._emit("total_progress", 0.82)
            self._emit("stage_progress", 1.0)
            self._emit("log", f"Transcript ready in: {folder}")
            self._emit("open_folder", folder)
        except CancelledError:
            self._emit("status", "Cancelled")
            self._emit("detail", "User cancelled the pipeline.")
            self._emit("log", "Pipeline cancelled.")
        except Exception as exc:
            self._emit("status", "Failed")
            self._emit("detail", str(exc))
            self._emit("log", f"Error: {exc}")
        finally:
            self._emit("controls", {"run": "normal", "summary": "normal" if self.last_pipeline_completed else "disabled", "cancel": "disabled"})

    def _run_summary_only(self):
        started = time.time()
        try:
            self._emit("status", "Gemini Summary Running")
            self._emit("detail", "Creating summary from saved transcripts...")
            self._emit("stage_progress", 0.0)
            self._emit("total_progress", 0.84)
            transcript_paths = self._load_transcript_paths_from_folder(self.last_job_folder)
            if transcript_paths:
                self.last_transcript_paths = transcript_paths
            self._summarize(self.last_job_folder, self.last_job_title, self.last_transcript_paths)
            elapsed = time.time() - started
            self._emit("status", "Completed")
            self._emit("detail", f"Summary done in {self._fmt_eta(elapsed)}")
            self._emit("log", f"Summary output folder: {self.last_job_folder}")
            self._emit("open_folder", self.last_job_folder)
        except CancelledError:
            self._emit("status", "Cancelled")
            self._emit("detail", "User cancelled Gemini summary.")
            self._emit("log", "Gemini summary cancelled.")
        except Exception as exc:
            self._emit("status", "Failed")
            self._emit("detail", str(exc))
            self._emit("log", f"Error: {exc}")
        finally:
            self._emit("controls", {"run": "normal", "summary": "normal" if self.last_pipeline_completed else "disabled", "cancel": "disabled"})

    def _download_audio(self):
        stage_started = time.time()
        self._check_cancelled()
        self._emit("status", "1/4 Downloading low-quality audio")
        self._emit("detail", "Fetching metadata...")
        self._emit("total_progress", 0.03)
        target_url = self._normalize_soop_url(self.url_var.get().strip())

        root = self.save_dir.get().strip() or BASE_DIR
        os.makedirs(root, exist_ok=True)

        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as probe:
            info = probe.extract_info(target_url, download=False)

        title = self._safe_name(info.get("title") or "SOOP_VOD", max_length=72)
        folder = os.path.join(root, title)
        os.makedirs(folder, exist_ok=True)
        self._ensure_job_dirs(folder)
        context_path, _ = write_summary_job_context(folder, title, target_url, info=info)
        self._emit("log", f"Job folder: {folder}")
        self._emit("log", f"Job context saved: {os.path.basename(context_path)}")
        entry_count = len(info.get("entries", [])) if info.get("entries") else 1
        reported_duration = info.get("duration")
        if reported_duration:
            self._emit("log", f"Metadata duration: {self._fmt_seconds(reported_duration)} | entries={entry_count}")
        else:
            self._emit("log", f"Metadata duration: unknown | entries={entry_count}")

        ydl_opts = {
            "paths": {"home": folder},
            "format": "worstaudio/worst",
            "outtmpl": "%(autonumber)s_source.%(ext)s" if entry_count > 1 else "source.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "ffmpeg_location": BASE_DIR,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "40",
                }
            ],
            "postprocessor_args": ["-ac", "1", "-ar", "16000", "-map_metadata", "-1"],
            "concurrent_fragment_downloads": 8,
            "retries": 10,
            "fragment_retries": 10,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([target_url])

        mp3_candidates = sorted(
            [
                os.path.join(folder, name)
                for name in os.listdir(folder)
                if os.path.isfile(os.path.join(folder, name))
                and name.lower().endswith(".mp3")
                and (
                    re.match(r"^\d+_source\.mp3$", name.lower())
                    or name.lower() == "source.mp3"
                )
            ]
        )

        if not mp3_candidates:
            mp3_candidates = sorted(
                [
                    os.path.join(folder, name)
                    for name in os.listdir(folder)
                    if os.path.isfile(os.path.join(folder, name))
                    and name.lower().endswith(".mp3")
                    and not name.lower().startswith("part")
                ]
            )
        if not mp3_candidates:
            raise RuntimeError("No MP3 source file was created.")

        normalized_candidates = []
        for candidate in mp3_candidates:
            target = os.path.join(self._audio_dir(folder), os.path.basename(candidate))
            if os.path.abspath(candidate) != os.path.abspath(target):
                if os.path.exists(target):
                    os.remove(target)
                shutil.move(candidate, target)
            normalized_candidates.append(target)
        mp3_candidates = normalized_candidates

        merged = os.path.join(self._audio_dir(folder), "source_full.mp3")
        if len(mp3_candidates) == 1:
            single = mp3_candidates[0]
            if os.path.abspath(single) != os.path.abspath(merged):
                shutil.copyfile(single, merged)
            source_media = merged
            self._emit("log", f"Single source MP3 ready: {os.path.basename(single)}")
        else:
            self._emit("detail", f"Merging {len(mp3_candidates)} downloaded MP3 parts...")
            self._emit("log", f"Merging source parts: {', '.join(os.path.basename(p) for p in mp3_candidates)}")
            self._merge_audio(mp3_candidates, merged, folder)
            source_media = merged

        actual_duration = self._probe_duration(source_media)
        if actual_duration > 0:
            self._emit("log", f"Merged source duration: {self._fmt_seconds(actual_duration)}")

        self._emit("total_progress", 0.18)
        self._emit("stage_progress", 1.0)
        self._emit(
            "log",
            f"Download complete: {os.path.basename(source_media)} ({self._fmt_eta(time.time() - stage_started)})",
        )
        return folder, title, source_media

    def _split_audio(self, audio_path, folder):
        stage_started = time.time()
        self._check_cancelled()
        minutes = max(5, int(self.chunk_minutes_var.get().strip() or "15"))
        segment_seconds = minutes * 60
        self._emit("status", "2/4 Splitting and converting audio")
        self._emit("detail", f"Chunk size: {minutes} minute(s)")
        self._emit("stage_progress", 0.1)
        self._emit("log", f"Split source: {os.path.basename(audio_path)}")

        for old_path in self._list_part_files(folder):
            try:
                os.remove(old_path)
            except OSError:
                pass

        total_duration = self._probe_duration(audio_path)
        if total_duration <= 0:
            raise RuntimeError("Could not read source duration for splitting.")

        chunks = []
        start = 0.0
        index = 0
        while start < total_duration:
            duration = min(segment_seconds, total_duration - start)
            chunks.append((index, start, duration))
            start += segment_seconds
            index += 1

        self._emit("log", f"Planned chunks: {len(chunks)} from total {self._fmt_seconds(total_duration)}")

        paths = []
        for idx, start_time, duration in chunks:
            self._check_cancelled()
            out_path = os.path.join(self._audio_dir(folder), f"part{idx:03d}.wav")
            self._emit(
                "detail",
                f"Extracting chunk {idx + 1}/{len(chunks)}: start={self._fmt_seconds(start_time)} len={self._fmt_seconds(duration)}",
            )
            self._emit(
                "log",
                f"Chunk extract start: part{idx:03d}.wav | start={self._fmt_seconds(start_time)} | duration={self._fmt_seconds(duration)}",
            )

            command = [
                FFMPEG_PATH,
                "-y",
                "-ss",
                self._ffmpeg_time(start_time),
                "-t",
                self._ffmpeg_time(duration),
                "-i",
                audio_path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-map_metadata",
                "-1",
                out_path,
            ]
            self._run_extract_subprocess(command, out_path, idx + 1, len(chunks))
            if not os.path.exists(out_path):
                raise RuntimeError(f"Chunk extraction failed: {out_path}")
            paths.append(out_path)
            self._emit(
                "log",
                f"Chunk ready: {os.path.basename(out_path)} {self._fmt_size(os.path.getsize(out_path))}",
            )
            self._emit("stage_progress", (idx + 1) / max(1, len(chunks)))

        if not paths:
            raise RuntimeError("Audio split failed. No chunk file was produced.")

        segments = []
        for idx, path in enumerate(paths):
            segments.append(
                SegmentFile(
                    index=idx,
                    path=path,
                    duration=self._probe_duration(path),
                    start_offset=chunks[idx][1],
                )
            )

        self._emit("stage_progress", 1.0)
        self._emit("total_progress", 0.25)
        self._emit(
            "log",
            f"Split complete: {len(segments)} chunk(s) ({self._fmt_eta(time.time() - stage_started)})",
        )
        return segments

    def _transcribe(self, folder, segments):
        stage_started = time.time()
        self._check_cancelled()
        self._emit("status", "3/4 Local STT")
        self._emit("detail", "Loading fast Whisper model...")
        self._emit("stage_progress", 0.02)
        self._emit(
            "log",
            f"STT model load requested: model={self.model_var.get().strip()} compute={self.compute_var.get().strip()} batch={self.batch_var.get().strip()} profile={self.stt_profile_var.get().strip()}",
        )

        model_name = self.model_var.get().strip()
        compute = self.compute_var.get().strip()
        language = self.language_var.get().strip()
        batch_size = max(1, int(self.batch_var.get().strip() or "8"))
        stt_profile = self.stt_profile_var.get().strip()
        cpu_count = os.cpu_count() or 8
        cpu_threads = max(4, min(cpu_count, cpu_count - 2 if cpu_count > 6 else cpu_count))
        num_workers = max(1, min(4, cpu_count // 4))

        self._emit(
            "log",
            f"CPU tuning: logical_cores={cpu_count} cpu_threads={cpu_threads} workers={num_workers}",
        )

        base_model = WhisperModel(
            model_name,
            device="cpu",
            compute_type=compute,
            cpu_threads=cpu_threads,
            num_workers=num_workers,
        )
        pipeline = BatchedInferencePipeline(model=base_model) if (BatchedInferencePipeline and stt_profile != "accurate") else None

        transcript_paths = []
        stage_weight = 0.55
        total_audio = sum(max(1.0, item.duration) for item in segments)
        done_audio = 0.0
        average_rtf = None

        for order, item in enumerate(segments, start=1):
            self._check_cancelled()
            chunk_name = os.path.basename(item.path)
            self._emit("log", f"STT start: {chunk_name} ({self._fmt_seconds(item.duration)})")
            self._emit("detail", f"Chunk {order}/{len(segments)}: 00:00 / {self._fmt_seconds(item.duration)}")

            kwargs = {
                "beam_size": 3 if stt_profile == "balanced" else 5,
                "best_of": 3 if stt_profile == "balanced" else 5,
                "vad_filter": True,
                "condition_on_previous_text": True,
                "temperature": 0.0,
                "word_timestamps": False,
                "compression_ratio_threshold": 2.2,
                "log_prob_threshold": -1.0,
                "no_speech_threshold": 0.6,
                "vad_parameters": {
                    "min_silence_duration_ms": 500 if stt_profile == "balanced" else 350,
                    "speech_pad_ms": 250 if stt_profile == "balanced" else 350,
                },
            }
            if language != "auto":
                kwargs["language"] = language
            if pipeline:
                kwargs["batch_size"] = batch_size

            started = time.time()
            iterator_source = pipeline if pipeline else base_model
            segments_iter, info = iterator_source.transcribe(item.path, **kwargs)

            json_rows = []
            text_lines = []
            last_report = 0.0

            for piece in segments_iter:
                self._check_cancelled()
                clean_text = piece.text.strip()
                global_start = item.start_offset + piece.start
                global_end = item.start_offset + piece.end
                json_rows.append(
                    {
                        "start": round(piece.start, 2),
                        "end": round(piece.end, 2),
                        "global_start": round(global_start, 2),
                        "global_end": round(global_end, 2),
                        "text": clean_text,
                    }
                )
                if clean_text:
                    text_lines.append(f"[{self._fmt_seconds(global_start)}] {clean_text}")

                if piece.end - last_report >= 20 or piece.end >= item.duration - 3:
                    elapsed = max(0.1, time.time() - started)
                    processed = min(item.duration, max(0.0, piece.end))
                    ratio = processed / max(1.0, item.duration)
                    rtf = elapsed / max(1.0, processed)
                    average_rtf = rtf if average_rtf is None else (average_rtf * 0.7 + rtf * 0.3)
                    remain_seconds = max(0.0, (item.duration - processed) * average_rtf)
                    self._emit(
                        "detail",
                        f"Chunk {order}/{len(segments)}: {self._fmt_seconds(processed)} / {self._fmt_seconds(item.duration)} | ETA {self._fmt_eta(remain_seconds)}",
                    )
                    total_ratio = (done_audio + processed) / max(1.0, total_audio)
                    self._emit("total_progress", 0.25 + stage_weight * total_ratio)
                    self._emit("stage_progress", total_ratio)
                    last_report = piece.end

            elapsed = time.time() - started
            done_audio += item.duration
            self._emit(
                "log",
                f"STT done: {chunk_name} in {self._fmt_eta(elapsed)} | language={getattr(info, 'language', 'unknown')}",
            )

            text_path = os.path.join(self._transcripts_dir(folder), f"part_{item.index:03d}_transcript.txt")
            json_path = os.path.join(self._segments_dir(folder), f"part_{item.index:03d}_segments.json")
            with open(text_path, "w", encoding="utf-8") as file:
                file.write("\n".join(text_lines))
            with open(json_path, "w", encoding="utf-8") as file:
                json.dump(json_rows, file, ensure_ascii=False, indent=2)

            transcript_paths.append({"segment": item, "text_path": text_path})

        self._emit("stage_progress", 1.0)
        self._emit("total_progress", 0.80)
        self._emit("log", f"STT stage complete ({self._fmt_eta(time.time() - stage_started)})")
        return transcript_paths

    def _summarize(self, folder, title, transcript_paths):
        stage_started = time.time()
        self._check_cancelled()
        self._emit("status", "4/4 Gemini summary")
        self._emit("detail", "Creating timeline from transcript parts...")
        self._emit("stage_progress", 0.02)
        self._emit("log", "Summary mode: per-part timeline merge")
        reference_notes = self.reference_notes.get("1.0", "end").strip()

        legacy_genai.configure(api_key=self.api_key.get().strip())
        model = legacy_genai.GenerativeModel(GEMINI_MODEL)

        transcript_paths = transcript_paths or self._load_transcript_paths_from_folder(folder)
        if not transcript_paths:
            raise RuntimeError("No transcript files were found for Gemini summary.")

        for idx, item in enumerate(transcript_paths, start=1):
            self._check_cancelled()
            ratio = idx / max(1, len(transcript_paths))
            self._emit("stage_progress", 0.1 + (0.2 * ratio))
            self._emit("total_progress", 0.84 + 0.10 * ratio)

        full_transcript_path = self._rebuild_full_transcript(folder, transcript_paths)
        with open(full_transcript_path, "r", encoding="utf-8") as file:
            full_transcript = file.read().strip()

        cleaned_text = self._clean_transcript_locally(full_transcript)
        with open(os.path.join(self._summaries_dir(folder), "cleaned_full_script.txt"), "w", encoding="utf-8") as file:
            file.write(cleaned_text)

        self._emit("log", "Local cleaned_full_script generated.")
        parts_dir = os.path.join(self._summaries_dir(folder), "parts")
        os.makedirs(parts_dir, exist_ok=True)

        part_timeline_blocks = []
        ordered_paths = sorted(transcript_paths, key=lambda x: x["segment"].index)
        grouped_batches = self._build_group_timeline_batches(ordered_paths, max_parts=3, max_chars=18000)
        total_groups = len(grouped_batches)

        for idx, batch in enumerate(grouped_batches, start=1):
            self._check_cancelled()
            start_idx = batch["start_index"]
            end_idx = batch["end_index"]
            label = batch["label"]
            self._emit("detail", f"Gemini grouped timeline {idx}/{total_groups} ({label})")
            part_prompt = self._part_timeline_prompt(
                title=title,
                part_index_label=label,
                transcript_text=batch["transcript_text"],
                reference_notes=reference_notes,
            )
            part_text = self._generate_gemini_text(model, part_prompt, f"grouped timeline {label}")
            part_path = os.path.join(parts_dir, f"group_{idx:02d}_{start_idx:03d}_{end_idx:03d}_timeline.txt")
            with open(part_path, "w", encoding="utf-8") as file:
                file.write(part_text)
            part_timeline_blocks.append(f"[Group {label}]\n{part_text}")

            ratio = idx / max(1, total_groups)
            self._emit("stage_progress", 0.20 + (0.55 * ratio))
            self._emit("total_progress", 0.86 + (0.08 * ratio))
            self._emit("log", f"Grouped timeline complete: {os.path.basename(part_path)}")

        merged_source = "\n\n".join(part_timeline_blocks)
        self._emit("stage_progress", 0.82)
        self._emit("total_progress", 0.96)

        final_prompt = self._timeline_merge_prompt(title, merged_source, reference_notes)
        final_text = self._generate_gemini_text(model, final_prompt, "final timeline merge")
        with open(os.path.join(self._summaries_dir(folder), "timeline.txt"), "w", encoding="utf-8") as file:
            file.write(final_text)
        with open(os.path.join(self._summaries_dir(folder), "final_summary.txt"), "w", encoding="utf-8") as file:
            file.write(final_text)
        _, context = write_summary_job_context(folder, title, self.url_var.get().strip())
        payload_path, _ = build_summary_payload_artifact(
            folder,
            title=title,
            source_url=context.get("canonical_source_url") or context.get("source_url") or "",
            reference_notes=reference_notes,
            summary_mode=self.summary_mode_var.get().strip() or "full_transcript",
        )

        self._emit("stage_progress", 1.0)
        self._emit("total_progress", 1.0)
        self._emit("log", f"Gemini summary complete ({self._fmt_eta(time.time() - stage_started)})")
        self._emit("log", f"Summary payload artifact saved: {payload_path}")

    def _timeline_prompt(self, title, source_text, reference_notes):
        clipped_notes = self._truncate_text(reference_notes, 2500).strip()
        notes_block = clipped_notes if clipped_notes else "없음"
        return f"""
당신은 SOOP 다시보기 타임라인 정리 에디터다.

반드시 한국어로만 답하라.
영어로 답하지 마라.
고유명사, 사람 이름, 게임 이름은 transcript와 참고 메모를 최우선으로 따른다.
추측으로 이름을 바꾸지 마라.

방송 제목: {title}
참고 메모:
{notes_block}

출력 형식:
아래 형식을 최대한 그대로 지켜라.

{title} 타임라인
[ 00:00:00 ] 시작 구간 또는 오프닝

주제 섹션 제목
[ 00:00:00 ] 내용
[ 00:00:00 ] 내용

다른 주제 섹션 제목
[ 00:00:00 ] 내용
[ 00:00:00 ] 내용

규칙:
- 결과물은 "타임라인 문서"처럼 작성하라. 일반 요약문처럼 길게 서술하지 마라.
- 큰 흐름에 따라 섹션 제목을 먼저 쓰고, 그 아래에 시간표가 달린 핵심 사건들을 정리하라.
- 타임라인 줄은 반드시 `[ 00:00:00 ]` 형식을 사용하라.
- transcript에 있는 시간표시를 활용해서 실제 흐름 순서대로 정리하라.
- 같은 주제의 대화는 묶고, 너무 사소한 잡담은 생략하라.
- 방송에서 실제로 의미 있는 반응, 사건, 선언, 게임/콘텐츠 전환, 밈, 인물 언급을 우선 적어라.
- 고유명사와 사람 이름이 애매하면 참고 메모와 문맥을 보고 보수적으로 적어라.
- 불확실한 내용은 억지로 만들지 마라.
- 섹션 제목은 너무 많지 않게 4~8개 정도로 구성하라.
- transcript가 raw하더라도 문맥을 정리해 사람이 읽기 좋은 타임라인 문서로 재작성하라.

raw full transcript:
{source_text}
"""

    def _part_timeline_prompt(self, title, part_index_label, transcript_text, reference_notes):
        clipped_notes = self._truncate_text(reference_notes, 2000).strip()
        notes_block = clipped_notes if clipped_notes else "없음"
        return f"""
당신은 SOOP 다시보기 타임라인 정리 에디터다.

반드시 한국어로만 답하라.
이 작업은 전체 방송의 한 파트만 다룬다.
주어진 transcript 안에 있는 시간표와 내용만 사용하라.
추정 금지. 불확실하면 생략하라.

방송 제목: {title}
파트 범위: {part_index_label}
참고 메모:
{notes_block}

출력 규칙:
- 섹션 제목 2~5개 정도로만 묶어라.
- 각 사건 줄은 반드시 `[ 00:00:00 ]` 형식을 써라.
- transcript에 있는 시간표를 그대로 활용하라.
- 너무 사소한 군더더기 대화는 줄이고, 사건/전환/반응 중심으로 정리하라.
- 문장은 짧고 명확하게 적어라.

transcript:
{transcript_text}
"""

    def _timeline_merge_prompt(self, title, merged_part_timelines, reference_notes):
        clipped_notes = self._truncate_text(reference_notes, 2500).strip()
        notes_block = clipped_notes if clipped_notes else "없음"
        return f"""
당신은 SOOP 다시보기 전체 타임라인 편집자다.

반드시 한국어로만 답하라.
아래에는 각 파트에서 이미 추출된 타임라인 초안이 있다.
이 초안들을 시간 순서대로 병합해서 최종 타임라인 문서를 만들어라.

규칙:
- 새로운 사실을 만들지 마라.
- 중복되는 내용은 합쳐라.
- 섹션 제목은 4~8개 정도로 정리하라.
- 각 사건 줄은 반드시 `[ 00:00:00 ]` 형식을 유지하라.
- 전체 문서는 사람이 읽기 좋은 타임라인 문서처럼 써라.
- 추정하지 말고, 애매하면 약하게 표현하거나 생략하라.

방송 제목: {title}
참고 메모:
{notes_block}

파트별 타임라인 초안:
{merged_part_timelines}
"""

    def _load_transcript_paths_from_folder(self, folder):
        transcript_dir = self._transcripts_dir(folder)
        job_root = folder
        if not os.path.isdir(transcript_dir):
            if os.path.basename(os.path.normpath(folder)).lower() == "transcripts":
                transcript_dir = folder
                job_root = os.path.dirname(folder)
            else:
                return []

        entries = []
        for name in sorted(os.listdir(transcript_dir)):
            if re.match(r"^part_(\d+)_transcript\.txt$", name):
                match = re.match(r"^part_(\d+)_transcript\.txt$", name)
                index = int(match.group(1))
                path = os.path.join(transcript_dir, name)
                entries.append(
                    {
                        "segment": SegmentFile(index=index, path="", duration=0.0, start_offset=0.0),
                        "text_path": path,
                    }
                )
        if entries:
            self.last_job_folder = job_root
        return entries

    def _rebuild_full_transcript(self, folder, transcript_paths):
        transcript_paths = transcript_paths or self._load_transcript_paths_from_folder(folder)
        if not transcript_paths:
            raise RuntimeError("No transcript files were found to build full_transcript.txt.")

        ordered = sorted(transcript_paths, key=lambda item: item["segment"].index)
        combined_blocks = []
        for item in ordered:
            text_path = item["text_path"]
            if not os.path.exists(text_path):
                continue
            with open(text_path, "r", encoding="utf-8") as file:
                transcript = file.read().strip()
            if transcript:
                combined_blocks.append(transcript)

        full_transcript_path = os.path.join(self._transcripts_dir(folder), "full_transcript.txt")
        with open(full_transcript_path, "w", encoding="utf-8") as file:
            file.write("\n\n".join(combined_blocks))
        self._emit("log", f"full_transcript rebuilt: {full_transcript_path}")
        return full_transcript_path

    def _clean_transcript_locally(self, text):
        lines = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            line = re.sub(r"\s+", " ", line)
            line = re.sub(r"([^\w\s\[\]:])\1{3,}", r"\1\1", line)
            line = re.sub(r"([가-힣A-Za-z0-9])\1{5,}", r"\1\1\1", line)
            line = re.sub(r"(\b\S+\b)( \1){3,}", r"\1 \1", line)
            line = re.sub(r"\?{3,}", "??", line)

            lines.append(line)

        return "\n".join(lines)

    def _extract_model_text(self, response):
        text = getattr(response, "text", None)
        if text:
            stripped = text.strip()
            if stripped:
                return stripped

        candidates = getattr(response, "candidates", None) or []
        finish_reason = None
        if candidates:
            finish_reason = getattr(candidates[0], "finish_reason", None)

        if finish_reason is not None:
            finish_reason_labels = {
                2: "MAX_TOKENS",
                3: "SAFETY",
                4: "RECITATION",
                5: "OTHER",
            }
            label = finish_reason_labels.get(int(finish_reason), str(finish_reason))
            raise RuntimeError(
                f"Gemini returned no text. finish_reason={label}. The prompt may have been blocked or filtered."
            )
        raise RuntimeError("Gemini returned no text.")

    def _timeline_prompt(self, title, source_text, reference_notes):
        clipped_notes = self._truncate_text(reference_notes, 2500).strip()
        notes_block = clipped_notes if clipped_notes else "없음"
        return f"""
당신은 SOOP 다시보기 타임라인 문서를 정리하는 편집자다.

반드시 한국어로만 작성하라.
영어로 답하지 마라.
고유명사, 멤버 이름, 게임명은 transcript와 참고 메모를 우선으로 따르되, 불확실하면 억지로 보정하지 마라.
추정해서 없는 사실을 만들지 마라.

방송 제목: {title}
참고 메모:
{notes_block}

출력 형식:
{title} 타임라인

섹션 제목
[ 00:00:00 ] 내용
[ 00:00:00 ] 내용

다른 섹션 제목
[ 00:00:00 ] 내용

규칙:
- 결과물은 읽기 좋은 타임라인 문서여야 한다.
- `[ 00:00:00 ]` 형식의 시간 표기를 유지하라.
- transcript에 있는 시간과 내용만 바탕으로 정리하라.
- 같은 내용을 반복하지 말고, 비슷한 이벤트는 한 줄로 묶어라.
- 사소한 군더더기보다 사건, 주제 전환, 중요한 반응, 게임/콘텐츠 변화, 인물 간 상호작용을 우선하라.
- 섹션 수는 대략 4개에서 8개 사이로 정리하라.
- 불확실한 고유명사는 그대로 두거나 보수적으로 적어라.

raw full transcript:
{source_text}
"""

    def _part_timeline_prompt(self, title, part_index_label, transcript_text, reference_notes):
        clipped_notes = self._truncate_text(reference_notes, 2000).strip()
        notes_block = clipped_notes if clipped_notes else "없음"
        return f"""
당신은 SOOP 다시보기의 일부 transcript만 보고 해당 구간의 타임라인 초안을 만드는 편집자다.

반드시 한국어로만 작성하라.
추정 금지. transcript에 없는 사실은 쓰지 마라.
시간은 transcript에 적힌 시간 그대로 사용하라.

방송 제목: {title}
구간 범위: {part_index_label}
참고 메모:
{notes_block}

출력 규칙:
- 섹션 제목은 2개에서 5개 정도로만 구성하라.
- 각 줄은 반드시 `[ 00:00:00 ]` 형식을 사용하라.
- transcript에 명확히 보이는 사건, 주제 전환, 반응, 대화 흐름 위주로 적어라.
- 사소한 반복 잡담은 줄이고 중요한 흐름만 남겨라.
- 문장은 짧고 명확하게 적어라.

transcript:
{transcript_text}
"""

    def _timeline_merge_prompt(self, title, merged_part_timelines, reference_notes):
        clipped_notes = self._truncate_text(reference_notes, 2500).strip()
        notes_block = clipped_notes if clipped_notes else "없음"
        return f"""
당신은 여러 구간 타임라인 초안을 하나의 최종 타임라인 문서로 병합하는 편집자다.

반드시 한국어로만 작성하라.
새로운 사실을 추가하지 마라.
서로 겹치는 내용은 합치고, 시간 순서는 유지하라.
애매한 표현은 과장하지 말고 보수적으로 정리하라.

방송 제목: {title}
참고 메모:
{notes_block}

최종 출력 규칙:
- 결과는 읽기 좋은 최종 타임라인 문서여야 한다.
- 섹션 제목은 대략 4개에서 8개 정도로 정리하라.
- 각 이벤트 줄은 반드시 `[ 00:00:00 ]` 형식을 유지하라.
- 중복된 항목은 합치고, 비슷한 사건은 한 줄로 묶어라.
- 추정이나 각색 없이 입력된 초안 범위 안에서만 정리하라.

구간별 타임라인 초안:
{merged_part_timelines}
"""

    def _build_group_timeline_batches(self, ordered_paths, max_parts=3, max_chars=18000):
        part_sections = []
        for item in ordered_paths:
            with open(item["text_path"], "r", encoding="utf-8") as file:
                part_transcript = file.read().strip()
            chunks = self._split_part_transcript_for_prompt(
                part_index=item["segment"].index,
                transcript_text=part_transcript,
                max_chars=max_chars,
            )
            part_sections.extend(chunks)

        batches = []
        current_sections = []
        current_part_indexes = []
        current_chars = 0

        for section in part_sections:
            part_index = section["part_index"]
            section_text = section["text"]
            section_chars = len(section_text) + (2 if current_sections else 0)
            prospective_parts = set(current_part_indexes)
            prospective_parts.add(part_index)

            if current_sections and (len(prospective_parts) > max_parts or current_chars + section_chars > max_chars):
                batches.append(
                    {
                        "start_index": current_part_indexes[0],
                        "end_index": current_part_indexes[-1],
                        "label": self._format_part_label(current_part_indexes),
                        "transcript_text": "\n\n".join(current_sections),
                    }
                )
                current_sections = []
                current_part_indexes = []
                current_chars = 0

            current_sections.append(section_text)
            if part_index not in current_part_indexes:
                current_part_indexes.append(part_index)
            current_chars += len(section_text) + (2 if len(current_sections) > 1 else 0)

        if current_sections:
            batches.append(
                {
                    "start_index": current_part_indexes[0],
                    "end_index": current_part_indexes[-1],
                    "label": self._format_part_label(current_part_indexes),
                    "transcript_text": "\n\n".join(current_sections),
                }
            )

        return batches

    def _split_part_transcript_for_prompt(self, part_index, transcript_text, max_chars):
        header = f"[Part {part_index:03d}]"
        if not transcript_text:
            return [{"part_index": part_index, "text": f"{header}\n(빈 transcript)"}]

        lines = [line.strip() for line in transcript_text.splitlines() if line.strip()]
        if not lines:
            return [{"part_index": part_index, "text": f"{header}\n(빈 transcript)"}]

        chunks = []
        current_lines = []
        current_chars = len(header) + 1
        chunk_no = 1

        for line in lines:
            addition = len(line) + 1
            if current_lines and current_chars + addition > max_chars:
                chunks.append(
                    {
                        "part_index": part_index,
                        "text": self._part_chunk_header(part_index, chunk_no, len(chunks) > 0) + "\n" + "\n".join(current_lines),
                    }
                )
                chunk_no += 1
                current_lines = []
                current_chars = len(header) + 1

            current_lines.append(line)
            current_chars += addition

        if current_lines:
            chunks.append(
                {
                    "part_index": part_index,
                    "text": self._part_chunk_header(part_index, chunk_no, len(chunks) > 0) + "\n" + "\n".join(current_lines),
                }
            )

        return chunks

    def _part_chunk_header(self, part_index, chunk_no, is_continued):
        if is_continued or chunk_no > 1:
            return f"[Part {part_index:03d} | chunk {chunk_no}]"
        return f"[Part {part_index:03d}]"

    def _format_part_label(self, part_indexes):
        unique_indexes = sorted(set(part_indexes))
        if not unique_indexes:
            return "part unknown"
        if len(unique_indexes) == 1:
            return f"part {unique_indexes[0]:03d}"
        return f"parts {unique_indexes[0]:03d}-{unique_indexes[-1]:03d}"

    def _generate_gemini_text(self, model, prompt, label):
        try:
            response = model.generate_content(prompt)
            return self._extract_model_text(response)
        except Exception as exc:
            raise RuntimeError(self._format_gemini_error(exc, label)) from exc

    def _format_gemini_error(self, exc, label):
        message = str(exc).strip() or exc.__class__.__name__
        lower = message.lower()

        if "429" in message or "quota exceeded" in lower:
            retry_delay = self._extract_retry_delay_seconds(message)
            if retry_delay:
                return f"Gemini quota exceeded during {label}. Retry after about {retry_delay} seconds."
            return f"Gemini quota exceeded during {label}. Please wait and try again later."

        if "finish_reason=recitation" in lower or "finish_reason is 4" in lower or "copyright" in lower:
            return f"Gemini blocked the response during {label} because it looked too close to source text. Try timeline-only processing or a stricter prompt."

        return f"Gemini failed during {label}: {message}"

    def _extract_retry_delay_seconds(self, message):
        match = re.search(r"retry_delay\s*\{[^}]*seconds:\s*(\d+)", message, re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _merge_audio(self, files, output, folder):
        list_path = os.path.join(folder, "merge_list.txt")
        with open(list_path, "w", encoding="utf-8") as file:
            for path in files:
                normalized = path.replace("\\", "/").replace("'", "'\\''")
                file.write(f"file '{normalized}'\n")

        self._run_subprocess(
            [FFMPEG_PATH, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output]
        )

        try:
            os.remove(list_path)
            for path in files:
                if os.path.exists(path):
                    os.remove(path)
        except OSError:
            pass

    def _probe_duration(self, path):
        command = [
            FFPROBE_PATH,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        output = self._run_subprocess(command, capture_output=True)
        try:
            return float(output.strip())
        except Exception:
            return 0.0

    def _run_subprocess(self, command, capture_output=False):
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

        if capture_output:
            return stdout_text
        return ""

    def _run_extract_subprocess(self, command, out_path, chunk_index, chunk_total):
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

        started = time.time()
        last_heartbeat = 0.0

        while True:
            if self.cancel_event.is_set():
                process.kill()
                raise CancelledError()

            code = process.poll()
            now = time.time()
            if now - last_heartbeat >= 2.0:
                elapsed = now - started
                size = 0
                if os.path.exists(out_path):
                    try:
                        size = os.path.getsize(out_path)
                    except OSError:
                        size = 0
                self._emit(
                    "detail",
                    f"Extracting chunk {chunk_index}/{chunk_total}... elapsed {self._fmt_eta(elapsed)} | {os.path.basename(out_path)} {self._fmt_size(size)}",
                )
                self._emit(
                    "log",
                    f"Chunk progress: {os.path.basename(out_path)}={self._fmt_size(size)} elapsed={self._fmt_eta(elapsed)}",
                )

                last_heartbeat = now

            if code is not None:
                break
            time.sleep(0.2)

        stdout, stderr = process.communicate()
        stdout_text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else (stdout or "")
        stderr_text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else (stderr or "")
        if code != 0:
            detail = stderr_text.strip() or stdout_text.strip() or "subprocess failed"
            raise RuntimeError(detail)

    def _truncate_text(self, text, max_chars):
        return text if len(text) <= max_chars else text[:max_chars]

    def _list_part_files(self, folder):
        paths = []
        try:
            audio_dir = self._audio_dir(folder)
            if not os.path.isdir(audio_dir):
                return []
            for name in os.listdir(audio_dir):
                if name.lower().startswith("part") and os.path.isfile(os.path.join(audio_dir, name)):
                    paths.append(os.path.join(audio_dir, name))
        except OSError:
            return []
        return sorted(paths)

    def _ensure_job_dirs(self, folder):
        for path in (
            self._audio_dir(folder),
            self._transcripts_dir(folder),
            self._segments_dir(folder),
            self._summaries_dir(folder),
        ):
            os.makedirs(path, exist_ok=True)

    def _audio_dir(self, folder):
        return os.path.join(folder, "audio")

    def _transcripts_dir(self, folder):
        return os.path.join(folder, "transcripts")

    def _segments_dir(self, folder):
        return os.path.join(folder, "segments")

    def _summaries_dir(self, folder):
        return os.path.join(folder, "summaries")

    def _safe_name(self, value, max_length=80):
        cleaned = re.sub(r'[\\/*?:"<>|]+', "", value).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length].rstrip()
        return cleaned or "SOOP_VOD"

    def _normalize_soop_url(self, url):
        return normalize_soop_url(url)

    def _fmt_seconds(self, value):
        total = max(0, int(value))
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _fmt_eta(self, seconds):
        seconds = max(0, int(seconds))
        minutes = seconds // 60
        remain = seconds % 60
        if minutes >= 60:
            hours = minutes // 60
            minutes = minutes % 60
            return f"{hours}h {minutes}m {remain}s"
        return f"{minutes}m {remain}s"

    def _ffmpeg_time(self, seconds):
        whole = max(0, int(seconds))
        hours = whole // 3600
        minutes = (whole % 3600) // 60
        remain = whole % 60
        return f"{hours:02d}:{minutes:02d}:{remain:02d}"

    def _fmt_size(self, size):
        if size >= 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024 * 1024):.2f}GB"
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        if size >= 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size}B"

    def _check_cancelled(self):
        if self.cancel_event.is_set():
            raise CancelledError()

    def _emit(self, kind, value):
        self.ui_queue.put((kind, value))

    def _ui_log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{timestamp}] {text}\n")
        self.log_box.see("end")

    def _drain_queue(self):
        while True:
            try:
                kind, value = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._ui_log(value)
            elif kind == "status":
                self.status_var.set(value)
            elif kind == "detail":
                self.detail_var.set(value)
            elif kind == "total_progress":
                self.total_progress.set(value)
            elif kind == "stage_progress":
                self.stage_progress.set(value)
            elif kind == "open_folder":
                try:
                    os.startfile(value)
                except OSError:
                    pass
            elif kind == "controls":
                self.run_button.configure(state=value["run"])
                self.summary_button.configure(state=value["summary"])
                self.cancel_button.configure(state=value["cancel"])

        self.after(120, self._drain_queue)


if __name__ == "__main__":
    app = SoopLocalSummarizerV3()
    app.mainloop()
