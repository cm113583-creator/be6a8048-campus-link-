from datetime import datetime, timedelta


def future_date(days=1):
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
