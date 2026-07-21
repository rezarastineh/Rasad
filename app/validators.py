import re

# فقط حروف/عدد/خط‌تیره/نقطه و یک ستاره‌ی اختیاری در ابتدا (برای وایلدکارت) مجاز است.
# هر چیز دیگری (;, `, $, |, &, >, <, space, ...) رد می‌شود تا از Command Injection
# در دستوراتی که بعدا با subprocess(shell=True) اجرا می‌شوند جلوگیری شود.
_DOMAIN_RE = re.compile(r"^\*?\.?[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$")

_TARGET_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")


def is_valid_domain_entry(value: str) -> bool:
    """اعتبارسنجی یک خط اسکوپ (دامنه‌ی عادی یا وایلدکارت مثل *.example.com)."""
    value = value.strip()
    if not value or len(value) > 253:
        return False
    return bool(_DOMAIN_RE.match(value))


def is_valid_target_name(value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    return bool(_TARGET_NAME_RE.match(value))
