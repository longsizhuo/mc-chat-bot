"""三角洲行动战绩抓取库（社区逆向 API）。

不依赖第三方包，纯 stdlib 实现，方便后续直接嵌入 mc-chat-bot。
"""

from .client import DFClient, load_from_curl_file
from .endpoints import (
    fetch_records,
    fetch_all_pages,
    fetch_career,
    fetch_all_seasons,
    fetch_role_binding,
    fetch_daily_secret,
)
from .parsers import summarize_records, format_match
from .profile import format_profile, format_seasons
from .analytics import (
    breakdown_by_map,
    breakdown_by_operator,
    breakdown_by_hour,
    format_highlights,
    analyze_teammates,
    format_match_detail,
    format_recent_matches_detail,
    generate_advice,
)
from .maps import MAP_NAMES, OPERATOR_NAMES, ESCAPE_REASON

__all__ = [
    "DFClient",
    "load_from_curl_file",
    "fetch_records",
    "fetch_all_pages",
    "summarize_records",
    "format_match",
    "breakdown_by_map",
    "breakdown_by_operator",
    "breakdown_by_hour",
    "format_highlights",
    "analyze_teammates",
    "MAP_NAMES",
    "OPERATOR_NAMES",
    "ESCAPE_REASON",
]
