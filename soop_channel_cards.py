import json
import os
import re
import threading
import time
from dataclasses import dataclass
from html import unescape
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError, URLError

import customtkinter as ctk
import pyperclip
from PIL import Image


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "soop_channel_cards.json"
COOKIE_PATH = BASE_DIR / "cookies_soop.pkl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_duration_ms(value: int | str | None) -> str:
    if value in (None, ""):
        return ""
    try:
        total_seconds = int(value) // 1000
    except (TypeError, ValueError):
        return ""
    hours, remain = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remain, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def fetch_text(url: str, timeout: int = 15) -> str:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_bytes(url: str, timeout: int = 15) -> bytes:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, timeout: int = 15, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = None
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        payload = parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = request.Request(url, data=payload, headers=headers)
    with request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset, errors="replace"))


def parse_streamer_id(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    patterns = [
        r"sooplive\.co\.kr/station/([A-Za-z0-9_]+)",
        r"ch\.sooplive\.co\.kr/([A-Za-z0-9_]+)",
        r"m\.sooplive\.co\.kr/station/([A-Za-z0-9_]+)",
        r"^([A-Za-z0-9_]+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return ""


def channel_url_for(streamer_id: str) -> str:
    return f"https://www.sooplive.co.kr/station/{streamer_id}"


def vod_url_for(streamer_id: str) -> str:
    return f"https://www.sooplive.co.kr/station/{streamer_id}/vod"


def profile_image_url_for(streamer_id: str) -> str:
    prefix = streamer_id[:2]
    return f"https://stimg.sooplive.co.kr/LOGO/{prefix}/{streamer_id}/m/{streamer_id}.webp"


@dataclass
class VodPreview:
    title: str
    url: str
    thumbnail_url: str
    duration_text: str = ""


class VodPreviewCard(ctk.CTkFrame):
    def __init__(self, master: Any, preview: dict[str, Any], image: ctk.CTkImage | None, copy_callback: Any):
        super().__init__(master, fg_color="#243240", corner_radius=12, border_width=1, border_color="#31495f")
        self.preview = preview
        self.copy_callback = copy_callback
        self.image_ref = image
        self.grid_columnconfigure(1, weight=1)

        self.thumb = ctk.CTkLabel(self, text="THUMB", width=180, height=102, fg_color="#101820", corner_radius=10)
        self.thumb.grid(row=0, column=0, rowspan=3, padx=12, pady=12)
        if image is not None:
            self.thumb.configure(text="", image=image)

        self.title = ctk.CTkTextbox(self, height=74, fg_color="#1c2833")
        self.title.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(12, 8))
        self.title.insert("1.0", preview.get("title") or "(제목 없음)")
        self.title.configure(state="disabled")

        duration = preview.get("duration_text") or ""
        self.meta = ctk.CTkLabel(self, text=duration, text_color="#93a7ba", anchor="w")
        self.meta.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(0, 8))

        ctk.CTkButton(
            self,
            text="링크 복사",
            fg_color="#1f6fb5",
            command=lambda: self.copy_callback(preview["url"]),
        ).grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(0, 12))

        ctk.CTkButton(
            self,
            text="열기",
            fg_color="#55616d",
            command=lambda: os.startfile(preview["url"]),
        ).grid(row=2, column=2, sticky="ew", padx=(0, 12), pady=(0, 12))


class StreamerCard(ctk.CTkFrame):
    def __init__(self, master: Any, streamer: dict[str, Any], select_callback: Any, delete_callback: Any):
        super().__init__(master, fg_color="#212c38", corner_radius=14, border_width=2, border_color="#2f4053")
        self.streamer = streamer
        self.select_callback = select_callback
        self.delete_callback = delete_callback
        self.image_ref = None

        self.grid_columnconfigure(2, weight=1)

        self.image_label = ctk.CTkLabel(self, text="IMG", width=62, height=62, fg_color="#0d141c", corner_radius=10)
        self.image_label.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)

        self.name_label = ctk.CTkLabel(self, text=streamer.get("nickname") or streamer["id"], font=("Malgun Gothic", 16, "bold"), anchor="w")
        self.name_label.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(10, 0))

        self.id_label = ctk.CTkLabel(self, text=streamer["id"], font=("Arial", 12), text_color="#8fa0b1", anchor="w")
        self.id_label.grid(row=1, column=1, sticky="w", pady=(0, 10))

        self.status_label = ctk.CTkLabel(self, text="Unchecked", font=("Arial", 12, "bold"), text_color="#9db0c0", width=90)
        self.status_label.grid(row=0, column=3, rowspan=2, padx=8)

        self.delete_button = ctk.CTkButton(
            self,
            text="X",
            width=36,
            height=30,
            fg_color="#8c2630",
            hover_color="#a52f3b",
            command=lambda: self.delete_callback(streamer["id"]),
        )
        self.delete_button.grid(row=0, column=4, rowspan=2, padx=(4, 12))

        for widget in (self, self.image_label, self.name_label, self.id_label, self.status_label):
            widget.bind("<Button-1>", self._handle_click)

    def _handle_click(self, _event: Any) -> None:
        self.select_callback(self.streamer["id"])

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.configure(border_color="#4ab87a", fg_color="#263847")
        else:
            self.configure(border_color="#2f4053", fg_color="#212c38")

    def set_profile_image(self, image: ctk.CTkImage | None) -> None:
        self.image_ref = image
        if image is None:
            self.image_label.configure(text="IMG", image=None)
        else:
            self.image_label.configure(text="", image=image)

    def update_streamer(self, streamer: dict[str, Any]) -> None:
        self.streamer = streamer
        self.name_label.configure(text=streamer.get("nickname") or streamer["id"])
        self.id_label.configure(text=streamer["id"])
        self.set_status(streamer.get("is_live"))

    def set_status(self, is_live: bool | None) -> None:
        if is_live is True:
            self.status_label.configure(text="LIVE", text_color="#ff686f")
            self.name_label.configure(text_color="#ffffff")
        elif is_live is False:
            self.status_label.configure(text="Offline", text_color="#8fa0b1")
            self.name_label.configure(text_color="#ffffff")
        else:
            self.status_label.configure(text="Unchecked", text_color="#9db0c0")
            self.name_label.configure(text_color="#ffffff")


class SoopChannelCardsApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SOOP Channel Cards")
        self.geometry("1220x820")
        self.minsize(1180, 760)

        self.input_var = ctk.StringVar()
        self.status_var = ctk.StringVar(value="Ready")
        self.streamers: list[dict[str, Any]] = []
        self.cards: dict[str, StreamerCard] = {}
        self.selected_id: str | None = None
        self.image_cache: dict[tuple[str, int, int], ctk.CTkImage] = {}

        self._build_ui()
        self._load_config()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        left.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(left, text="SOOP Cards", font=("Arial", 24, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 12))

        input_box = ctk.CTkFrame(left, fg_color="#1d2732")
        input_box.grid(row=1, column=0, sticky="new")
        input_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(input_box, text="채널 링크 또는 방송국 아이디", font=("Arial", 13)).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        ctk.CTkEntry(input_box, textvariable=self.input_var, width=370, placeholder_text="예: https://www.sooplive.co.kr/station/nanamoon777").grid(row=1, column=0, padx=12, sticky="ew")
        ctk.CTkButton(input_box, text="카드 추가", command=self.add_channel_from_input, fg_color="#1f6fb5").grid(row=2, column=0, padx=12, pady=10, sticky="ew")
        ctk.CTkButton(input_box, text="전체 라이브 확인", command=self.check_live_all, fg_color="#1f9a59").grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")

        self.card_list = ctk.CTkScrollableFrame(left, width=430, fg_color="#131b22")
        self.card_list.grid(row=2, column=0, sticky="nsew", pady=(14, 0))

        right = ctk.CTkFrame(self, fg_color="#18212b")
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 18), pady=18)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(right, text="상세 패널", font=("Arial", 20, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))

        self.summary_box = ctk.CTkFrame(right, fg_color="#202c38")
        self.summary_box.grid(row=1, column=0, sticky="ew", padx=18)
        self.summary_box.grid_columnconfigure(1, weight=1)

        self.detail_profile = ctk.CTkLabel(self.summary_box, text="IMG", width=96, height=96, fg_color="#0f151c", corner_radius=12)
        self.detail_profile.grid(row=0, column=0, rowspan=4, padx=14, pady=14)
        self.detail_profile_ref = None

        self.detail_name = ctk.CTkLabel(self.summary_box, text="카드를 선택해 주세요", font=("Malgun Gothic", 20, "bold"), anchor="w")
        self.detail_name.grid(row=0, column=1, sticky="ew", pady=(16, 4))

        self.detail_id = ctk.CTkLabel(self.summary_box, text="-", font=("Arial", 13), text_color="#9fb0c0", anchor="w")
        self.detail_id.grid(row=1, column=1, sticky="ew")

        self.detail_live = ctk.CTkLabel(self.summary_box, text="라이브 상태: 미확인", font=("Arial", 13), text_color="#9fb0c0", anchor="w")
        self.detail_live.grid(row=2, column=1, sticky="ew")

        self.detail_channel = ctk.CTkLabel(self.summary_box, text="", font=("Arial", 12), text_color="#7e93a6", anchor="w", wraplength=720, justify="left")
        self.detail_channel.grid(row=3, column=1, sticky="ew", pady=(0, 16))

        self.vod_box = ctk.CTkFrame(right, fg_color="#202c38")
        self.vod_box.grid(row=2, column=0, sticky="nsew", padx=18, pady=16)
        self.vod_box.grid_columnconfigure(0, weight=1)
        self.vod_box.grid_rowconfigure(1, weight=1)

        vod_header = ctk.CTkFrame(self.vod_box, fg_color="transparent")
        vod_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
        vod_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(vod_header, text="최근 다시보기", font=("Arial", 18, "bold")).grid(row=0, column=0, sticky="w")

        self.refresh_vod_button = ctk.CTkButton(
            vod_header,
            text="다시보기 새로고침",
            command=self.refresh_selected_vod,
            fg_color="#1f9a59",
            state="disabled",
            width=140,
        )
        self.refresh_vod_button.grid(row=0, column=1, padx=(8, 8))

        self.open_channel_button = ctk.CTkButton(
            vod_header,
            text="채널 열기",
            command=self.open_selected_channel,
            fg_color="#555f6a",
            state="disabled",
            width=110,
        )
        self.open_channel_button.grid(row=0, column=2)

        self.vod_list_frame = ctk.CTkScrollableFrame(self.vod_box, fg_color="#17222c")
        self.vod_list_frame.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.vod_list_frame.grid_columnconfigure(0, weight=1)

        self.vod_empty_label = ctk.CTkLabel(
            self.vod_list_frame,
            text="카드를 선택하면 최근 다시보기 3~4개를 불러옵니다.",
            text_color="#98abbb",
            anchor="w",
            justify="left",
        )
        self.vod_empty_label.grid(row=0, column=0, sticky="ew", padx=10, pady=12)
        self.vod_preview_cards: list[VodPreviewCard] = []

        self.log_box = ctk.CTkTextbox(right, height=160)
        self.log_box.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))

        ctk.CTkLabel(self, textvariable=self.status_var, text_color="#8ea3b6", anchor="w").grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 12))

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.status_var.set(message)

    def _load_config(self) -> None:
        if not CONFIG_PATH.exists():
            return
        try:
            items = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(items, list):
                self.streamers = items
        except Exception as exc:
            self.log(f"설정 파일을 읽지 못했습니다: {exc}")
            self.streamers = []
        for streamer in self.streamers:
            streamer.setdefault("channel_url", channel_url_for(streamer["id"]))
            streamer.setdefault("nickname", streamer["id"])
            streamer.setdefault("profile_image_url", profile_image_url_for(streamer["id"]))
            streamer.setdefault("is_live", None)
            streamer.setdefault("live_title", "")
            if "vod_previews" not in streamer:
                legacy_preview = streamer.pop("latest_vod", None)
                streamer["vod_previews"] = [legacy_preview] if legacy_preview else []
        for streamer in self.streamers:
            self._create_card(streamer)
            self._apply_card_visuals(streamer["id"])

    def _save_config(self) -> None:
        CONFIG_PATH.write_text(json.dumps(self.streamers, ensure_ascii=False, indent=2), encoding="utf-8")

    def _find_streamer(self, streamer_id: str) -> dict[str, Any] | None:
        for streamer in self.streamers:
            if streamer["id"] == streamer_id:
                return streamer
        return None

    def _create_card(self, streamer: dict[str, Any]) -> None:
        card = StreamerCard(self.card_list, streamer, self.select_card, self.delete_card)
        card.pack(fill="x", padx=6, pady=6)
        self.cards[streamer["id"]] = card

    def _fetch_ctk_image(self, url: str, size: tuple[int, int]) -> ctk.CTkImage | None:
        if not url:
            return None
        key = (url, size[0], size[1])
        if key in self.image_cache:
            return self.image_cache[key]
        try:
            data = fetch_bytes(url)
            image = Image.open(BytesIO(data)).convert("RGB")
            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=size)
            self.image_cache[key] = ctk_image
            return ctk_image
        except Exception:
            return None

    def _apply_card_visuals(self, streamer_id: str) -> None:
        streamer = self._find_streamer(streamer_id)
        card = self.cards.get(streamer_id)
        if not streamer or not card:
            return
        card.update_streamer(streamer)
        card.set_selected(streamer_id == self.selected_id)
        image = self._fetch_ctk_image(streamer.get("profile_image_url", ""), (62, 62))
        card.set_profile_image(image)

    def add_channel_from_input(self) -> None:
        raw = self.input_var.get().strip()
        streamer_id = parse_streamer_id(raw)
        if not streamer_id:
            self.log("채널 링크나 방송국 아이디 형식이 올바르지 않습니다.")
            return
        if self._find_streamer(streamer_id):
            self.log(f"{streamer_id} 는 이미 등록되어 있습니다.")
            return
        self.input_var.set("")
        self.log(f"{streamer_id} 정보를 불러오는 중...")

        def worker() -> None:
            try:
                profile = self.fetch_streamer_profile(streamer_id)
                streamer = {
                    "id": streamer_id,
                    "channel_url": channel_url_for(streamer_id),
                    "nickname": profile.get("nickname") or streamer_id,
                    "profile_image_url": profile.get("profile_image_url") or profile_image_url_for(streamer_id),
                    "is_live": None,
                    "live_title": "",
                    "vod_previews": [],
                }
                self.streamers.append(streamer)
                self._save_config()
                self.after(0, lambda: self._create_and_select(streamer))
                self.log(f"{streamer_id} 카드가 추가되었습니다.")
            except Exception as exc:
                self.log(f"{streamer_id} 등록 실패: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _create_and_select(self, streamer: dict[str, Any]) -> None:
        self._create_card(streamer)
        self._apply_card_visuals(streamer["id"])
        self.select_card(streamer["id"])

    def delete_card(self, streamer_id: str) -> None:
        self.streamers = [item for item in self.streamers if item["id"] != streamer_id]
        card = self.cards.pop(streamer_id, None)
        if card:
            card.destroy()
        if self.selected_id == streamer_id:
            self.selected_id = None
            self._clear_detail()
        self._save_config()
        self.log(f"{streamer_id} 카드를 삭제했습니다.")

    def _clear_detail(self) -> None:
        self.detail_name.configure(text="카드를 선택해 주세요")
        self.detail_id.configure(text="-")
        self.detail_live.configure(text="라이브 상태: 미확인", text_color="#9fb0c0")
        self.detail_channel.configure(text="")
        self.detail_profile.configure(text="IMG", image=None)
        self.detail_profile_ref = None
        self._set_vod_previews([])
        self.refresh_vod_button.configure(state="disabled")
        self.open_channel_button.configure(state="disabled")

    def select_card(self, streamer_id: str) -> None:
        self.selected_id = streamer_id
        for sid in self.cards:
            self._apply_card_visuals(sid)
        streamer = self._find_streamer(streamer_id)
        if not streamer:
            return
        self._fill_detail(streamer)
        self.refresh_vod_button.configure(state="normal")
        self.open_channel_button.configure(state="normal")
        self.log(f"{streamer_id} 카드를 선택했습니다. 최근 다시보기를 불러옵니다.")
        self.load_vod_previews(streamer_id)

    def _fill_detail(self, streamer: dict[str, Any]) -> None:
        self.detail_name.configure(text=streamer.get("nickname") or streamer["id"])
        self.detail_id.configure(text=f"ID: {streamer['id']}")
        if streamer.get("is_live") is True:
            self.detail_live.configure(text="라이브 상태: LIVE", text_color="#ff686f")
        elif streamer.get("is_live") is False:
            self.detail_live.configure(text="라이브 상태: Offline", text_color="#9fb0c0")
        else:
            self.detail_live.configure(text="라이브 상태: 미확인", text_color="#9fb0c0")
        if streamer.get("live_title"):
            self.detail_live.configure(text=f"라이브 상태: LIVE / {streamer['live_title']}", text_color="#ff686f")
        self.detail_channel.configure(text=streamer.get("channel_url", ""))
        image = self._fetch_ctk_image(streamer.get("profile_image_url", ""), (96, 96))
        self.detail_profile_ref = image
        if image is None:
            self.detail_profile.configure(text="IMG", image=None)
        else:
            self.detail_profile.configure(text="", image=image)
        self._set_vod_previews(streamer.get("vod_previews") or [])

    def _clear_vod_cards(self) -> None:
        for card in self.vod_preview_cards:
            card.destroy()
        self.vod_preview_cards = []
        self.vod_empty_label.grid_forget()

    def _set_vod_previews(self, previews: list[dict[str, Any]]) -> None:
        self._clear_vod_cards()
        if not previews:
            self.vod_empty_label.configure(text="최근 다시보기가 없습니다.")
            self.vod_empty_label.grid(row=0, column=0, sticky="ew", padx=10, pady=12)
            return
        for index, preview in enumerate(previews):
            thumb = self._fetch_ctk_image(preview.get("thumbnail_url", ""), (180, 102))
            card = VodPreviewCard(self.vod_list_frame, preview, thumb, self.copy_vod_link)
            card.grid(row=index, column=0, sticky="ew", padx=8, pady=(0, 10))
            self.vod_preview_cards.append(card)

    def fetch_streamer_profile(self, streamer_id: str) -> dict[str, str]:
        try:
            data = fetch_json(f"https://st.sooplive.co.kr/api/get_station_status.php?szBjId={streamer_id}")
            station = data.get("DATA") or {}
            nickname = station.get("user_nick") or streamer_id
            return {
                "nickname": nickname,
                "profile_image_url": profile_image_url_for(streamer_id),
            }
        except Exception:
            html = fetch_text(channel_url_for(streamer_id))
            nickname_match = re.search(r'ProfileInfo_nick[^>]*>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
            image_match = re.search(r'ProfileInfo_profileImg.*?<img src="([^"]+)"', html, re.IGNORECASE | re.DOTALL)
            title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            nickname = clean_text(nickname_match.group(1)) if nickname_match else ""
            if not nickname and title_match:
                nickname = clean_text(title_match.group(1)).replace("| SOOP", "").strip()
            return {
                "nickname": nickname or streamer_id,
                "profile_image_url": image_match.group(1).strip() if image_match else profile_image_url_for(streamer_id),
            }

    def fetch_live_info(self, streamer_id: str) -> dict[str, Any]:
        data = fetch_json(
            "https://live.sooplive.co.kr/afreeca/player_live_api.php",
            data={"bid": streamer_id},
        )
        channel = data.get("CHANNEL") or {}
        result = int(channel.get("RESULT", 0) or 0)
        return {
            "is_live": result == 1,
            "title": channel.get("TITLE") or "",
            "nickname": channel.get("BJNICK") or "",
            "bno": channel.get("BNO") or "",
        }

    def check_live_all(self) -> None:
        if not self.streamers:
            self.log("먼저 채널 카드를 추가해 주세요.")
            return

        self.log("전체 라이브 상태를 한 번만 확인합니다.")

        def worker() -> None:
            for streamer in self.streamers:
                try:
                    live_info = self.fetch_live_info(streamer["id"])
                    streamer["is_live"] = live_info["is_live"]
                    streamer["live_title"] = live_info["title"]
                    if live_info["nickname"] and (not streamer.get("nickname") or streamer["nickname"] == streamer["id"]):
                        streamer["nickname"] = live_info["nickname"]
                    self.after(0, lambda sid=streamer["id"]: self._apply_card_visuals(sid))
                    if self.selected_id == streamer["id"]:
                        self.after(0, lambda item=dict(streamer): self._fill_detail(item))
                    if live_info["is_live"]:
                        self.log(f"{streamer['id']} 라이브 확인: LIVE / {live_info['title'] or '(제목 없음)'}")
                    else:
                        self.log(f"{streamer['id']} 라이브 확인: Offline")
                except Exception as exc:
                    streamer["is_live"] = False
                    streamer["live_title"] = ""
                    self.after(0, lambda sid=streamer["id"]: self._apply_card_visuals(sid))
                    self.log(f"{streamer['id']} 라이브 확인 실패: {exc}")
            self._save_config()

        threading.Thread(target=worker, daemon=True).start()

    def fetch_vod_previews(self, streamer_id: str, limit: int = 4) -> list[VodPreview]:
        url = (
            f"https://chapi.sooplive.co.kr/api/{streamer_id}/vods/review/streamer"
            f"?keyword=&orderby=reg_date&page=1&field=title,contents,user_nick,user_id"
            f"&per_page={max(limit * 3, 12)}&start_date=&end_date="
        )
        payload = fetch_json(url)
        items = payload.get("data") or []
        previews: list[VodPreview] = []

        for item in items:
            title_no = item.get("title_no")
            if not title_no:
                continue
            try:
                detail_payload = fetch_json(
                    "https://api.m.sooplive.co.kr/station/video/a/view",
                    data={"nTitleNo": title_no},
                )
            except (URLError, HTTPError, TimeoutError):
                continue
            detail = detail_payload.get("data") or {}
            if detail.get("file_type") != "REVIEW":
                continue
            share = detail.get("share") or {}
            url = (share.get("url") or f"https://vod.sooplive.co.kr/player/{title_no}").split("?")[0]
            if "/catch" in url:
                continue
            previews.append(
                VodPreview(
                    title=detail.get("title") or detail.get("bbs_title") or "(제목 없음)",
                    url=url,
                    thumbnail_url=detail.get("thumb") or "",
                    duration_text=format_duration_ms(detail.get("total_file_duration")),
                )
            )
            if len(previews) >= limit:
                break
        return previews

    def load_vod_previews(self, streamer_id: str) -> None:
        streamer = self._find_streamer(streamer_id)
        if not streamer:
            return
        self.refresh_vod_button.configure(state="disabled")
        self.log(f"{streamer_id} 최근 다시보기를 불러오는 중...")

        def worker() -> None:
            try:
                previews = self.fetch_vod_previews(streamer_id, limit=4)
                streamer["vod_previews"] = [preview.__dict__ for preview in previews]
                self._save_config()
                self.after(0, lambda item=dict(streamer): self._fill_detail(item))
                if previews:
                    self.log(f"{streamer_id} 최근 다시보기 {len(previews)}개를 불러왔습니다.")
                else:
                    self.log(f"{streamer_id} 최근 다시보기를 찾지 못했습니다.")
            except Exception as exc:
                self.log(f"{streamer_id} 다시보기 조회 실패: {exc}")
            finally:
                self.after(0, lambda: self.refresh_vod_button.configure(state="normal" if self.selected_id else "disabled"))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_selected_vod(self) -> None:
        if not self.selected_id:
            self.log("먼저 카드를 선택해 주세요.")
            return
        self.load_vod_previews(self.selected_id)

    def copy_vod_link(self, url: str) -> None:
        pyperclip.copy(url)
        self.log("다시보기 링크를 복사했습니다.")

    def open_selected_channel(self) -> None:
        if not self.selected_id:
            return
        streamer = self._find_streamer(self.selected_id)
        if streamer:
            os.startfile(streamer.get("channel_url", channel_url_for(streamer["id"])))

if __name__ == "__main__":
    app = SoopChannelCardsApp()
    app.mainloop()
