import json
import re
from datetime import datetime
from typing import Optional


def _strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing ```json ... ``` wrapper if present."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    t = re.sub(r"^```(?:json)?\s*", "", t, count=1, flags=re.IGNORECASE)
    t = t.rstrip()
    if t.endswith("```"):
        t = t[:-3].rstrip()
    return t.strip()


def _extract_first_json_object(text: str) -> Optional[str]:
    """
    Extract the first balanced {...} span, respecting strings and escapes.
    Avoids greedy ``{.*}`` matching past the real end when extra ``}`` appears outside JSON.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    n = len(text)
    i = start
    while i < n:
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return None


def parse_response_json(result_text: str):
    """Parse model text response into JSON object."""
    if not result_text or not str(result_text).strip():
        raise ValueError("模型返回为空")

    raw = str(result_text).strip()
    stripped = _strip_markdown_fences(raw)

    for candidate in (stripped, raw):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    for source in (stripped, raw):
        blob = _extract_first_json_object(source)
        if blob:
            try:
                return json.loads(blob)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"模型返回的 JSON 无法解析：{e.msg}（约第 {e.lineno} 行、字符 {e.pos}）。"
                    "Claude Sonnet 4 单次输出可达数万 token；若在约 1 万字符附近报错，多数是 JSON 语法错误（如漏逗号、引号未转义），"
                    "一般不是 config 里 max_tokens 不够。若因输出上限截断，控制台会提示 stop_reason=max_tokens。"
                ) from e

    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(
                f"模型返回的 JSON 无法解析（备用提取后仍失败）：{e.msg}（约第 {e.lineno} 行、字符 {e.pos}）。"
            ) from e
    raise ValueError("响应中未找到可解析的 JSON")


def format_to_mmddyyyy(date_value):
    """Convert common date formats to MM/DD/YYYY; return original if conversion fails."""
    if date_value is None:
        return date_value
    if not isinstance(date_value, str):
        return date_value

    value = date_value.strip()
    if not value:
        return date_value

    if re.match(r"^\d{2}/\d{2}/\d{4}$", value):
        return value

    iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if iso_match:
        year, month, day = iso_match.groups()
        return f"{month}/{day}/{year}"

    for fmt in ("%Y/%m/%d", "%m-%d-%Y", "%m/%d/%Y", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%m/%d/%Y")
        except ValueError:
            continue

    return date_value


def format_to_yyyymmdd(date_value):
    """Convert common date formats to YYYY-MM-DD; return original if conversion fails."""
    if date_value is None or not isinstance(date_value, str):
        return date_value

    value = date_value.strip()
    if not value:
        return date_value

    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value

    if " " in value and re.match(r"^\d{4}-\d{2}-\d{2}\s", value):
        return value.split(" ", 1)[0]
    if "T" in value and re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        return value.split("T", 1)[0]

    ym_match = re.match(r"^(\d{4})[-/](\d{1,2})$", value)
    if ym_match:
        year, month = ym_match.groups()
        month_num = int(month)
        if 1 <= month_num <= 12:
            return f"{year}-{month_num:02d}"
        return date_value

    dmy_match = re.match(r"^(\d{1,2})([-/])(\d{1,2})\2(\d{4})$", value)
    if dmy_match:
        first, sep, second, year = dmy_match.groups()
        first_num = int(first)
        second_num = int(second)
        if sep == "/":
            month, day = first_num, second_num
            if first_num > 12 and second_num <= 12:
                day, month = first_num, second_num
        else:
            day, month = first_num, second_num
            if second_num > 12 and first_num <= 12:
                month, day = first_num, second_num
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d}"

    for fmt in ("%Y/%m/%d", "%d-%m-%Y", "%m-%d-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_value


def format_to_ddmmyyyy(date_value):
    """Convert common date formats to DD-MM-YYYY; return original if conversion fails."""
    if date_value is None or not isinstance(date_value, str):
        return date_value

    value = date_value.strip()
    if not value:
        return date_value

    if re.match(r"^\d{2}-\d{2}-\d{4}$", value):
        return value

    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        year, month, day = value.split("-")
        return f"{day}-{month}-{year}"

    if re.match(r"^\d{4}/\d{2}/\d{2}$", value):
        year, month, day = value.split("/")
        return f"{day}-{month}-{year}"

    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            continue

    return date_value


def format_to_yyyymm(date_value):
    """Convert common date formats to YYYY-MM; return original if conversion fails."""
    if date_value is None or not isinstance(date_value, str):
        return date_value

    value = date_value.strip()
    if not value:
        return date_value

    if re.match(r"^\d{4}-\d{2}$", value):
        return value
    if re.match(r"^\d{4}/\d{2}$", value):
        year, month = value.split("/")
        return f"{year}-{month}"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value[:7]

    for fmt in ("%d-%m-%Y", "%m-%d-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m")
        except ValueError:
            continue

    return date_value


def is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def extract_digits_as_int(value):
    if not isinstance(value, str):
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def is_non_price_text(value) -> bool:
    if not isinstance(value, str):
        return False
    value_lower = value.strip().lower()
    non_price_patterns = [
        "private driveway",
        "private garage",
        "private street",
        "private lot",
        "private parking",
        "street",
        "garage",
        "driveway",
        "parking",
        "yes",
        "no",
        "new",
        "used",
        "demo",
    ]
    return value_lower in non_price_patterns


def normalize_name_field(name: str) -> str:
    if not isinstance(name, str):
        return name

    name = name.strip()
    if not name:
        return name

    name = re.sub(r"[\u200B-\u200D\uFEFF]", "", name)
    try:
        name = re.sub(r"[^\w\s\-\'\.]", "", name, flags=re.UNICODE)
    except Exception:
        name = re.sub(r"[^\w\s\-\'\.]", "", name)

    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return name

    words = [w.strip() for w in name.split() if w.strip()]
    if len(words) == 0:
        return name

    cleaned_words = []
    for word in words:
        try:
            cleaned_word = re.sub(r"[^\w\-\']", "", word, flags=re.UNICODE)
        except Exception:
            cleaned_word = re.sub(r"[^\w\-\']", "", word)
        if cleaned_word:
            cleaned_words.append(cleaned_word)

    if len(cleaned_words) == 0:
        return "Unknown Unknown"

    if len(cleaned_words) < 2:
        single_word = cleaned_words[0]
        if len(single_word) >= 2:
            return f"{single_word} {single_word}"
        padded = single_word.ljust(2, "X")
        return f"{single_word} {padded}"

    last_word = cleaned_words[-1]
    if len(last_word) < 2:
        if len(cleaned_words) >= 2:
            second_last = cleaned_words[-2]
            if len(second_last) >= 2:
                first_name_parts = cleaned_words[:-2] + [last_word]
                first_name = " ".join(first_name_parts) if first_name_parts else second_last
                if not first_name or not first_name.strip():
                    first_name = second_last if len(second_last) >= 1 else "Unknown"
                return f"{first_name} {second_last}"
            combined_last_name = second_last + last_word
            if len(combined_last_name) >= 2:
                first_name = " ".join(cleaned_words[:-2]) if len(cleaned_words) > 2 else "Unknown"
                if not first_name or not first_name.strip():
                    first_name = "Unknown"
                return f"{first_name} {combined_last_name}"
            padded_last = combined_last_name.ljust(2, "X")
            first_name = " ".join(cleaned_words[:-2]) if len(cleaned_words) > 2 else "Unknown"
            if not first_name or not first_name.strip():
                first_name = "Unknown"
            return f"{first_name} {padded_last}"
        padded_last = last_word.ljust(2, "X")
        return f"{last_word} {padded_last}"

    first_name_parts = cleaned_words[:-1]
    first_name = " ".join(first_name_parts)
    if not first_name or not first_name.strip():
        if len(cleaned_words) >= 2:
            first_name = cleaned_words[0]
        else:
            first_name = "Unknown"

    last_name = cleaned_words[-1]
    if len(last_name) < 2:
        last_name = last_name.ljust(2, "X")

    result = f"{first_name} {last_name}"
    result_words = result.split()
    if len(result_words) < 2:
        if len(result_words) == 1:
            single = result_words[0]
            return f"{single} {single}"
        return "Unknown Unknown"

    result_first_name = " ".join(result_words[:-1])
    if not result_first_name or not result_first_name.strip():
        result_first_name = result_words[0] if len(result_words) > 0 else "Unknown"
        result = f"{result_first_name} {result_words[-1]}"

    return result


def validate_and_debug_name(name: str, field_name: str):
    if not isinstance(name, str):
        print(f"[WARNING] {field_name} is not a string: {type(name)}")
        return

    name = name.strip()
    if not name:
        print(f"[ERROR] {field_name} is empty or contains only whitespace")
        return

    words = [w.strip() for w in name.split() if w.strip()]
    word_count = len(words)
    if word_count < 2:
        print(f"[ERROR] {field_name} has only {word_count} word(s), need at least 2")
        print(f"  Original name: '{name}'")
        print(f"  Words: {words}")
        return

    first_name_parts = words[:-1]
    first_name = " ".join(first_name_parts)
    last_name = words[-1]

    if not first_name or not first_name.strip():
        print(f"[ERROR] {field_name} - First Name is EMPTY after parsing!")
        print(f"  Original name: '{name}'")
        print(f"  Word count: {word_count}")
        print(f"  Words: {words}")
        print(f"  First Name parts: {first_name_parts}")
        print(f"  First Name (joined): '{first_name}'")
        print(f"  Last Name: '{last_name}'")
        print("  [CRITICAL] This indicates a parsing error - First Name should not be empty!")
        return

    first_name_len = len(first_name)
    last_name_len = len(last_name)

    print(f"[DEBUG] {field_name} validation:")
    print(f"  Original name: '{name}'")
    print(f"  Word count: {word_count}")
    print(f"  Words: {words}")
    print(f"  First Name: '{first_name}' (length: {first_name_len})")
    print(f"  Last Name: '{last_name}' (length: {last_name_len})")

    if first_name_len < 1:
        print(f"  [ERROR] First Name is too short (length: {first_name_len}, need >= 1)")
        print("  [CRITICAL] First Name must have at least 1 character!")

    if last_name_len < 2:
        print(f"  [ERROR] Last Name is too short (length: {last_name_len}, need >= 2)")
        print("  [CRITICAL] Last Name must have at least 2 characters!")

    try:
        if re.search(r"[^\w\s\-\'\.]", name, flags=re.UNICODE):
            print("  [WARNING] Name contains special characters (excluding Unicode letters)")
    except Exception:
        if re.search(r"[^\w\s\-\'\.]", name):
            print("  [WARNING] Name contains special characters")

    if "  " in name:
        print("  [WARNING] Name contains multiple consecutive spaces")

    if first_name_len >= 1 and last_name_len >= 2:
        print(f"  [OK] Name format is valid: First Name='{first_name}', Last Name='{last_name}'")
    else:
        print("  [ERROR] Name format is INVALID!")
        if first_name_len < 1:
            print("    - First Name is empty or too short")
        if last_name_len < 2:
            print("    - Last Name is too short")


def clean_coverage_amount(value: str) -> str:
    if value is None:
        return value

    if not isinstance(value, str):
        value = str(value)

    original_value = value
    value = value.strip()

    special_values = ["Standard", "Inc.", "Included", "N/A"]
    if re.search(r"\d+\s*(Months?|Days?|Years?)", value, re.IGNORECASE):
        return value
    if any(value.upper() == sv.upper() for sv in special_values):
        return value

    zero_patterns = [
        r"^no\s+deductible$",
        r"^\$0\s*ded\.?$",
        r"^0\s*ded\.?$",
        r"^\$0$",
        r"^0$",
    ]
    for pattern in zero_patterns:
        if re.match(pattern, value, re.IGNORECASE):
            return "0"

    value = value.replace("$", "")
    value = re.sub(r"\s*ded\.?\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*deductible\s*$", "", value, flags=re.IGNORECASE)
    value = value.strip()
    if not value:
        return "0"

    if value != original_value:
        print(f"[INFO] Cleaned coverage_amount: '{original_value}' -> '{value}'")
    return value
