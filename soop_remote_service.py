import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError, URLError


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "soop_channel_cards.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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


def profile_image_url_for(streamer_id: str) -> str:
    prefix = streamer_id[:2]
    return f"https://stimg.sooplive.co.kr/LOGO/{prefix}/{streamer_id}/m/{streamer_id}.webp"


@dataclass
class VodPreview:
    title: str
    url: str
    thumbnail_url: str
    duration_text: str = ""


class SoopRemoteService:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config_path = config_path

    def _load_raw(self) -> list[dict[str, Any]]:
        if not self.config_path.exists():
            return []
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        items: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, str):
                items.append({"id": item})
            elif isinstance(item, dict):
                items.append(dict(item))
        return items

    def _save_raw(self, streamers: list[dict[str, Any]]) -> None:
        self.config_path.write_text(
            json.dumps(streamers, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_streamers(self) -> list[dict[str, Any]]:
        return self._load_raw()

    def add_streamer(self, raw_value: str) -> dict[str, Any]:
        streamer_id = parse_streamer_id(raw_value)
        if not streamer_id:
            raise ValueError("Could not parse a valid SOOP streamer id from the input")

        streamers = self._load_raw()
        existing = next((item for item in streamers if item.get("id") == streamer_id), None)
        if existing:
            return existing

        profile = self.fetch_streamer_profile(streamer_id)
        item = {
            "id": streamer_id,
            "nickname": profile.get("nickname") or streamer_id,
            "profile_image_url": profile.get("profile_image_url") or profile_image_url_for(streamer_id),
            "channel_url": channel_url_for(streamer_id),
            "is_live": None,
            "live_title": "",
            "vod_previews": [],
            "updated_at": now_iso(),
        }
        streamers.append(item)
        self._save_raw(streamers)
        return item

    def remove_streamer(self, streamer_id: str) -> bool:
        streamers = self._load_raw()
        filtered = [item for item in streamers if item.get("id") != streamer_id]
        if len(filtered) == len(streamers):
            return False
        self._save_raw(filtered)
        return True

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
            nickname_match = re.search(r"ProfileInfo_nick[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
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

    def fetch_vod_previews(self, streamer_id: str, limit: int = 4) -> list[dict[str, Any]]:
        url = (
            f"https://chapi.sooplive.co.kr/api/{streamer_id}/vods/review/streamer"
            f"?keyword=&orderby=reg_date&page=1&field=title,contents,user_nick,user_id"
            f"&per_page={max(limit * 3, 12)}&start_date=&end_date="
        )
        payload = fetch_json(url)
        items = payload.get("data") or []
        previews: list[dict[str, Any]] = []

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
                    title=detail.get("title") or detail.get("bbs_title") or "(untitled)",
                    url=url,
                    thumbnail_url=detail.get("thumb") or "",
                    duration_text=format_duration_ms(detail.get("total_file_duration")),
                ).__dict__
            )
            if len(previews) >= limit:
                break
        return previews

    def refresh_streamer_live(self, streamer_id: str) -> dict[str, Any]:
        streamers = self._load_raw()
        updated: dict[str, Any] | None = None
        for item in streamers:
            if item.get("id") != streamer_id:
                continue
            live_info = self.fetch_live_info(streamer_id)
            item["is_live"] = live_info["is_live"]
            item["live_title"] = live_info["title"]
            item["bno"] = live_info["bno"]
            item["updated_at"] = now_iso()
            if live_info["nickname"]:
                item["nickname"] = live_info["nickname"]
            updated = item
            break
        if updated is None:
            raise ValueError("Streamer not found")
        self._save_raw(streamers)
        return updated

    def refresh_all_live(self) -> list[dict[str, Any]]:
        streamers = self._load_raw()
        for item in streamers:
            try:
                live_info = self.fetch_live_info(item["id"])
                item["is_live"] = live_info["is_live"]
                item["live_title"] = live_info["title"]
                item["bno"] = live_info["bno"]
                if live_info["nickname"]:
                    item["nickname"] = live_info["nickname"]
            except Exception as exc:
                item["is_live"] = False
                item["live_error"] = str(exc)
            item["updated_at"] = now_iso()
        self._save_raw(streamers)
        return streamers

    def refresh_streamer_vods(self, streamer_id: str, limit: int = 4) -> dict[str, Any]:
        streamers = self._load_raw()
        updated: dict[str, Any] | None = None
        for item in streamers:
            if item.get("id") != streamer_id:
                continue
            item["vod_previews"] = self.fetch_vod_previews(streamer_id, limit=limit)
            item["updated_at"] = now_iso()
            updated = item
            break
        if updated is None:
            raise ValueError("Streamer not found")
        self._save_raw(streamers)
        return updated

    def latest_vod(self, streamer_id: str) -> dict[str, Any] | None:
        previews = self.fetch_vod_previews(streamer_id, limit=1)
        return previews[0] if previews else None
