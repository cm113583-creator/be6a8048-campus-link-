APP_NAME = "CampusLink"
APP_TAGLINE = "Campus skills. Trusted trade."
PLATFORM_FEE_RATE = 0.05

CAMPUS_AREAS = [
    "Main Campus",
    "Great East Road",
    "City Campus",
    "Ridgeway",
    "Kabulonga",
    "Chilenje",
    "Matero",
    "Kabwata",
    "Other Lusaka area",
]

WEEKDAYS = [
    (0, "Monday", "Mon"),
    (1, "Tuesday", "Tue"),
    (2, "Wednesday", "Wed"),
    (3, "Thursday", "Thu"),
    (4, "Friday", "Fri"),
    (5, "Saturday", "Sat"),
    (6, "Sunday", "Sun"),
]

PRICE_UNITS = ["per hour", "per task", "per session", "per day"]

DURATION_OPTIONS = [
    (30, "30 minutes"),
    (60, "1 hour"),
    (90, "1 hour 30 minutes"),
    (120, "2 hours"),
    (180, "3 hours"),
    (240, "4 hours"),
]

PROGRAMS = [
    "Bachelor of Science in Computing",
    "Bachelor of Business Administration",
    "Bachelor of Accounting",
    "Bachelor of Law",
    "Bachelor of Medicine and Surgery",
    "Bachelor of Arts in Education",
    "Bachelor of Mass Communication",
    "Bachelor of Science in Nursing",
    "Other programme",
]

YEAR_OPTIONS = ["Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Postgraduate"]

BOOKING_STATUSES = {
    "pending": {"label": "Awaiting provider", "color": "warning"},
    "accepted": {"label": "Awaiting payment", "color": "info"},
    "in_escrow": {"label": "In progress", "color": "primary"},
    "delivered": {"label": "Awaiting confirmation", "color": "purple"},
    "completed": {"label": "Completed", "color": "success"},
    "declined": {"label": "Declined", "color": "secondary"},
    "cancelled": {"label": "Cancelled", "color": "secondary"},
    "disputed": {"label": "In dispute", "color": "danger"},
    "refunded": {"label": "Refunded", "color": "secondary"},
}

BOOKING_ACTIVE = ("pending", "accepted", "in_escrow", "delivered", "disputed")
BOOKING_BLOCKING = ("accepted", "in_escrow", "delivered", "disputed")

REQUEST_STATUSES = {
    "open": {"label": "Open", "color": "success"},
    "awarded": {"label": "Awarded", "color": "primary"},
    "closed": {"label": "Closed", "color": "secondary"},
    "cancelled": {"label": "Cancelled", "color": "secondary"},
}

OFFER_STATUSES = {
    "pending": {"label": "Pending", "color": "warning"},
    "accepted": {"label": "Accepted", "color": "success"},
    "declined": {"label": "Declined", "color": "secondary"},
    "withdrawn": {"label": "Withdrawn", "color": "secondary"},
}

SERVICE_STATUSES = {
    "active": {"label": "Live", "color": "success"},
    "paused": {"label": "Paused", "color": "secondary"},
    "suspended": {"label": "Suspended by admin", "color": "danger"},
}
