from datetime import datetime

import dateparser

ddp = dateparser.DateDataParser(
    languages=["de"],
    settings={
        "PREFER_DATES_FROM": "past",
        "PREFER_DAY_OF_MONTH": "first",
        "DATE_ORDER": "DMY",
        "RELATIVE_BASE": datetime.now(),
    },
)
