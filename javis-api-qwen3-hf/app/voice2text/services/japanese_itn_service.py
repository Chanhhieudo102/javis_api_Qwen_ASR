# -*- coding: utf-8 -*-
"""japanese_itn_service.py.

========================
Module Inverse Text Normalization (ITN) tổng quát cho tiếng Nhật trong ASR.
Chỉ áp dụng các quy tắc ngữ pháp và biểu diễn số tổng quát, TUYỆT ĐỐI KHÔNG hardcode từ vựng:
1. Chuỗi số đọc rời (đặc trưng số điện thoại, mã số): 'ゼロ五ゼロ' -> '050', '一七八二' -> '1782'.
2. Ngày trong tháng tổng quát: '十四日' -> '14日', '二十一日' -> '21日'.
3. Thời gian tổng quát: '九時' -> '9時', '二十一時' -> '21時', '三十分' -> '30分'.
"""

import re
from typing import ClassVar, Dict

KANJI_DIGIT_MAP: Dict[str, str] = {
    "〇": "0", "零": "0", "ゼロ": "0", "ぜろ": "0",
    "一": "1", "壱": "1", "いち": "1",
    "二": "2", "弐": "2", "に": "2",
    "三": "3", "参": "3", "さん": "3",
    "四": "4", "よん": "4", "し": "4",
    "五": "5", "ご": "5",
    "六": "6", "ろく": "6",
    "七": "7", "なな": "7", "しち": "7",
    "八": "8", "はち": "8",
    "九": "9", "きゅう": "9", "く": "9",
}

KANJI_DIGITS_ONLY: Dict[str, str] = {
    "〇": "0", "零": "0",
    "一": "1", "壱": "1",
    "二": "2", "弐": "2",
    "三": "3", "参": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}

KANJI_UNIT_MULTIPLIERS: Dict[str, int] = {
    "十": 10,
    "百": 100,
    "千": 1000,
    "万": 10000,
}


def kanji_number_to_arabic(kanji_str: str) -> int:
    """Chuyển chuỗi chữ Hán số lượng tổng quát (như 十四, 二十一, 百二十) sang int."""
    val = 0
    temp = 0
    for char in kanji_str:
        if char in KANJI_DIGITS_ONLY:
            temp = int(KANJI_DIGITS_ONLY[char])
        elif char in KANJI_UNIT_MULTIPLIERS:
            unit_val = KANJI_UNIT_MULTIPLIERS[char]
            if temp == 0:
                temp = 1
            val += temp * unit_val
            temp = 0
    val += temp
    return val


class JapaneseITNService:
    """Dịch vụ chuẩn hóa số tổng quát (ITN) tiếng Nhật cho ASR."""

    # Pre-compiled Regex patterns for performance (avoids recompiling per call)
    _PHONE_DIGIT_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"([〇零ゼロぜろ一二三四五六七八九壱弐参]{2,})"
    )
    _DAY_PATTERN: ClassVar[re.Pattern] = re.compile(r"([一二三四五六七八九十]+)日")
    _HOUR_PATTERN: ClassVar[re.Pattern] = re.compile(r"([一二三四五六七八九十]+)時")
    _MINUTE_PATTERN: ClassVar[re.Pattern] = re.compile(r"([一二三四五六七八九十]+)分")
    _COUNTER_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"([一二三四五六七八九十百]+)(件|人|月|年|番|回)"
    )
    _COMPOUND_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"([〇一二三四五六七八九十百千]+)(月|日|年|号|番|回|件|人|階|本|台|枚|冊|個|袋)"
    )

    # Full-width digit -> half-width digit mapping
    _FULLWIDTH_DIGIT_MAP: ClassVar[dict] = str.maketrans(
        "０１２３４５６７８９", "0123456789"
    )

    # General Simplified Chinese -> Japanese Shinjitai Kanji mapping
    # Multilingual models (like Qwen) occasionally output Chinese simplified glyphs.
    _SIMPLIFIED_KANJI_MAP: ClassVar[dict] = str.maketrans({
        "时": "時", "话": "話", "说": "説", "为": "為", "开": "開",
        "关": "関", "见": "見", "电": "電", "认": "認", "东": "東",
        "车": "車", "门": "門", "贝": "貝", "页": "頁", "给": "給",
        "长": "長", "发": "発", "记": "記", "头": "頭", "经": "経",
        "问": "問", "间": "間", "学": "学", "体": "体", "声": "声",
        "线": "線", "总": "総", "请": "請", "县": "県", "机": "機",
        "实": "実", "语": "語", "报": "報", "会": "会", "结": "結",
    })

    @classmethod
    def normalize_phone_digit_sequences(cls, text: str) -> str:
        """Nhận diện và chuyển đổi các chuỗi số đọc rời tổng quát (đặc trưng số điện thoại / ID).

        Ví dụ: 'ゼロ五ゼロ' -> '050', '一七八二' -> '1782', '一八八ゼロ' -> '1880'.
        """
        def replace_digits(m: re.Match) -> str:
            s = m.group(1)
            # Nếu chứa các đơn vị hàng chục, trăm, nghìn thì không phải chuỗi số đọc rời
            if any(k in s for k in ("十", "百", "千", "万")):
                return s
            res = []
            i = 0
            while i < len(s):
                matched = False
                for token, digit in (("ゼロ", "0"), ("ぜろ", "0")):
                    if s[i:i + 2] == token:
                        res.append(digit)
                        i += 2
                        matched = True
                        break
                if not matched:
                    ch = s[i]
                    res.append(KANJI_DIGIT_MAP.get(ch, ch))
                    i += 1
            return "".join(res)

        return cls._PHONE_DIGIT_PATTERN.sub(replace_digits, text)

    @classmethod
    def normalize_time_and_dates(cls, text: str) -> str:
        """Chuẩn hóa ngày tháng và thời gian tổng quát:

        '十四日' -> '14日', '二十一日' -> '21日', '十時' -> '10時', '二十一時' -> '21時'.
        """
        text = cls._DAY_PATTERN.sub(
            lambda m: f"{kanji_number_to_arabic(m.group(1))}日", text
        )
        text = cls._HOUR_PATTERN.sub(
            lambda m: f"{kanji_number_to_arabic(m.group(1))}時", text
        )
        text = cls._MINUTE_PATTERN.sub(
            lambda m: f"{kanji_number_to_arabic(m.group(1))}分", text
        )
        return text

    @classmethod
    def normalize_quantifiers(cls, text: str) -> str:
        """Chuẩn hóa số đếm tổng quát đi kèm các lượng từ thông dụng:

        '一件' -> '1件', '三人' -> '3人', '五月' -> '5月', '一年' -> '1年', '一番' -> '1番', '一回' -> '1回'.
        """
        return cls._COUNTER_PATTERN.sub(
            lambda m: f"{kanji_number_to_arabic(m.group(1))}{m.group(2)}", text
        )

    @classmethod
    def normalize_mixed_numbers(cls, text: str) -> str:
        """Chuẩn hóa số hỗn hợp Kanji-Arabic thường xuất hiện trong ASR nhật.

        Ví dụ:
          '10月19日' -> '10月19日' (giữ nguyên — đã là dạng chuẩn)
          '１０月１９日' -> '10月19日' (full-width -> half-width)
          '一月十九日' -> '1月19日'
        """
        # 1. Full-width digit -> half-width digit
        text = text.translate(cls._FULLWIDTH_DIGIT_MAP)

        # 2. Kanji standalone decade + unit
        def replace_compound(m: re.Match) -> str:
            try:
                val = kanji_number_to_arabic(m.group(1))
                return f"{val}{m.group(2)}"
            except Exception:
                return m.group(0)

        return cls._COMPOUND_PATTERN.sub(replace_compound, text)

    @classmethod
    def normalize_kanji_variants(cls, text: str) -> str:
        """Map common simplified Hanzi variants to standard Japanese Shinjitai Kanji."""
        return text.translate(cls._SIMPLIFIED_KANJI_MAP)

    @classmethod
    def normalize(cls, text: str) -> str:
        """Chuẩn hóa số tổng quát và Hán tự trong transcript."""
        if not text:
            return ""

        # 0. Chuẩn hóa Hán tự giản thể sang Hán tự chuẩn Nhật (Shinjitai)
        text = cls.normalize_kanji_variants(text)

        # 1. Full-width and mixed Kanji-Arabic numbers
        text = cls.normalize_mixed_numbers(text)

        # 2. Chuẩn hóa ngày tháng, giờ giấc tổng quát
        text = cls.normalize_time_and_dates(text)

        # 3. Chuẩn hóa các lượng từ đếm tổng quát
        text = cls.normalize_quantifiers(text)

        # 4. Chuẩn hóa chuỗi số đọc rời tổng quát
        text = cls.normalize_phone_digit_sequences(text)

        return text
