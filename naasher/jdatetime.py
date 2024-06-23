# Gregorian & Jalali ( Hijri_Shamsi , Solar ) Date Converter  Functions
# Author: JDF.SCR.IR =>> Download Full Version :  http://jdf.scr.ir/jdf
# License: GNU/LGPL _ Open Source & Free :: Version: 2.80 : [2020=1399]
# ---------------------------------------------------------------------
# 355746=361590-5844 & 361590=(30*33*365)+(30*8) & 5844=(16*365)+(16/4)
# 355666=355746-79-1 & 355668=355746-79+1 &  1595=605+990 &  605=621-16
# 990=30*33 & 12053=(365*33)+(32/4) & 36524=(365*100)+(100/4)-(100/100)
# 1461=(365*4)+(4/4)   &   146097=(365*400)+(400/4)-(400/100)+(400/400)

import re
from typing import Any, Callable, NoReturn
from datetime import datetime


def gregorian_to_jalali(gy: int, gm: int, gd: int):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gm > 2:
        gy2 = gy + 1
    else:
        gy2 = gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return (jy, jm, jd), days


def jalali_to_gregorian(jy: int, jm: int, jd: int):
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    if (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0):
        kab = 29
    else:
        kab = 28
    sal_a = [0, 31, kab, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return (gy, gm, gd), days


def __create_jstrftime():

    WEEKDAY_ABBR_NAME = ["۱ش", "۲ش", "۳ش", "۴ش", "۵ش", "ج"]
    WEEKDAY_FULL_NAME = ["یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
    MONTH_FULL_NAME = [
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    ]
    MONTH_ABBR_NAME = [
        "فرو",
        "ارد",
        "خرد",
        "تیر",
        "امر",
        "شهر",
        "مهر",
        "آبا",
        "آذر",
        "دی",
        "بهم",
        "اسف",
    ]

    class JDt(object):
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def NOT_IMPLEMENTED(directive: str):
        def raiser(dt: JDt):
            raise NotImplementedError(
                f"Directive `%{directive}` is yet not implemented for solar hijri date"
            )

        return raiser

    def ordinal_suffix(d: int):
        if d > 10 and d <= 20:
            return "th"
        if d % 10 == 1:
            return "st"
        if d % 10 == 2:
            return "nd"
        if d % 10 == 3:
            return "rd"
        return "th"

    PRE_FORMATTERS: dict[str, Callable[[Any], str]] = {
        "a": lambda dt: WEEKDAY_ABBR_NAME[dt.wd],
        "A": lambda dt: WEEKDAY_FULL_NAME[dt.wd],
        "d": lambda dt: f"{dt.d:02}",
        "x": lambda dt: f"{dt.d}",
        "b": lambda dt: MONTH_ABBR_NAME[dt.m - 1],
        "B": lambda dt: MONTH_FULL_NAME[dt.m - 1],
        "m": lambda dt: f"{dt.m:02}",
        "y": lambda dt: f"{(dt.y % 100):02}",
        "Y": lambda dt: f"{dt.y:04}",
        "p": lambda dt: "ب.ظ." if dt.hour >= 12 else "ق.ظ.",
        "j": lambda dt: f"{dt.days:03}",
        "U": NOT_IMPLEMENTED("U"),
        "W": NOT_IMPLEMENTED("W"),
        "G": NOT_IMPLEMENTED("W"),
        "u": lambda dt: f"{dt.d}{ordinal_suffix(dt.d)}",  # Override this format identifier
        "V": NOT_IMPLEMENTED("W"),
    }

    U_REGEX = re.compile(r"(%+)(" + "|".join(re.escape(k) for k in ["u"]) + ")")
    DIR_REGEX = re.compile(
        r"(%+)(" + "|".join(re.escape(k) for k in PRE_FORMATTERS.keys()) + ")"
    )

    def to_jdt(dt: datetime, is_solar_hijri: bool):
        if is_solar_hijri:
            (y, m, d), days = gregorian_to_jalali(dt.year, dt.month, dt.day)
        else:
            (y, m, d), days = (dt.year, dt.month, dt.day), dt.timetuple().tm_yday
        wd = dt.toordinal() % 7
        return JDt(y=y, m=m, d=d, wd=wd, hour=dt.hour, days=days)

    def create_formatter(dt: datetime, is_solar_hijri: bool):
        def formatter(m: re.Match[str]):
            if len(m.group(1)) % 2 == 0:
                return m.group(0)
            return m.group(1)[:-1] + PRE_FORMATTERS[m.group(2)](to_jdt(dt, is_solar_hijri))

        return formatter

    def jstrftime(dt: datetime, format: str) -> str:
        is_solar_hijri = False
        for suffix in ("SHC", "JC"):
            if format.endswith(suffix):
                is_solar_hijri = True
                format = format[: -len(suffix)]
        corrected_format = re.sub(
            DIR_REGEX if is_solar_hijri else U_REGEX,
            create_formatter(dt, is_solar_hijri),
            format,
        )
        return dt.strftime(corrected_format)

    return jstrftime


jstrftime = __create_jstrftime()
del __create_jstrftime
