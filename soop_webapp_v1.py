import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
import warnings
import webbrowser
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import yt_dlp
from soop_remote_service import SoopRemoteService

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


BASE_DIR = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else BASE_DIR
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) if getattr(sys, "frozen", False) else BASE_DIR
FFMPEG_PATH = RESOURCE_DIR / "ffmpeg.exe"
FFPROBE_PATH = RESOURCE_DIR / "ffprobe.exe"
GEMINI_MODEL = "gemini-2.5-flash"
INDEX_HTML = RESOURCE_DIR / "webapp" / "index.html"
MODEL_DIR = APP_DIR / "models"
CONFIG_PATH = APP_DIR / "config.json"
SERVER_HOST = os.getenv("SOOP_SERVER_HOST", "127.0.0.1").strip() or "127.0.0.1"
SERVER_PORT = int(os.getenv("SOOP_SERVER_PORT", "8765"))
SERVER_TOKEN = os.getenv("SOOP_SERVER_TOKEN", "").strip()
OPEN_BROWSER_ON_START = os.getenv("SOOP_OPEN_BROWSER", "1").strip().lower() not in {"0", "false", "no"}


def select_folder_dialog(initial_dir: str | None = None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError(f"Folder dialog is unavailable: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(initialdir=initial_dir or str(APP_DIR), title="Select a folder")
    finally:
        root.destroy()
    return selected or None


class StartJobRequest(BaseModel):
    api_key: str
    save_dir: str
    url: str
    language: str = "ko"
    chunk_minutes: int = 15
    whisper_model: str = "medium"
    compute: str = "int8"
    batch_size: int = 8
    stt_profile: str = "balanced"
    reference_notes: str = ""
    auto_summary: bool = False


class SummaryJobRequest(BaseModel):
    api_key: str
    folder: str
    reference_notes: str = ""


class RemoteStreamerCreate(BaseModel):
    value: str


class RemoteSummaryStartRequest(BaseModel):
    api_key: str | None = None
    save_dir: str | None = None
    url: str | None = None
    language: str | None = None
    chunk_minutes: int | None = None
    whisper_model: str | None = None
    compute: str | None = None
    batch_size: int | None = None
    stt_profile: str | None = None
    reference_notes: str | None = None
    auto_summary: bool | None = None


@dataclass
class SegmentFile:
    index: int
    path: str
    duration: float
    start_offset: float


@dataclass
class JobState:
    id: str
    mode: str
    status: str = "queued"
    detail: str = "waiting"
    progress: float = 0.0
    stage_progress: float = 0.0
    folder: str | None = None
    title: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    cancel_requested: bool = False


class CancelledError(Exception):
    pass


class JobStore:
    def __init__(self):
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def create(self, mode: str) -> JobState:
        job = JobState(id=uuid.uuid4().hex[:12], mode=mode)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def clear_finished(self) -> int:
        with self._lock:
            keys = [key for key, job in self._jobs.items() if job.status in {"completed", "failed", "cancelled"}]
            for key in keys:
                self._jobs.pop(key, None)
            return len(keys)

    def all(self) -> list[JobState]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def patch(self, job_id: str, **kwargs: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in kwargs.items():
                setattr(job, key, value)
            job.updated_at = time.time()

    def request_cancel(self, job_id: str) -> JobState:
        with self._lock:
            job = self._jobs[job_id]
            job.cancel_requested = True
            job.updated_at = time.time()
            return job

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(job and job.cancel_requested)

    def log(self, job_id: str, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        with self._lock:
            job = self._jobs[job_id]
            job.logs.append(f"[{timestamp}] {message}")
            job.updated_at = time.time()


class PipelineService:
    def __init__(self, store: JobStore):
        self.store = store

    def start_stt(self, payload: StartJobRequest) -> JobState:
        if WhisperModel is None:
            raise HTTPException(status_code=500, detail="faster-whisper is not installed.")
        if not FFMPEG_PATH.exists() or not FFPROBE_PATH.exists():
            raise HTTPException(status_code=500, detail="ffmpeg/ffprobe is missing.")

        job = self.store.create(mode="stt")
        thread = threading.Thread(target=self._run_stt_job, args=(job.id, payload), daemon=True)
        thread.start()
        return job

    def start_uploaded_audio(
        self,
        upload: UploadFile,
        save_dir: str,
        language: str,
        chunk_minutes: int,
        whisper_model: str,
        compute: str,
        batch_size: int,
        stt_profile: str,
    ) -> JobState:
        if WhisperModel is None:
            raise HTTPException(status_code=500, detail="faster-whisper is not installed.")
        if not FFMPEG_PATH.exists() or not FFPROBE_PATH.exists():
            raise HTTPException(status_code=500, detail="ffmpeg/ffprobe is missing.")

        folder, title, source_audio = self._save_uploaded_audio(upload, save_dir)
        job = self.store.create(mode="meeting_stt")
        self.store.patch(job.id, folder=str(folder), title=title, detail="uploaded audio saved", progress=0.03)
        self.store.log(job.id, f"Uploaded file saved: {source_audio.name}")
        thread = threading.Thread(
            target=self._run_uploaded_audio_job,
            args=(job.id, folder, title, source_audio, language, chunk_minutes, whisper_model, compute, batch_size, stt_profile),
            daemon=True,
        )
        thread.start()
        return job

    def cancel_job(self, job_id: str) -> JobState:
        job = self.store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status not in {"queued", "running"}:
            raise HTTPException(status_code=400, detail="Only queued or running jobs can be cancelled.")
        self.store.request_cancel(job_id)
        self.store.log(job_id, "Cancellation requested.")
        self.store.patch(job_id, detail="Cancellation requested")
        return self.store.get(job_id)

    def start_summary(self, payload: SummaryJobRequest) -> JobState:
        if legacy_genai is None:
            raise HTTPException(status_code=500, detail="google-generativeai is not installed.")
        folder = self._normalize_job_folder(Path(payload.folder))
        if not folder.exists():
            raise HTTPException(status_code=400, detail="Selected job folder does not exist.")
        transcript_dir = folder / "transcripts"
        if not transcript_dir.exists():
            raise HTTPException(status_code=400, detail="Selected folder has no transcripts directory.")

        job = self.store.create(mode="summary")
        thread = threading.Thread(target=self._run_summary_job, args=(job.id, payload), daemon=True)
        thread.start()
        return job

    def _normalize_job_folder(self, folder: Path) -> Path:
        if folder.name.lower() == "transcripts" and folder.parent.exists():
            return folder.parent
        return folder

    def _raise_if_cancelled(self, job_id: str) -> None:
        if self.store.is_cancelled(job_id):
            raise CancelledError("Job cancelled by user.")

    def _run_stt_job(self, job_id: str, payload: StartJobRequest) -> None:
        try:
            self.store.patch(job_id, status="running", detail="starting")
            self._raise_if_cancelled(job_id)
            folder, title, source_audio = self._download_audio(job_id, payload)
            segments = self._split_audio(job_id, source_audio, folder, payload.chunk_minutes)
            transcript_paths = self._transcribe(
                job_id=job_id,
                folder=folder,
                segments=segments,
                model_name=payload.whisper_model,
                compute=payload.compute,
                language=payload.language,
                batch_size=payload.batch_size,
                stt_profile=payload.stt_profile,
            )
            self._rebuild_full_transcript(job_id, folder, transcript_paths)
            self.store.patch(
                job_id,
                status="completed",
                detail="Local STT finished",
                progress=0.82,
                stage_progress=1.0,
                folder=str(folder),
                title=title,
            )
            if payload.auto_summary:
                self.store.log(job_id, "Auto Gemini processing is ON. Start summary from existing transcripts.")
                summary_payload = SummaryJobRequest(
                    api_key=payload.api_key,
                    folder=str(folder),
                    reference_notes=payload.reference_notes,
                )
                self._run_summary_job(job_id, summary_payload, reuse_existing_job=True)
        except CancelledError as exc:
            self.store.patch(job_id, status="cancelled", detail=str(exc), error=None)
            self.store.log(job_id, str(exc))
        except Exception as exc:
            self.store.patch(job_id, status="failed", detail=str(exc), error=str(exc))
            self.store.log(job_id, f"Error: {exc}")

    def _run_summary_job(self, job_id: str, payload: SummaryJobRequest, reuse_existing_job: bool = False) -> None:
        try:
            self._raise_if_cancelled(job_id)
            folder = Path(payload.folder)
            title = folder.name
            if not reuse_existing_job:
                self.store.patch(
                    job_id,
                    status="running",
                    detail="Gemini summary starting",
                    folder=str(folder),
                    title=title,
                    progress=0.84,
                )
            transcript_paths = self._load_transcript_paths(folder)
            if not transcript_paths:
                raise RuntimeError("No transcript files were found.")
            self._summarize(job_id, folder, title, transcript_paths, payload.api_key, payload.reference_notes)
            self.store.patch(job_id, status="completed", detail="Gemini summary finished", progress=1.0, stage_progress=1.0)
        except CancelledError as exc:
            self.store.patch(job_id, status="cancelled", detail=str(exc), error=None)
            self.store.log(job_id, str(exc))
        except Exception as exc:
            self.store.patch(job_id, status="failed", detail=str(exc), error=str(exc))
            self.store.log(job_id, f"Error: {exc}")

    def _run_uploaded_audio_job(
        self,
        job_id: str,
        folder: Path,
        title: str,
        source_audio: Path,
        language: str,
        chunk_minutes: int,
        whisper_model: str,
        compute: str,
        batch_size: int,
        stt_profile: str,
    ) -> None:
        try:
            self.store.patch(job_id, status="running", detail="starting uploaded audio STT")
            self._raise_if_cancelled(job_id)
            segments = self._split_audio(job_id, source_audio, folder, chunk_minutes)
            transcript_paths = self._transcribe(
                job_id=job_id,
                folder=folder,
                segments=segments,
                model_name=whisper_model,
                compute=compute,
                language=language,
                batch_size=batch_size,
                stt_profile=stt_profile,
            )
            full_path = self._rebuild_full_transcript(job_id, folder, transcript_paths)
            self.store.log(job_id, f"Meeting transcript ready: {full_path.name}")
            self.store.patch(job_id, status="completed", detail="Meeting transcript finished", progress=1.0, stage_progress=1.0, title=title)
        except CancelledError as exc:
            self.store.patch(job_id, status="cancelled", detail=str(exc), error=None)
            self.store.log(job_id, str(exc))
        except Exception as exc:
            self.store.patch(job_id, status="failed", detail=str(exc), error=str(exc))
            self.store.log(job_id, f"Error: {exc}")

    def _download_audio(self, job_id: str, payload: StartJobRequest):
        self.store.patch(job_id, detail="Downloading low-quality audio", progress=0.03, stage_progress=0.0)
        root = Path(payload.save_dir).expanduser()
        root.mkdir(parents=True, exist_ok=True)

        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as probe:
            info = probe.extract_info(payload.url.strip(), download=False)

        title = self._safe_name(info.get("title") or "SOOP_VOD", max_length=72)
        folder = root / title
        self._ensure_job_dirs(folder)
        self.store.log(job_id, f"Job folder: {folder}")

        entry_count = len(info.get("entries", [])) if info.get("entries") else 1
        duration = info.get("duration")
        if duration:
            self.store.log(job_id, f"Metadata duration: {self._fmt_seconds(duration)} | entries={entry_count}")

        ydl_opts = {
            "paths": {"home": str(folder)},
            "format": "worstaudio/worst",
            "outtmpl": "%(autonumber)s_source.%(ext)s" if entry_count > 1 else "source.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "ffmpeg_location": str(BASE_DIR),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "40"}],
            "postprocessor_args": ["-ac", "1", "-ar", "16000", "-map_metadata", "-1"],
            "concurrent_fragment_downloads": 8,
            "retries": 10,
            "fragment_retries": 10,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([payload.url.strip()])

        mp3_candidates = sorted(
            [
                folder / name
                for name in os.listdir(folder)
                if (folder / name).is_file()
                and name.lower().endswith(".mp3")
                and (re.match(r"^\d+_source\.mp3$", name.lower()) or name.lower() == "source.mp3")
            ]
        )
        if not mp3_candidates:
            mp3_candidates = sorted(
                [
                    folder / name
                    for name in os.listdir(folder)
                    if (folder / name).is_file() and name.lower().endswith(".mp3") and not name.lower().startswith("part")
                ]
            )
        if not mp3_candidates:
            raise RuntimeError("No MP3 source file was created.")

        normalized = []
        for candidate in mp3_candidates:
            target = self._audio_dir(folder) / candidate.name
            if candidate.resolve() != target.resolve():
                if target.exists():
                    target.unlink()
                shutil.move(str(candidate), str(target))
            normalized.append(target)
        mp3_candidates = normalized

        merged = self._audio_dir(folder) / "source_full.mp3"
        if len(mp3_candidates) == 1:
            if mp3_candidates[0].resolve() != merged.resolve():
                shutil.copyfile(mp3_candidates[0], merged)
        else:
            self._merge_audio(job_id, mp3_candidates, merged, folder)

        actual_duration = self._probe_duration(merged)
        self.store.log(job_id, f"Merged source duration: {self._fmt_seconds(actual_duration)}")
        self.store.patch(job_id, progress=0.18, stage_progress=1.0, folder=str(folder), title=title)
        self.store.log(job_id, f"Download complete: {merged.name}")
        return folder, title, merged

    def _save_uploaded_audio(self, upload: UploadFile, save_dir: str) -> tuple[Path, str, Path]:
        filename = Path(upload.filename or "meeting_recording.wav").name
        stem = self._safe_name(Path(filename).stem or "meeting_recording", max_length=60)
        ext = Path(filename).suffix or ".wav"
        root = Path(save_dir).expanduser() if str(save_dir or "").strip() else (APP_DIR / "data" / "meeting_uploads")
        root.mkdir(parents=True, exist_ok=True)

        title = self._safe_name(f"{stem}_{time.strftime('%Y%m%d_%H%M%S')}", max_length=80)
        folder = root / title
        self._ensure_job_dirs(folder)

        source_audio = self._audio_dir(folder) / f"source_upload{ext.lower()}"
        with source_audio.open("wb") as output:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        upload.file.close()

        if source_audio.stat().st_size <= 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        return folder, title, source_audio

    def _split_audio(self, job_id: str, audio_path: Path, folder: Path, chunk_minutes: int):
        minutes = max(5, int(chunk_minutes or 15))
        segment_seconds = minutes * 60
        self.store.patch(job_id, detail=f"Splitting audio every {minutes} minutes", stage_progress=0.1)
        self.store.log(job_id, f"Split source: {audio_path.name}")

        for old in self._list_part_files(folder):
            try:
                old.unlink()
            except OSError:
                pass

        total_duration = self._probe_duration(audio_path)
        if total_duration <= 0:
            raise RuntimeError("Could not read source duration.")

        chunks = []
        start = 0.0
        index = 0
        while start < total_duration:
            duration = min(segment_seconds, total_duration - start)
            chunks.append((index, start, duration))
            start += segment_seconds
            index += 1

        self.store.log(job_id, f"Planned chunks: {len(chunks)} from total {self._fmt_seconds(total_duration)}")
        paths = []
        for idx, start_time, duration in chunks:
            self._raise_if_cancelled(job_id)
            out_path = self._audio_dir(folder) / f"part{idx:03d}.wav"
            self.store.patch(
                job_id,
                detail=f"Extracting chunk {idx + 1}/{len(chunks)}: start={self._fmt_seconds(start_time)} len={self._fmt_seconds(duration)}",
                stage_progress=(idx + 1) / max(1, len(chunks)),
            )
            self.store.log(job_id, f"Chunk extract start: {out_path.name} | start={self._fmt_seconds(start_time)} | duration={self._fmt_seconds(duration)}")

            command = [
                str(FFMPEG_PATH),
                "-y",
                "-ss",
                self._ffmpeg_time(start_time),
                "-t",
                self._ffmpeg_time(duration),
                "-i",
                str(audio_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-map_metadata",
                "-1",
                str(out_path),
            ]
            self._run_subprocess(command, job_id=job_id)
            paths.append(out_path)
            self.store.log(job_id, f"Chunk ready: {out_path.name} {self._fmt_size(out_path.stat().st_size)}")

        segments = [
            SegmentFile(index=idx, path=str(path), duration=self._probe_duration(path), start_offset=chunks[idx][1])
            for idx, path in enumerate(paths)
        ]
        self.store.patch(job_id, progress=0.25, stage_progress=1.0)
        self.store.log(job_id, f"Split complete: {len(segments)} chunk(s)")
        return segments

    def _transcribe(self, job_id: str, folder: Path, segments: list[SegmentFile], model_name: str, compute: str, language: str, batch_size: int, stt_profile: str):
        self.store.patch(job_id, detail="Loading Whisper model", stage_progress=0.02)
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self.store.log(job_id, f"Whisper model cache: {MODEL_DIR}")
        cpu_count = os.cpu_count() or 8
        cpu_threads = max(4, min(cpu_count, cpu_count - 2 if cpu_count > 6 else cpu_count))
        num_workers = max(1, min(4, cpu_count // 4))
        self.store.log(job_id, f"CPU tuning: logical_cores={cpu_count} cpu_threads={cpu_threads} workers={num_workers}")

        base_model = WhisperModel(model_name, device="cpu", compute_type=compute, cpu_threads=cpu_threads, num_workers=num_workers, download_root=str(MODEL_DIR))
        pipeline = BatchedInferencePipeline(model=base_model) if (BatchedInferencePipeline and stt_profile != "accurate") else None

        total_audio = sum(max(1.0, item.duration) for item in segments)
        done_audio = 0.0
        average_rtf = None
        transcript_paths = []

        for order, item in enumerate(segments, start=1):
            self._raise_if_cancelled(job_id)
            chunk_name = Path(item.path).name
            self.store.log(job_id, f"STT start: {chunk_name} ({self._fmt_seconds(item.duration)})")
            self.store.patch(job_id, detail=f"Chunk {order}/{len(segments)}: 00:00 / {self._fmt_seconds(item.duration)}")

            kwargs: dict[str, Any] = {
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
                kwargs["batch_size"] = max(1, int(batch_size or 8))

            started = time.time()
            iterator_source = pipeline if pipeline else base_model
            segments_iter, info = iterator_source.transcribe(item.path, **kwargs)

            rows = []
            text_lines = []
            last_report = 0.0
            for piece in segments_iter:
                self._raise_if_cancelled(job_id)
                self._raise_if_cancelled(job_id)
                clean_text = piece.text.strip()
                global_start = item.start_offset + piece.start
                global_end = item.start_offset + piece.end
                rows.append(
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
                    rtf = elapsed / max(1.0, processed)
                    average_rtf = rtf if average_rtf is None else (average_rtf * 0.7 + rtf * 0.3)
                    remain = max(0.0, (item.duration - processed) * average_rtf)
                    self.store.patch(
                        job_id,
                        detail=f"Chunk {order}/{len(segments)}: {self._fmt_seconds(processed)} / {self._fmt_seconds(item.duration)} | ETA {self._fmt_eta(remain)}",
                        progress=0.25 + 0.55 * ((done_audio + processed) / max(1.0, total_audio)),
                        stage_progress=(done_audio + processed) / max(1.0, total_audio),
                    )
                    last_report = piece.end

            done_audio += item.duration
            elapsed = time.time() - started
            self.store.log(job_id, f"STT done: {chunk_name} in {self._fmt_eta(elapsed)} | language={getattr(info, 'language', 'unknown')}")

            text_path = self._transcripts_dir(folder) / f"part_{item.index:03d}_transcript.txt"
            json_path = self._segments_dir(folder) / f"part_{item.index:03d}_segments.json"
            text_path.write_text("\n".join(text_lines), encoding="utf-8")
            json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            transcript_paths.append({"segment": item, "text_path": str(text_path)})

        self.store.patch(job_id, progress=0.80, stage_progress=1.0)
        self.store.log(job_id, "STT stage complete.")
        return transcript_paths

    def _summarize(self, job_id: str, folder: Path, title: str, transcript_paths: list[dict[str, Any]], api_key: str, reference_notes: str):
        self.store.patch(job_id, detail="Creating timeline from transcript parts...", stage_progress=0.02)
        self.store.log(job_id, "Summary mode: 3-part grouped timeline merge")
        legacy_genai.configure(api_key=api_key)
        model = legacy_genai.GenerativeModel(GEMINI_MODEL)

        full_transcript_path = self._rebuild_full_transcript(job_id, folder, transcript_paths)
        full_transcript = full_transcript_path.read_text(encoding="utf-8").strip()
        cleaned_text = self._clean_transcript_locally(full_transcript)
        (self._summaries_dir(folder) / "cleaned_full_script.txt").write_text(cleaned_text, encoding="utf-8")
        self.store.log(job_id, "Local cleaned_full_script generated.")

        parts_dir = self._summaries_dir(folder) / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        ordered = sorted(transcript_paths, key=lambda item: item["segment"].index)
        grouped = [ordered[i:i + 3] for i in range(0, len(ordered), 3)]
        group_blocks = []

        for idx, group in enumerate(grouped, start=1):
            self._raise_if_cancelled(job_id)
            group_indices = [item["segment"].index for item in group]
            start_idx, end_idx = group_indices[0], group_indices[-1]
            label = f"parts {start_idx:03d}-{end_idx:03d}" if start_idx != end_idx else f"part {start_idx:03d}"
            self.store.patch(job_id, detail=f"Gemini grouped timeline {idx}/{len(grouped)} ({label})")
            combined = []
            for item in group:
                combined.append(f"[Part {item['segment'].index:03d}]\n{Path(item['text_path']).read_text(encoding='utf-8').strip()}")
            prompt = self._part_timeline_prompt(title, label, self._truncate_text("\n\n".join(combined), 22000), reference_notes)
            response = model.generate_content(prompt)
            self._raise_if_cancelled(job_id)
            part_text = self._extract_model_text(response)
            out_path = parts_dir / f"group_{start_idx:03d}_{end_idx:03d}_timeline.txt"
            out_path.write_text(part_text, encoding="utf-8")
            group_blocks.append(f"[Group {label}]\n{part_text}")
            ratio = idx / max(1, len(grouped))
            self.store.patch(job_id, progress=0.86 + 0.08 * ratio, stage_progress=0.20 + 0.55 * ratio)
            self.store.log(job_id, f"Grouped timeline complete: {out_path.name}")

        merge_prompt = self._timeline_merge_prompt(title, "\n\n".join(group_blocks), reference_notes)
        self._raise_if_cancelled(job_id)
        merge_response = model.generate_content(merge_prompt)
        self._raise_if_cancelled(job_id)
        final_text = self._extract_model_text(merge_response)
        (self._summaries_dir(folder) / "timeline.txt").write_text(final_text, encoding="utf-8")
        (self._summaries_dir(folder) / "final_summary.txt").write_text(final_text, encoding="utf-8")
        self.store.log(job_id, "Gemini summary complete.")

    def _load_transcript_paths(self, folder: Path) -> list[dict[str, Any]]:
        transcript_dir = self._transcripts_dir(folder)
        if not transcript_dir.exists():
            return []
        entries = []
        for name in sorted(os.listdir(transcript_dir)):
            match = re.match(r"^part_(\d+)_transcript\.txt$", name)
            if match:
                index = int(match.group(1))
                entries.append({"segment": SegmentFile(index=index, path="", duration=0.0, start_offset=0.0), "text_path": str(transcript_dir / name)})
        return entries

    def _rebuild_full_transcript(self, job_id: str, folder: Path, transcript_paths: list[dict[str, Any]]) -> Path:
        ordered = sorted(transcript_paths, key=lambda item: item["segment"].index)
        combined = []
        for item in ordered:
            text = Path(item["text_path"]).read_text(encoding="utf-8").strip()
            if text:
                combined.append(text)
        full_path = self._transcripts_dir(folder) / "full_transcript.txt"
        full_path.write_text("\n\n".join(combined), encoding="utf-8")
        self.store.log(job_id, f"full_transcript rebuilt: {full_path}")
        return full_path

    def _clean_transcript_locally(self, text: str) -> str:
        lines = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            line = re.sub(r"\s+", " ", line)
            line = re.sub(r"([^\w\s\[\]:])\1{3,}", r"\1\1", line)
            line = re.sub(r"([媛-?쥱-Za-z0-9])\1{5,}", r"\1\1\1", line)
            line = re.sub(r"(\b\S+\b)( \1){3,}", r"\1 \1", line)
            line = re.sub(r"\?{3,}", "??", line)
            lines.append(line)
        return "\n".join(lines)

    def _part_timeline_prompt(self, title: str, part_index_label: str, transcript_text: str, reference_notes: str) -> str:
        notes = self._truncate_text(reference_notes, 2000).strip() or "?놁쓬"
        return f"""
?뱀떊? SOOP ?ㅼ떆蹂닿린 ??꾨씪???뺣━ ?먮뵒?곕떎.

諛섎뱶???쒓뎅?대줈留??듯븯??
???묒뾽? ?꾩껜 諛⑹넚?????뚰듃留??ㅻ，??
二쇱뼱吏?transcript ?덉뿉 ?덈뒗 ?쒓컙?쒖? ?댁슜留??ъ슜?섎씪.
異붿젙 湲덉?. 遺덊솗?ㅽ븯硫??앸왂?섎씪.

諛⑹넚 ?쒕ぉ: {title}
?뚰듃 踰붿쐞: {part_index_label}
李멸퀬 硫붾え:
{notes}

異쒕젰 洹쒖튃:
- ?뱀뀡 ?쒕ぉ 2~5媛??뺣룄濡쒕쭔 臾띠뼱??
- 媛??ш굔 以꾩? 諛섎뱶??`[ 00:00:00 ]` ?뺤떇???⑤씪.
- transcript???덈뒗 ?쒓컙?쒕? 洹몃?濡??쒖슜?섎씪.
- ?덈Т ?ъ냼??援곕뜑?붽린 ??붾뒗 以꾩씠怨? ?ш굔/?꾪솚/諛섏쓳 以묒떖?쇰줈 ?뺣━?섎씪.
- 臾몄옣? 吏㏐퀬 紐낇솗?섍쾶 ?곸뼱??

transcript:
{transcript_text}
"""

    def _timeline_merge_prompt(self, title: str, merged_part_timelines: str, reference_notes: str) -> str:
        notes = self._truncate_text(reference_notes, 2500).strip() or "?놁쓬"
        return f"""
?뱀떊? SOOP ?ㅼ떆蹂닿린 ?꾩껜 ??꾨씪???몄쭛?먮떎.

諛섎뱶???쒓뎅?대줈留??듯븯??
?꾨옒?먮뒗 媛??뚰듃?먯꽌 ?대? 異붿텧????꾨씪??珥덉븞???덈떎.
??珥덉븞?ㅼ쓣 ?쒓컙 ?쒖꽌?濡?蹂묓빀?댁꽌 理쒖쥌 ??꾨씪??臾몄꽌瑜?留뚮뱾?대씪.

洹쒖튃:
- ?덈줈???ъ떎??留뚮뱾吏 留덈씪.
- 以묐났?섎뒗 ?댁슜? ?⑹퀜??
- ?뱀뀡 ?쒕ぉ? 4~8媛??뺣룄濡??뺣━?섎씪.
- 媛??ш굔 以꾩? 諛섎뱶??`[ 00:00:00 ]` ?뺤떇???좎??섎씪.
- ?꾩껜 臾몄꽌???щ엺???쎄린 醫뗭? ??꾨씪??臾몄꽌泥섎읆 ?⑤씪.
- 異붿젙?섏? 留먭퀬, ?좊ℓ?섎㈃ ?쏀븯寃??쒗쁽?섍굅???앸왂?섎씪.

諛⑹넚 ?쒕ぉ: {title}
李멸퀬 硫붾え:
{notes}

?뚰듃蹂???꾨씪??珥덉븞:
{merged_part_timelines}
"""

    def _extract_model_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if text and text.strip():
            return text.strip()
        candidates = getattr(response, "candidates", None) or []
        finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
        if finish_reason is not None:
            raise RuntimeError(f"Gemini returned no text. finish_reason={finish_reason}.")
        raise RuntimeError("Gemini returned no text.")

    def _merge_audio(self, job_id: str, files: list[Path], output: Path, folder: Path) -> None:
        list_path = folder / "merge_list.txt"
        with open(list_path, "w", encoding="utf-8") as file:
            for path in files:
                normalized = str(path).replace("\\", "/").replace("'", "'\\''")
                file.write(f"file '{normalized}'\n")
        self._run_subprocess([str(FFMPEG_PATH), "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output)])
        try:
            list_path.unlink()
        except OSError:
            pass

    def _probe_duration(self, path: Path) -> float:
        command = [
            str(FFPROBE_PATH),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        output = self._run_subprocess(command, capture_output=True)
        try:
            return float(output.strip())
        except Exception:
            return 0.0

    def _run_subprocess(self, command: list[str], capture_output: bool = False, job_id: str | None = None) -> str:
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags)
        while process.poll() is None:
            if job_id and self.store.is_cancelled(job_id):
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise CancelledError("Job cancelled by user.")
            time.sleep(0.2)
        stdout, stderr = process.communicate()
        stdout_text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else (stdout or "")
        stderr_text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else (stderr or "")
        if process.returncode != 0:
            raise RuntimeError(stderr_text.strip() or stdout_text.strip() or "subprocess failed")
        return stdout_text if capture_output else ""

    def _ensure_job_dirs(self, folder: Path) -> None:
        for path in (self._audio_dir(folder), self._transcripts_dir(folder), self._segments_dir(folder), self._summaries_dir(folder)):
            path.mkdir(parents=True, exist_ok=True)

    def _list_part_files(self, folder: Path) -> list[Path]:
        audio_dir = self._audio_dir(folder)
        if not audio_dir.exists():
            return []
        return sorted(path for path in audio_dir.iterdir() if path.is_file() and path.name.lower().startswith("part"))

    def _audio_dir(self, folder: Path) -> Path:
        return folder / "audio"

    def _transcripts_dir(self, folder: Path) -> Path:
        return folder / "transcripts"

    def _segments_dir(self, folder: Path) -> Path:
        return folder / "segments"

    def _summaries_dir(self, folder: Path) -> Path:
        return folder / "summaries"

    def _safe_name(self, value: str, max_length: int = 80) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|]+', "", value).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return (cleaned[:max_length].rstrip() or "SOOP_VOD")

    def _truncate_text(self, text: str, max_chars: int) -> str:
        return text if len(text) <= max_chars else text[:max_chars]

    def _fmt_seconds(self, value: float) -> str:
        total = max(0, int(value))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _ffmpeg_time(self, seconds: float) -> str:
        return self._fmt_seconds(seconds)

    def _fmt_eta(self, seconds: float) -> str:
        total = max(0, int(seconds))
        m = total // 60
        s = total % 60
        if m >= 60:
            h = m // 60
            m = m % 60
            return f"{h}h {m}m {s}s"
        return f"{m}m {s}s"

    def _fmt_size(self, size: int) -> str:
        if size >= 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024 * 1024):.2f}GB"
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        if size >= 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size}B"


store = JobStore()
service = PipelineService(store)
remote_service = SoopRemoteService()
app = FastAPI(title="SOOP WebApp V1")


def load_runtime_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_remote_start_payload(url: str, overrides: RemoteSummaryStartRequest) -> StartJobRequest:
    config = load_runtime_config()
    api_key = overrides.api_key or str(config.get("api_key") or "").strip()
    save_dir = overrides.save_dir or str(config.get("save_dir") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is missing. Set it in config.json or send it in the request.")
    if not save_dir:
        raise HTTPException(status_code=400, detail="save_dir is missing. Set it in config.json or send it in the request.")

    def pick_int(override: int | None, *keys: str, fallback: int) -> int:
        if override is not None:
            return override
        for key in keys:
            value = config.get(key)
            if value not in (None, ""):
                return int(value)
        return fallback

    def pick_str(override: str | None, *keys: str, fallback: str) -> str:
        if override is not None and override != "":
            return override
        for key in keys:
            value = config.get(key)
            if value not in (None, ""):
                return str(value)
        return fallback

    auto_summary = overrides.auto_summary
    if auto_summary is None:
        auto_summary = bool(config.get("v3_auto_summary", False))

    return StartJobRequest(
        api_key=api_key,
        save_dir=save_dir,
        url=url,
        language=pick_str(overrides.language, "v3_language", "stt_language", fallback="ko"),
        chunk_minutes=pick_int(overrides.chunk_minutes, "v3_chunk_minutes", "segment_minutes", fallback=15),
        whisper_model=pick_str(overrides.whisper_model, "v3_model", "stt_model_size", fallback="medium"),
        compute=pick_str(overrides.compute, "v3_compute", "stt_compute_type", fallback="int8"),
        batch_size=pick_int(overrides.batch_size, "v3_batch", fallback=8),
        stt_profile=pick_str(overrides.stt_profile, "v3_stt_profile", fallback="balanced"),
        reference_notes=pick_str(overrides.reference_notes, "v3_reference_notes", fallback=""),
        auto_summary=bool(auto_summary),
    )


@app.middleware("http")
async def token_guard(request: Request, call_next):
    protected_prefixes = ("/api/remote/", "/api/soop/")
    if SERVER_TOKEN and request.url.path.startswith(protected_prefixes):
        provided = request.headers.get("x-api-token", "").strip()
        auth = request.headers.get("authorization", "").strip()
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
        if provided != SERVER_TOKEN:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index():
    if not INDEX_HTML.exists():
        return HTMLResponse("<h1>Missing webapp/index.html</h1>", status_code=500)
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.get("/api/system/status")
def system_status():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    cached_models = [path.name for path in MODEL_DIR.iterdir() if path.is_dir()]
    home = Path.home()
    downloads = home / "Downloads"
    desktop = home / "Desktop"
    documents = home / "Documents"
    return {
        "app_dir": str(APP_DIR),
        "resource_dir": str(RESOURCE_DIR),
        "model_dir": str(MODEL_DIR),
        "ffmpeg_exists": FFMPEG_PATH.exists(),
        "ffprobe_exists": FFPROBE_PATH.exists(),
        "cached_models": cached_models,
        "default_paths": {
            "home": str(home),
            "downloads": str(downloads),
            "downloads_test": str(downloads / "test"),
            "desktop": str(desktop),
            "documents": str(documents),
        },
    }


@app.get("/api/remote/config")
def remote_config():
    config = load_runtime_config()
    api_key = str(config.get("api_key") or "").strip()
    return {
        "server_host": SERVER_HOST,
        "server_port": SERVER_PORT,
        "token_required": bool(SERVER_TOKEN),
        "config_path": str(CONFIG_PATH),
        "has_api_key": bool(api_key),
        "save_dir": str(config.get("save_dir") or ""),
        "language": str(config.get("v3_language") or config.get("stt_language") or "ko"),
        "chunk_minutes": int(config.get("v3_chunk_minutes") or config.get("segment_minutes") or 15),
        "whisper_model": str(config.get("v3_model") or config.get("stt_model_size") or "medium"),
        "compute": str(config.get("v3_compute") or config.get("stt_compute_type") or "int8"),
        "batch_size": int(config.get("v3_batch") or 8),
        "stt_profile": str(config.get("v3_stt_profile") or "balanced"),
        "auto_summary": bool(config.get("v3_auto_summary", False)),
    }


@app.get("/api/soop/streamers")
def list_soop_streamers():
    return remote_service.list_streamers()


@app.post("/api/soop/streamers")
def add_soop_streamer(payload: RemoteStreamerCreate):
    try:
        return remote_service.add_streamer(payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/soop/streamers/{streamer_id}")
def delete_soop_streamer(streamer_id: str):
    ok = remote_service.remove_streamer(streamer_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Streamer not found")
    return {"ok": True, "streamer_id": streamer_id}


@app.post("/api/soop/streamers/refresh-live")
def refresh_soop_live_all():
    return remote_service.refresh_all_live()


@app.post("/api/soop/streamers/{streamer_id}/refresh-live")
def refresh_soop_live(streamer_id: str):
    try:
        return remote_service.refresh_streamer_live(streamer_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/soop/streamers/{streamer_id}/refresh-vods")
def refresh_soop_vods(streamer_id: str, limit: int = Query(default=4, ge=1, le=12)):
    try:
        return remote_service.refresh_streamer_vods(streamer_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/soop/streamers/{streamer_id}/latest-vod")
def latest_vod(streamer_id: str):
    vod = remote_service.latest_vod(streamer_id)
    if not vod:
        raise HTTPException(status_code=404, detail="No VOD found")
    return vod


@app.post("/api/soop/streamers/{streamer_id}/start-latest-summary")
def start_latest_summary(streamer_id: str, payload: RemoteSummaryStartRequest):
    latest = remote_service.latest_vod(streamer_id)
    if not latest:
        raise HTTPException(status_code=404, detail="No latest VOD found for this streamer")
    start_payload = build_remote_start_payload(latest["url"], payload)
    job = service.start_stt(start_payload)
    return {
        "job_id": job.id,
        "streamer_id": streamer_id,
        "vod_url": latest["url"],
        "vod_title": latest["title"],
    }


@app.post("/api/remote/start-summary-from-url")
def remote_start_summary_from_url(payload: RemoteSummaryStartRequest):
    if not payload.url:
        raise HTTPException(status_code=400, detail="url is required")
    start_payload = build_remote_start_payload(payload.url, payload)
    job = service.start_stt(start_payload)
    return {"job_id": job.id, "url": payload.url}


@app.get("/api/dialog/select-folder")
def select_folder(initial: str | None = Query(default=None)):
    try:
        selected = select_folder_dialog(initial)
        return {"folder": selected or ""}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/open-folder")
def open_folder(payload: dict[str, str]):
    folder = Path(payload.get("folder") or "")
    if not folder.exists():
        raise HTTPException(status_code=400, detail="Folder does not exist")
    subprocess.Popen(["explorer", str(folder)])
    return {"ok": True}

@app.get("/api/jobs")
def list_jobs():
    return [job.__dict__ for job in store.all()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.__dict__


@app.get("/api/jobs/{job_id}/transcript")
def get_job_transcript(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.folder:
        raise HTTPException(status_code=400, detail="This job has no output folder.")

    folder = Path(job.folder)
    full_path = service._transcripts_dir(folder) / "full_transcript.txt"
    if not full_path.exists():
        transcript_paths = service._load_transcript_paths(folder)
        if not transcript_paths:
            raise HTTPException(status_code=404, detail="Transcript not found yet.")
        full_path = service._rebuild_full_transcript(job_id, folder, transcript_paths)

    return {
        "job_id": job_id,
        "title": job.title or folder.name,
        "folder": str(folder),
        "path": str(full_path),
        "text": full_path.read_text(encoding="utf-8"),
    }


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    ok = store.delete(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}

@app.delete("/api/jobs")
def clear_finished_jobs():
    removed = store.clear_finished()
    return {"removed": removed}

@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = service.cancel_job(job_id)
    return {"job_id": job.id, "status": job.status}

@app.post("/api/jobs/start-stt")
def start_stt(payload: StartJobRequest):
    job = service.start_stt(payload)
    return {"job_id": job.id}


@app.post("/api/jobs/upload-meeting-audio")
async def upload_meeting_audio(
    audio_file: UploadFile = File(...),
    save_dir: str = Form(""),
    language: str = Form("ko"),
    chunk_minutes: int = Form(15),
    whisper_model: str = Form("medium"),
    compute: str = Form("int8"),
    batch_size: int = Form(8),
    stt_profile: str = Form("balanced"),
):
    if not (audio_file.filename or "").strip():
        raise HTTPException(status_code=400, detail="audio_file is required")
    job = service.start_uploaded_audio(
        upload=audio_file,
        save_dir=save_dir,
        language=language,
        chunk_minutes=chunk_minutes,
        whisper_model=whisper_model,
        compute=compute,
        batch_size=batch_size,
        stt_profile=stt_profile,
    )
    return {"job_id": job.id, "mode": job.mode}


@app.post("/api/jobs/start-summary")
def start_summary(payload: SummaryJobRequest):
    job = service.start_summary(payload)
    return {"job_id": job.id}



if __name__ == "__main__":
    import uvicorn

    if OPEN_BROWSER_ON_START:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{SERVER_HOST}:{SERVER_PORT}")).start()
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_config=None, access_log=False)
