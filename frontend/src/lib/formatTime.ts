/**
 * Formats ISO-8601 timestamps (including UTC timestamps) and schedule strings
 * into human-friendly Indonesian date and time strings.
 */

const MONTHS_ID = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "Mei",
  "Jun",
  "Jul",
  "Agu",
  "Sep",
  "Okt",
  "Nov",
  "Des",
];

const DAYS_ID = [
  "Minggu",
  "Senin",
  "Selasa",
  "Rabu",
  "Kamis",
  "Jumat",
  "Sabtu",
];

function mapTzToIana(tzOrLabel?: string): { iana: string; label: string } {
  const clean = (tzOrLabel || "").trim();
  if (clean === "Asia/Makassar" || clean.toUpperCase() === "WITA") {
    return { iana: "Asia/Makassar", label: "WITA" };
  }
  if (clean === "Asia/Jayapura" || clean.toUpperCase() === "WIT") {
    return { iana: "Asia/Jayapura", label: "WIT" };
  }
  return { iana: "Asia/Jakarta", label: "WIB" };
}

/**
 * Formats an audit event or system UTC timestamp into readable Indonesian local time (WIB).
 * Example: "2026-11-07T07:02:41.123456+00:00" -> "07 Nov 2026, 14:02:41 WIB"
 */
export function formatAuditTimestamp(isoString?: string): string {
  if (!isoString) return "-";
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return isoString;

  try {
    const formatter = new Intl.DateTimeFormat("id-ID", {
      timeZone: "Asia/Jakarta",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    const formatted = formatter.format(d).replace(/\./g, ":");
    return `${formatted} WIB`;
  } catch {
    return d.toLocaleString("id-ID");
  }
}

/**
 * Formats a schedule string (such as "2026-10-23T10:00:00+07:00" or "2026-10-23 13:30 WIB")
 * into a friendly Indonesian schedule label:
 * Example: "Jumat, 23 Okt 2026 • Pukul 10:00 WIB"
 */
export function formatScheduleTime(sendAt?: string, tzOrLabel?: string): string {
  if (!sendAt) return "-";
  const raw = sendAt.trim();

  // Case 1: Slot string like "2026-10-23 13:30 WIB"
  const slotMatch = raw.match(
    /^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}:\d{2})(?:\s*(WIB|WITA|WIT))?$/i
  );
  if (slotMatch) {
    const [, yearStr, monthStr, dayStr, hm, slotTz] = slotMatch;
    const year = Number(yearStr);
    const monthIdx = Number(monthStr) - 1;
    const day = Number(dayStr);
    const utcDate = new Date(Date.UTC(year, monthIdx, day));
    const dayName = DAYS_ID[utcDate.getUTCDay()] || "";
    const monthName = MONTHS_ID[monthIdx] || monthStr;
    const tzLabel = (slotTz || tzOrLabel || "WIB").toUpperCase();
    return `${dayName}, ${day} ${monthName} ${year} • Pukul ${hm} ${tzLabel}`;
  }

  // Case 2: ISO-8601 string like "2026-10-23T10:00:00+07:00"
  const d = new Date(raw);
  if (!isNaN(d.getTime())) {
    // Determine target timezone from argument or ISO offset
    let target = mapTzToIana(tzOrLabel);
    if (!tzOrLabel) {
      if (raw.endsWith("+08:00")) target = { iana: "Asia/Makassar", label: "WITA" };
      else if (raw.endsWith("+09:00")) target = { iana: "Asia/Jayapura", label: "WIT" };
    }

    try {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: target.iana,
        weekday: "short",
        year: "numeric",
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).formatToParts(d);

      const map: Record<string, string> = {};
      parts.forEach((p) => {
        map[p.type] = p.value;
      });

      const weekdayMap: Record<string, string> = {
        Sun: "Minggu",
        Mon: "Senin",
        Tue: "Selasa",
        Wed: "Rabu",
        Thu: "Kamis",
        Fri: "Jumat",
        Sat: "Sabtu",
      };
      const dayName = weekdayMap[map.weekday] || "";
      const monthName = MONTHS_ID[Number(map.month) - 1] || map.month;
      const hour = map.hour === "24" ? "00" : map.hour;
      return `${dayName}, ${map.day} ${monthName} ${map.year} • Pukul ${hour}:${map.minute} ${target.label}`;
    } catch {
      return `${d.toLocaleString("id-ID")} ${target.label}`;
    }
  }

  return tzOrLabel ? `${raw} (${tzOrLabel})` : raw;
}

/**
 * Formats a simple YYYY-MM-DD date string into "22 Okt 2026".
 */
export function formatSimpleDate(dateStr?: string): string {
  if (!dateStr) return "-";
  const m = dateStr.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return dateStr;
  const [, year, monthStr, day] = m;
  const monthName = MONTHS_ID[Number(monthStr) - 1] || monthStr;
  return `${ Number(day) } ${monthName} ${year}`;
}
