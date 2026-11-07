from __future__ import annotations

from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import yaml

from app.config import settings
from app.models.domain import ActionSchedule, ChannelType, PICProfile


def load_operational_rules() -> dict[str, Any]:
    path = Path(settings.CONFIG_DIR) / "operational_rules.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_hhmm(val: str) -> time:
    parts = val.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def map_city_to_timezone(city: str) -> str:
    rules = load_operational_rules()
    city_map: dict[str, str] = rules.get("city_timezone", {})
    for k, tz in city_map.items():
        if k.lower() == city.strip().lower():
            return tz
    # Substring fallback
    city_lower = city.lower()
    if any(c in city_lower for c in ["balikpapan", "samarinda", "makassar", "banjarmasin", "bali", "denpasar"]):
        return "Asia/Makassar"
    if any(c in city_lower for c in ["jayapura", "papua", "timika", "sorong", "ambon"]):
        return "Asia/Jayapura"
    return "Asia/Jakarta"


def get_tz_label(tz_name: str) -> str:
    rules = load_operational_rules()
    labels: dict[str, str] = rules.get("timezone_labels", {})
    return labels.get(tz_name, "WIB")


def _next_working_day_0800(dt_local: datetime, holidays: set[str]) -> datetime:
    candidate = (dt_local + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    while candidate.weekday() >= 5 or candidate.strftime("%Y-%m-%d") in holidays:
        candidate = (candidate + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    return candidate


def _next_weekday(dt_local: datetime, target_weekday: int) -> datetime:
    days_ahead = target_weekday - dt_local.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return dt_local + timedelta(days=days_ahead)


def get_friday_safe_slots(
    recipient_tz_name: str,
    reference_time: datetime,
    sender_tz_name: str = "Asia/Jakarta",
) -> list[str]:
    """
    Returns Friday afternoon/morning slots that are strictly outside 11:30–13:00 in BOTH
    sender and recipient timezones (T1 requirement).
    """
    sender_tz = ZoneInfo(sender_tz_name)
    recip_tz = ZoneInfo(recipient_tz_name)
    tz_label = get_tz_label(recipient_tz_name)

    ref_recip = reference_time.astimezone(recip_tz)
    friday_date = _next_weekday(ref_recip, 4).date()  # 4 = Friday

    candidate_hours = [(10, 0), (13, 30), (14, 0), (14, 30), (15, 0), (16, 0)]
    friday_start = time(11, 30)
    friday_end = time(13, 0)

    safe_slots: list[str] = []
    for hh, mm in candidate_hours:
        slot_recip = datetime(
            friday_date.year, friday_date.month, friday_date.day, hh, mm, tzinfo=recip_tz
        )
        slot_sender = slot_recip.astimezone(sender_tz)

        # Must be strictly outside [11:30, 13:00) in BOTH recipient and sender local time
        in_recip_jumatan = friday_start <= slot_recip.time() < friday_end
        in_sender_jumatan = friday_start <= slot_sender.time() < friday_end

        if not in_recip_jumatan and not in_sender_jumatan:
            safe_slots.append(f"{slot_recip.strftime('%Y-%m-%d %H:%M')} {tz_label}")

    return safe_slots


def evaluate_schedule(
    pic: PICProfile,
    requested_time_str: str,
    current_time: datetime,
    channel: ChannelType | None = None,
    sender_tz_name: str = "Asia/Jakarta",
) -> ActionSchedule:
    """
    Deterministic Indonesia Cultural & Temporal Rules Engine (BR-04, TR-09):
    - Evaluates against recipient's local timezone (WIB UTC+7, WITA UTC+8, WIT UTC+9).
    - Friday prayer block (11:30-13:00 local time in both sender and recipient zones) -> shifts & proposes safe slots (T1).
    - Outside recipient local work_hours (08:00-17:00, or Ramadan 08:00-15:00) ->
      for email: schedules at 08:00 local recipient time next working day;
      for whatsapp: creates owner reminder at 08:00 local recipient time (FR-18, T5).
    """
    rules = load_operational_rules()
    recip_tz_name = pic.timezone or map_city_to_timezone(pic.city)
    recip_tz = ZoneInfo(recip_tz_name)
    sender_tz = ZoneInfo(sender_tz_name)
    tz_label = get_tz_label(recip_tz_name)
    effective_channel = channel or pic.channel_pref

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=sender_tz)

    recip_now = current_time.astimezone(recip_tz)
    holidays = set(rules.get("national_holidays_2026", []))

    ramadan_cfg = rules.get("ramadan", {})
    if ramadan_cfg.get("enabled", False):
        work_start = _parse_hhmm(ramadan_cfg.get("start", "08:00"))
        work_end = _parse_hhmm(ramadan_cfg.get("end", "15:00"))
    else:
        wh_cfg = rules.get("work_hours", {})
        work_start = _parse_hhmm(wh_cfg.get("start", "08:00"))
        work_end = _parse_hhmm(wh_cfg.get("end", "17:00"))

    req_lower = (requested_time_str or "").strip().lower()
    friday_start = _parse_hhmm(rules["friday_prayer_block"]["start"])
    friday_end = _parse_hhmm(rules["friday_prayer_block"]["end"])

    # Check if request explicitly asks for Friday / Jumatan / Jumat siang / Habis Zuhur
    is_friday_request = "jumat" in req_lower or (recip_now.weekday() == 4 and any(
        k in req_lower for k in ["siang", "zuhur", "jumatan", "11:", "12:"]
    ))

    if is_friday_request:
        friday_dt = _next_weekday(recip_now, 4)
        # Default requested time on Friday if "jumat siang" -> 12:00 (which hits Friday prayer block!)
        if "habis zuhur" in req_lower or "setelah zuhur" in req_lower:
            candidate_dt = friday_dt.replace(hour=12, minute=30, second=0, microsecond=0)
        elif "sore" in req_lower:
            candidate_dt = friday_dt.replace(hour=15, minute=0, second=0, microsecond=0)
        elif "pagi" in req_lower:
            candidate_dt = friday_dt.replace(hour=9, minute=30, second=0, microsecond=0)
        else:
            candidate_dt = friday_dt.replace(hour=12, minute=0, second=0, microsecond=0)

        sender_equiv = candidate_dt.astimezone(sender_tz)
        in_recip_jumatan = friday_start <= candidate_dt.time() < friday_end
        in_sender_jumatan = friday_start <= sender_equiv.time() < friday_end

        safe_slots = get_friday_safe_slots(recip_tz_name, current_time, sender_tz_name)
        if in_recip_jumatan or in_sender_jumatan:
            # Shift automatically to the first afternoon slot strictly outside 11:30-13:00 in both zones
            # (e.g., 13:30 WIB or 14:30 WITA so both WIB and WITA are past 13:00)
            chosen_slot_dt = friday_dt.replace(hour=13, minute=30, second=0, microsecond=0)
            while (
                friday_start <= chosen_slot_dt.time() < friday_end
                or friday_start <= chosen_slot_dt.astimezone(sender_tz).time() < friday_end
            ):
                chosen_slot_dt += timedelta(minutes=30)

            return ActionSchedule(
                send_at=chosen_slot_dt.isoformat(),
                tz=recip_tz_name,
                tz_label=tz_label,
                rule_applied="friday_prayer_block_shifted",
                proposed_slots=safe_slots,
                owner_reminder_at=None,
            )

        return ActionSchedule(
            send_at=candidate_dt.isoformat(),
            tz=recip_tz_name,
            tz_label=tz_label,
            rule_applied="friday_schedule_valid",
            proposed_slots=safe_slots,
            owner_reminder_at=None,
        )

    # Check other Indonesian time expressions
    if "habis zuhur" in req_lower or "setelah zuhur" in req_lower:
        target_dt = recip_now.replace(hour=13, minute=30, second=0, microsecond=0)
        return ActionSchedule(
            send_at=target_dt.isoformat(),
            tz=recip_tz_name,
            tz_label=tz_label,
            rule_applied="fuzzy_time_habis_zuhur",
            proposed_slots=[f"{target_dt.strftime('%Y-%m-%d %H:%M')} {tz_label}"],
        )
    if "sore" in req_lower:
        target_dt = recip_now.replace(hour=15, minute=30, second=0, microsecond=0)
        return ActionSchedule(
            send_at=target_dt.isoformat(),
            tz=recip_tz_name,
            tz_label=tz_label,
            rule_applied="fuzzy_time_sore",
            proposed_slots=[f"{target_dt.strftime('%Y-%m-%d %H:%M')} {tz_label}"],
        )

    # Evaluate current/requested time against recipient working hours & Friday prayer
    if (
        recip_now.weekday() == 4
        and (
            friday_start <= recip_now.time() < friday_end
            or friday_start <= recip_now.astimezone(sender_tz).time() < friday_end
        )
    ):
        safe_slots = get_friday_safe_slots(recip_tz_name, current_time, sender_tz_name)
        shifted = recip_now.replace(hour=13, minute=30, second=0, microsecond=0)
        while (
            friday_start <= shifted.time() < friday_end
            or friday_start <= shifted.astimezone(sender_tz).time() < friday_end
        ):
            shifted += timedelta(minutes=30)
        return ActionSchedule(
            send_at=shifted.isoformat(),
            tz=recip_tz_name,
            tz_label=tz_label,
            rule_applied="friday_prayer_block_shifted",
            proposed_slots=safe_slots,
        )

    is_weekend_or_holiday = recip_now.weekday() >= 5 or recip_now.strftime("%Y-%m-%d") in holidays
    is_before_hours = recip_now.time() < work_start
    is_after_hours = recip_now.time() >= work_end

    if is_weekend_or_holiday or is_before_hours or is_after_hours:
        if is_before_hours and not is_weekend_or_holiday:
            next_0800 = recip_now.replace(hour=8, minute=0, second=0, microsecond=0)
        else:
            next_0800 = _next_working_day_0800(recip_now, holidays)

        if effective_channel == "whatsapp":
            return ActionSchedule(
                send_at=next_0800.isoformat(),
                tz=recip_tz_name,
                tz_label=tz_label,
                rule_applied="outside_hours_owner_reminder_0800",
                proposed_slots=[f"{next_0800.strftime('%Y-%m-%d %H:%M')} {tz_label}"],
                owner_reminder_at=next_0800.isoformat(),
            )
        else:
            return ActionSchedule(
                send_at=next_0800.isoformat(),
                tz=recip_tz_name,
                tz_label=tz_label,
                rule_applied="outside_hours_scheduled_0800",
                proposed_slots=[f"{next_0800.strftime('%Y-%m-%d %H:%M')} {tz_label}"],
                owner_reminder_at=None,
            )

    return ActionSchedule(
        send_at=recip_now.isoformat(),
        tz=recip_tz_name,
        tz_label=tz_label,
        rule_applied="within_working_hours",
        proposed_slots=[f"{recip_now.strftime('%Y-%m-%d %H:%M')} {tz_label}"],
        owner_reminder_at=None,
    )

