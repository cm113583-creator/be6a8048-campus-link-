from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from .extensions import db
from .models import (
    Booking,
    Category,
    Conversation,
    Dispute,
    Message,
    Notification,
    Offer,
    Payment,
    Review,
    Service,
    ServiceRequest,
    User,
    WalletTransaction,
)
from .reputation import refresh_provider_stats


def _fee(amount):
    return (Decimal(amount) * Decimal("0.05")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def seed_database(reset=False):
    if reset:
        db.drop_all()
    db.create_all()
    if User.query.count() and not reset:
        print("Database already contains data. Use --reset to rebuild.")
        return

    now = datetime.now()

    def at(days_offset, hour=9, minute=0):
        base = now + timedelta(days=days_offset)
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

    categories_data = [
        ("Tutoring", "tutoring", "One-to-one academic support and exam preparation", "bi-mortarboard", "#2563EB"),
        ("Assignment Help", "assignment-help", "Proofreading, editing, research and referencing", "bi-journal-check", "#7C3AED"),
        ("Cleaning & Laundry", "cleaning-laundry", "Laundry, room cleaning and hostel upkeep", "bi-basket2", "#0E9F6E"),
        ("Photography", "photography", "Portraits, graduations and campus events", "bi-camera", "#DB2777"),
        ("Graphic Design", "graphic-design", "Posters, logos, slides and social media kits", "bi-palette", "#EA580C"),
        ("Tech Support", "tech-support", "Laptop repairs, installations and data help", "bi-laptop", "#0891B2"),
        ("Delivery & Errands", "delivery-errands", "Campus deliveries, queueing and errands", "bi-scooter", "#CA8A04"),
        ("Event Support", "event-support", "Setup, décor, ushering and event assistance", "bi-calendar-event", "#4F46E5"),
        ("Other", "other", "Anything else the campus community needs", "bi-grid", "#64748B"),
    ]
    categories = {}
    for index, (name, slug, description, icon, color) in enumerate(categories_data):
        category = Category(
            name=name,
            slug=slug,
            description=description,
            icon=icon,
            color=color,
            sort_order=index,
        )
        db.session.add(category)
        categories[slug] = category

    def make_user(
        full_name,
        email,
        student_number,
        program,
        year,
        campus,
        bio,
        skills,
        verified=True,
        role="student",
        admin=False,
    ):
        user = User(
            full_name=full_name,
            email=email,
            student_number=student_number,
            phone=f"+260 97 {student_number.replace('-', '')[-6:]}",
            role=role,
            program=program,
            year_of_study=year,
            campus_area=campus,
            bio=bio,
            skills=skills,
            is_verified=verified,
            created_at=at(-120, 9),
        )
        user.set_password("Admin@12345" if admin else "Demo@123")
        db.session.add(user)
        return user

    admin = make_user(
        "Thandiwe Banda",
        "admin@campuslink.zm",
        "STAFF-001",
        "Other programme",
        "Postgraduate",
        "Main Campus",
        "Platform administrator at CampusLink.",
        "Trust and safety, marketplace operations",
        verified=True,
        role="admin",
        admin=True,
    )

    chama = make_user(
        "Chama Mwelwa",
        "chama@student.cavendish.ac.zm",
        "113-583",
        "Bachelor of Science in Computing",
        "Year 3",
        "Main Campus",
        "Final-year project student who books tutoring, photography and the occasional laundry run.",
        "Python, research, badminton",
    )
    zondiwe = make_user(
        "Zondiwe Chirwa",
        "zondiwe@student.cavendish.ac.zm",
        "112-214",
        "Bachelor of Business Administration",
        "Year 2",
        "Great East Road",
        "Student entrepreneur running a small snack business between lectures.",
        "Marketing, Canva, sales",
    )
    kelvin = make_user(
        "Kelvin Mulenga",
        "kelvin@student.cavendish.ac.zm",
        "111-874",
        "Bachelor of Science in Computing",
        "Year 4",
        "City Campus",
        "Computing student preparing for end-of-semester exams.",
        "Java, databases",
        verified=False,
    )
    naomi = make_user(
        "Naomi Chanda",
        "naomi@student.cavendish.ac.zm",
        "114-022",
        "Bachelor of Science in Nursing",
        "Year 2",
        "Ridgeway",
        "Nursing student balancing clinical placements with a busy hostel schedule.",
        "First aid, note-taking",
    )
    bwalya = make_user(
        "Bwalya Mwansa",
        "bwalya@student.cavendish.ac.zm",
        "113-901",
        "Bachelor of Law",
        "Year 3",
        "Main Campus",
        "Law student and moot court enthusiast.",
        "Legal research, debate",
    )

    luyando = make_user(
        "Luyando Phiri",
        "luyando@student.cavendish.ac.zm",
        "110-441",
        "Bachelor of Science in Computing",
        "Year 4",
        "Main Campus",
        "Self-taught designer helping student clubs and small businesses look sharp. I deliver editable files and two rounds of revisions.",
        "Figma, Illustrator, branding, social media",
    )
    natasha = make_user(
        "Natasha Zulu",
        "natasha@student.cavendish.ac.zm",
        "109-332",
        "Bachelor of Arts in Education",
        "Year 4",
        "Main Campus",
        "Mathematics tutor with three years of experience preparing students for exams. Patient, structured and practical.",
        "Mathematics, statistics, exam coaching",
    )
    kabwe = make_user(
        "Kabwe Chileshe",
        "kabwe@student.cavendish.ac.zm",
        "111-208",
        "Bachelor of Science in Computing",
        "Year 3",
        "Great East Road",
        "Photographer covering graduations, birthdays and campus events. Edited galleries delivered within 72 hours.",
        "Portrait photography, Lightroom, event coverage",
    )
    joseph = make_user(
        "Joseph Mumba",
        "joseph@student.cavendish.ac.zm",
        "112-566",
        "Bachelor of Science in Computing",
        "Year 2",
        "City Campus",
        "Laptop technician working out of the City Campus lab. Honest diagnostics before any repair.",
        "Hardware repair, Windows, data recovery",
    )
    grace = make_user(
        "Grace Tembo",
        "grace@student.cavendish.ac.zm",
        "110-775",
        "Bachelor of Business Administration",
        "Year 4",
        "Matero",
        "Reliable laundry and hostel cleaning service with same-day pickup around Main Campus.",
        "Laundry, deep cleaning, organisation",
    )
    emmanuel = make_user(
        "Emmanuel Sakala",
        "emmanuel@student.cavendish.ac.zm",
        "113-118",
        "Bachelor of Business Administration",
        "Year 2",
        "Great East Road",
        "Fast campus runner. Documents, food, printing and errands handled while you study.",
        "Delivery, queueing, local errands",
    )
    chisomo = make_user(
        "Chisomo Nyirenda",
        "chisomo@student.cavendish.ac.zm",
        "111-650",
        "Bachelor of Mass Communication",
        "Year 3",
        "Main Campus",
        "Journalism student offering careful proofreading, structure feedback and APA referencing checks.",
        "Proofreading, APA, research, editing",
        verified=False,
    )
    taonga = make_user(
        "Taonga Siame",
        "taonga@student.cavendish.ac.zm",
        "112-903",
        "Bachelor of Business Administration",
        "Year 3",
        "Kabulonga",
        "Event assistant for student societies: setup, décor, sound checks and ushering.",
        "Event setup, décor, ushering",
    )

    providers = [luyando, natasha, kabwe, joseph, grace, emmanuel, chisomo, taonga]
    seekers = [chama, zondiwe, kelvin, naomi, bwalya]
    db.session.flush()

    services = {}

    def make_service(
        key,
        provider,
        category,
        title,
        description,
        price,
        unit,
        duration,
        area,
        days="0,1,2,3,4",
        start="08:00",
        end="18:00",
        status="active",
        created_days=-60,
    ):
        service = Service(
            provider_id=provider.id,
            category_id=category.id,
            title=title,
            description=description,
            price=Decimal(price),
            price_unit=unit,
            duration_minutes=duration,
            campus_area=area,
            available_days=days,
            available_from=start,
            available_to=end,
            status=status,
            created_at=at(created_days, 10),
            updated_at=at(created_days, 10),
        )
        db.session.add(service)
        services[key] = service

    make_service(
        "poster",
        luyando,
        categories["graphic-design"],
        "Event poster & social media kit",
        "A scroll-stopping poster plus three matched social media sizes for your society event, party or launch. "
        "Includes two revision rounds, print-ready PDF and editable Figma source files.",
        "450.00",
        "per task",
        120,
        "Main Campus",
        "0,1,2,3,4",
        "09:00",
        "18:00",
    )
    make_service(
        "logo",
        luyando,
        categories["graphic-design"],
        "Logo design for student businesses",
        "A clean, memorable logo for your side hustle, society or final-year venture. "
        "You get primary and secondary lockups, colour and monochrome versions, and a short brand guide.",
        "800.00",
        "per task",
        240,
        "Main Campus",
        "0,1,2,3,4,5",
        "09:00",
        "17:00",
    )
    make_service(
        "maths",
        natasha,
        categories["tutoring"],
        "Mathematics & statistics tutoring",
        "One-to-one sessions tailored to your course outline. We work through past papers, "
        "fix shaky foundations and build a revision plan you can actually follow.",
        "120.00",
        "per hour",
        60,
        "Main Campus",
        "0,1,2,3,4,5",
        "08:00",
        "19:00",
    )
    make_service(
        "revision",
        natasha,
        categories["tutoring"],
        "Exam revision crash course",
        "A focused 90-minute revision session for statistics or calculus. Bring your syllabus and past papers; "
        "we prioritise the topics that carry the most marks.",
        "100.00",
        "per hour",
        90,
        "Main Campus",
        "0,1,2,3,4",
        "08:00",
        "19:00",
    )
    make_service(
        "graduation",
        kabwe,
        categories["photography"],
        "Graduation & event photography",
        "Two hours of coverage for graduations, birthdays and society events. "
        "You receive 40+ edited high-resolution photos in a private online gallery within 72 hours.",
        "600.00",
        "per session",
        120,
        "Great East Road",
        "4,5,6",
        "09:00",
        "19:00",
    )
    make_service(
        "portrait",
        kabwe,
        categories["photography"],
        "Portrait shoot on campus",
        "A relaxed one-hour portrait session at a campus location of your choice. "
        "Includes 10 retouched images for LinkedIn, graduation announcements or social media.",
        "250.00",
        "per session",
        60,
        "Great East Road",
        "0,1,2,3,4,5,6",
        "08:00",
        "18:00",
    )
    make_service(
        "laptop",
        joseph,
        categories["tech-support"],
        "Laptop diagnostics & repair",
        "Slow, overheating or not starting? I run a full diagnostic, explain the options and only proceed after you approve. "
        "Common fixes include cleaning, RAM/SSD upgrades and Windows repair.",
        "250.00",
        "per task",
        90,
        "City Campus",
        "0,1,2,3,4",
        "08:00",
        "17:00",
    )
    make_service(
        "software",
        joseph,
        categories["tech-support"],
        "Software setup & data recovery",
        "Clean Windows or Linux installation, essential software setup, virus cleanup, and safe backup or recovery of files. "
        "Bring your own licence keys where required.",
        "180.00",
        "per task",
        60,
        "City Campus",
        "0,1,2,3,4,5",
        "08:00",
        "18:00",
    )
    make_service(
        "laundry",
        grace,
        categories["cleaning-laundry"],
        "Laundry wash, dry & fold",
        "Pickup from your hostel, wash, dry, fold and return within 24 hours. "
        "Price covers one standard load; delicates handled by arrangement.",
        "80.00",
        "per task",
        60,
        "Matero",
        "0,1,2,3,4,5,6",
        "07:00",
        "19:00",
    )
    make_service(
        "room-clean",
        grace,
        categories["cleaning-laundry"],
        "Hostel room deep clean",
        "A top-to-bottom reset of your room: floors, windows, bathroom, wardrobe and desk. "
        "Bring your own preferred products or use mine at no extra cost.",
        "150.00",
        "per task",
        180,
        "Matero",
        "5,6",
        "08:00",
        "17:00",
    )
    make_service(
        "weekly-clean",
        grace,
        categories["cleaning-laundry"],
        "Weekly room cleaning plan",
        "A weekly tidy-up and clean for busy students. Includes floor, bathroom and desk, "
        "plus a monthly deep clean. Pause any week with 24 hours' notice.",
        "400.00",
        "per task",
        120,
        "Matero",
        "0,1,2,3,4",
        "08:00",
        "16:00",
        status="paused",
        created_days=-30,
    )
    make_service(
        "delivery",
        emmanuel,
        categories["delivery-errands"],
        "Campus delivery within 2 hours",
        "Need food, printing, a charger or documents moved across campus? "
        "I pick up and deliver within two hours. Live updates by message.",
        "40.00",
        "per task",
        60,
        "Great East Road",
        "0,1,2,3,4,5,6",
        "08:00",
        "20:00",
    )
    make_service(
        "errands",
        emmanuel,
        categories["delivery-errands"],
        "Queue & errand runs",
        "Skip the queue at the bank, registrar or pharmacy. I handle queueing and errands by the hour, "
        "with photo confirmation of every receipt and document.",
        "70.00",
        "per hour",
        60,
        "Great East Road",
        "0,1,2,3,4,5",
        "08:00",
        "18:00",
    )
    make_service(
        "proofreading",
        chisomo,
        categories["assignment-help"],
        "Proofreading & referencing",
        "Careful proofreading for grammar, clarity and flow, plus APA or Harvard referencing checks. "
        "I work in Word with tracked changes so you can see every edit.",
        "90.00",
        "per task",
        120,
        "Main Campus",
        "0,1,2,3,4",
        "09:00",
        "18:00",
        created_days=-20,
    )
    make_service(
        "research",
        chisomo,
        categories["assignment-help"],
        "Research assistance & formatting",
        "Help finding credible sources, organising your literature review and formatting your document. "
        "Guidance only — you keep authorship and final writing.",
        "150.00",
        "per hour",
        60,
        "Main Campus",
        "0,1,2,3,4",
        "09:00",
        "17:00",
        created_days=-20,
    )
    make_service(
        "event-setup",
        taonga,
        categories["event-support"],
        "Event setup, décor & ushering",
        "Setup and pack-down for student society events: chairs, table styling, simple décor, signage and ushering. "
        "Price covers a three-hour session within Lusaka.",
        "350.00",
        "per session",
        180,
        "Kabulonga",
        "4,5,6",
        "10:00",
        "20:00",
        created_days=-80,
    )

    request_one = ServiceRequest(
        seeker_id=zondiwe.id,
        category_id=categories["photography"].id,
        title="Photographer for a 21st birthday shoot",
        description="I am planning a small 21st birthday celebration at a lodge on Great East Road and need someone "
        "to take portraits and candid photos for about two hours. I would like around 25 edited photos.",
        budget=Decimal("400.00"),
        campus_area="Great East Road",
        needed_by=(now + timedelta(days=14)).date(),
        status="open",
        created_at=at(-2, 11),
    )
    request_two = ServiceRequest(
        seeker_id=kelvin.id,
        category_id=categories["tutoring"].id,
        title="Statistics tutor before end-of-semester exams",
        description="Looking for a patient tutor to help me prepare for an intro statistics exam. "
        "I need help with probability, hypothesis testing and interpreting SPSS output. Two or three sessions would be ideal.",
        budget=Decimal("300.00"),
        campus_area="Main Campus",
        needed_by=(now + timedelta(days=10)).date(),
        status="open",
        created_at=at(-1, 15),
    )
    request_three = ServiceRequest(
        seeker_id=naomi.id,
        category_id=categories["delivery-errands"].id,
        title="Help moving boxes to a new hostel room",
        description="I am moving from Ridgeway to a hostel nearer campus and need help moving about six boxes and a small fridge. "
        "The job should take about two hours if we use a trolley.",
        budget=Decimal("200.00"),
        campus_area="Ridgeway",
        needed_by=(now + timedelta(days=5)).date(),
        status="open",
        created_at=now - timedelta(hours=2),
    )
    request_four = ServiceRequest(
        seeker_id=zondiwe.id,
        category_id=categories["assignment-help"].id,
        title="Proofreading for a literature review",
        description="I need help checking the grammar, flow and APA referencing in a 12-page literature review "
        "before I submit it on Friday. The content is finished; I just need a careful edit.",
        budget=Decimal("100.00"),
        campus_area="Main Campus",
        needed_by=(now + timedelta(days=-1)).date(),
        status="awarded",
        created_at=at(-6, 10),
    )
    db.session.add_all([request_one, request_two, request_three, request_four])
    db.session.flush()

    offer_one = Offer(
        request_id=request_one.id,
        provider_id=kabwe.id,
        price=Decimal("450.00"),
        proposed_at=at(10, 14),
        duration_minutes=120,
        message="I shoot birthday events around campus most weekends and can cover the full two hours, "
        "including group portraits. My price covers 30 edited photos and travel to the lodge.",
        status="pending",
        created_at=at(-1, 9),
    )
    offer_four = Offer(
        request_id=request_four.id,
        provider_id=chisomo.id,
        price=Decimal("90.00"),
        proposed_at=at(-1, 9),
        duration_minutes=120,
        message="I can do a careful tracked-changes edit and check your APA references. I will return the document within 24 hours.",
        status="accepted",
        created_at=at(-5, 12),
    )
    db.session.add_all([offer_one, offer_four])
    db.session.flush()

    booking_specs = [
        {
            "key": "b1",
            "seeker": chama,
            "provider": natasha,
            "service": services["maths"],
            "title": "Statistics tutoring — hypothesis testing",
            "description": "I need help with hypothesis testing and regression before my stats exam.",
            "price": "240.00",
            "scheduled": at(-24, 10),
            "duration": 120,
            "status": "completed",
            "review": (5, 5, 5, "Natasha explained hypothesis testing in a way that finally made sense. "
                                 "She brought past papers and left me with a clear revision plan."),
        },
        {
            "key": "b2",
            "seeker": zondiwe,
            "provider": luyando,
            "service": services["logo"],
            "title": "Logo for my snack business",
            "description": "I need a friendly logo for my campus snack delivery brand, with a version for Instagram.",
            "price": "800.00",
            "scheduled": at(-40, 14),
            "duration": 120,
            "status": "completed",
            "review": (5, 4, 5, "Understood the brief immediately and gave me two strong directions. "
                                 "Delivery was one day later than planned but the files were perfect."),
        },
        {
            "key": "b3",
            "seeker": kelvin,
            "provider": joseph,
            "service": services["laptop"],
            "title": "Laptop diagnostics & SSD upgrade",
            "description": "Laptop is very slow and sometimes overheats during labs. Please diagnose and advise.",
            "price": "250.00",
            "scheduled": at(-12, 11),
            "duration": 90,
            "status": "completed",
            "review": (5, 5, 5, "Joseph explained the problem before touching anything and showed me the old drive. "
                                 "The laptop feels brand new."),
        },
        {
            "key": "b4",
            "seeker": naomi,
            "provider": grace,
            "service": services["laundry"],
            "title": "Laundry wash, dry & fold",
            "description": "Two weeks of hostel laundry, mostly uniforms and light clothing.",
            "price": "80.00",
            "scheduled": at(-18, 9),
            "duration": 60,
            "status": "completed",
            "review": (4, 5, 5, "Clothes came back clean, folded and on time. Pickup was easy to arrange."),
        },
        {
            "key": "b5",
            "seeker": bwalya,
            "provider": kabwe,
            "service": services["graduation"],
            "title": "Graduation photo coverage",
            "description": "Family graduation photos at the Great East Road campus, including group shots.",
            "price": "600.00",
            "scheduled": at(-65, 14),
            "duration": 120,
            "status": "completed",
            "review": (5, 5, 4, "Photos were beautiful and the gallery arrived quickly. I would have liked more group shots, "
                                 "but overall a great experience."),
        },
        {
            "key": "b6",
            "seeker": chama,
            "provider": emmanuel,
            "service": services["delivery"],
            "title": "Printing pickup and delivery",
            "description": "Collect two printed project drafts from the library and deliver them to the hostel.",
            "price": "40.00",
            "scheduled": at(-7, 12),
            "duration": 60,
            "status": "completed",
            "review": None,
        },
        {
            "key": "b7",
            "seeker": zondiwe,
            "provider": chisomo,
            "service": services["proofreading"],
            "title": "Proofreading for a marketing report",
            "description": "Check grammar, flow and Harvard references in a 10-page marketing report.",
            "price": "90.00",
            "scheduled": at(-33, 10),
            "duration": 120,
            "status": "completed",
            "review": (4, 4, 5, "Very thorough with references and the tracked changes were easy to review. "
                                 "A little tight on the deadline."),
        },
        {
            "key": "b8",
            "seeker": naomi,
            "provider": taonga,
            "service": services["event-setup"],
            "title": "Nursing society welcome event setup",
            "description": "Help set up chairs, décor and the registration table for a society welcome event.",
            "price": "350.00",
            "scheduled": at(-50, 16),
            "duration": 180,
            "status": "completed",
            "review": (5, 4, 5, "Taonga arrived early, kept the setup calm and stayed to pack down. "
                                 "Would book again for society events."),
        },
        {
            "key": "b9",
            "seeker": kelvin,
            "provider": natasha,
            "service": services["revision"],
            "title": "Exam revision crash course",
            "description": "Revise calculus and probability using past exam papers.",
            "price": "150.00",
            "scheduled": at(-70, 9),
            "duration": 90,
            "status": "completed",
            "review": (5, 5, 4, "We covered more than I expected in 90 minutes. The revision sheet was especially useful."),
        },
        {
            "key": "b10",
            "seeker": bwalya,
            "provider": luyando,
            "service": services["poster"],
            "title": "Moot court event poster",
            "description": "A formal poster and matching Instagram post for a moot court final.",
            "price": "450.00",
            "scheduled": at(-90, 13),
            "duration": 120,
            "status": "completed",
            "review": (4, 4, 4, "The design was clean and professional. A couple of small text changes took a while, "
                                 "but the final files were good."),
        },
        {
            "key": "b11",
            "seeker": bwalya,
            "provider": grace,
            "service": services["room-clean"],
            "title": "Hostel room deep clean",
            "description": "Deep clean of a hostel room before family visiting weekend, including windows and bathroom.",
            "price": "150.00",
            "scheduled": at(-5, 11),
            "duration": 180,
            "status": "disputed",
            "review": None,
        },
        {
            "key": "b12",
            "seeker": chama,
            "provider": kabwe,
            "service": services["portrait"],
            "title": "LinkedIn portrait shoot",
            "description": "One-hour portrait session near the library for a graduation announcement and LinkedIn profile.",
            "price": "250.00",
            "scheduled": at(2, 10),
            "duration": 60,
            "status": "in_escrow",
            "review": None,
            "paid": at(-1, 9),
        },
        {
            "key": "b13",
            "seeker": zondiwe,
            "provider": chisomo,
            "service": services["proofreading"],
            "title": "Proofreading for a literature review",
            "description": "Careful edit of grammar, flow and APA references in a 12-page literature review.",
            "price": "90.00",
            "scheduled": at(-1, 9),
            "duration": 120,
            "status": "delivered",
            "review": None,
            "paid": at(-2, 9),
            "delivered": now - timedelta(hours=3),
            "request": request_four,
            "offer": offer_four,
        },
        {
            "key": "b14",
            "seeker": kelvin,
            "provider": luyando,
            "service": services["poster"],
            "title": "Computing society hackathon poster",
            "description": "A bold poster and social kit for a weekend hackathon, including sponsor logos.",
            "price": "450.00",
            "scheduled": at(5, 14),
            "duration": 120,
            "status": "pending",
            "review": None,
        },
        {
            "key": "b15",
            "seeker": naomi,
            "provider": natasha,
            "service": services["revision"],
            "title": "Nursing statistics revision",
            "description": "A 90-minute revision session on statistics for nursing research.",
            "price": "100.00",
            "scheduled": at(3, 11),
            "duration": 90,
            "status": "accepted",
            "review": None,
        },
        {
            "key": "b16",
            "seeker": bwalya,
            "provider": joseph,
            "service": services["software"],
            "title": "Windows setup & file recovery",
            "description": "Reinstall Windows and recover notes from a failing drive before exams.",
            "price": "250.00",
            "scheduled": at(-1, 9),
            "duration": 60,
            "status": "in_escrow",
            "review": None,
            "paid": at(-2, 15),
        },
    ]

    bookings = {}
    for spec in booking_specs:
        scheduled = spec["scheduled"]
        status = spec["status"]
        paid_at = spec.get("paid")
        delivered_at = spec.get("delivered")
        completed_at = None
        if status == "completed":
            paid_at = scheduled - timedelta(days=1)
            completed_at = scheduled + timedelta(minutes=spec["duration"] + 120)
            delivered_at = completed_at - timedelta(hours=1)
        if status == "disputed":
            paid_at = scheduled - timedelta(days=1)
        created_at = min(scheduled - timedelta(days=3), now - timedelta(days=2))
        accepted_at = created_at + timedelta(hours=4) if status != "pending" else None
        booking = Booking(
            seeker_id=spec["seeker"].id,
            provider_id=spec["provider"].id,
            service_id=spec["service"].id,
            category_id=spec["service"].category_id,
            request_id=spec.get("request").id if spec.get("request") else None,
            offer_id=spec.get("offer").id if spec.get("offer") else None,
            title=spec["title"],
            description=spec["description"],
            price=Decimal(spec["price"]),
            scheduled_at=scheduled,
            duration_minutes=spec["duration"],
            location=spec["service"].campus_area,
            status=status,
            created_at=created_at,
            accepted_at=accepted_at,
            paid_at=paid_at,
            delivered_at=delivered_at,
            completed_at=completed_at,
        )
        db.session.add(booking)
        bookings[spec["key"]] = booking

    db.session.flush()
    for booking in bookings.values():
        if not booking.reference:
            booking.reference = f"CML-{now.year}-{booking.id:05d}"

    review_specs = [spec for spec in booking_specs if spec.get("review")]
    for spec in review_specs:
        booking = bookings[spec["key"]]
        quality, timeliness, communication, comment = spec["review"]
        review = Review(
            booking_id=booking.id,
            author_id=booking.seeker_id,
            provider_id=booking.provider_id,
            quality=quality,
            timeliness=timeliness,
            communication=communication,
            comment=comment,
            created_at=booking.completed_at + timedelta(days=1),
        )
        db.session.add(review)

    dispute = Dispute(
        booking_id=bookings["b11"].id,
        opened_by_id=bwalya.id,
        reason="Service not completed as described",
        details="The bathroom and windows were not cleaned and the visit ended early. "
        "I asked for a partial refund but we could not agree, so I am asking the platform to review.",
        status="open",
        created_at=at(-2, 10),
    )
    db.session.add(dispute)

    topups = {
        chama: Decimal("1500.00"),
        zondiwe: Decimal("1200.00"),
        kelvin: Decimal("1000.00"),
        naomi: Decimal("800.00"),
        bwalya: Decimal("2200.00"),
    }
    financial_events = []
    for user, amount in topups.items():
        financial_events.append(
            (at(-110, 8), 0, user, amount, "top_up", "Demo wallet top-up", None)
        )

    for spec in booking_specs:
        booking = bookings[spec["key"]]
        amount = Decimal(spec["price"])
        if booking.paid_at:
            financial_events.append(
                (
                    booking.paid_at,
                    1,
                    booking.seeker,
                    -amount,
                    "escrow_hold",
                    f"Escrow hold for {booking.reference} · {booking.title}",
                    booking.id,
                )
            )
            fee = _fee(amount)
            payment_status = "held"
            released_at = None
            if spec["status"] == "completed":
                payment_status = "released"
                released_at = booking.completed_at + timedelta(minutes=30)
                financial_events.append(
                    (
                        released_at,
                        2,
                        booking.provider,
                        amount - fee,
                        "escrow_release",
                        f"Earnings for {booking.reference} · {booking.title}",
                        booking.id,
                    )
                )
            payment = Payment(
                booking_id=booking.id,
                amount=amount,
                platform_fee=fee,
                provider_amount=amount - fee,
                status=payment_status,
                created_at=booking.paid_at,
                released_at=released_at,
            )
            db.session.add(payment)

    financial_events.sort(key=lambda event: (event[0], event[1]))
    for when, _priority, user, amount, kind, description, booking_id in financial_events:
        user.wallet_balance = Decimal(user.wallet_balance or 0) + Decimal(amount)
        entry = WalletTransaction(
            user_id=user.id,
            amount=Decimal(amount),
            balance_after=user.wallet_balance,
            kind=kind,
            description=description,
            booking_id=booking_id,
            created_at=when,
        )
        db.session.add(entry)

    conversation_one = Conversation(
        user_a_id=min(chama.id, kabwe.id),
        user_b_id=max(chama.id, kabwe.id),
        created_at=at(-2, 12),
        last_message_at=at(-1, 16),
    )
    conversation_two = Conversation(
        user_a_id=min(chama.id, natasha.id),
        user_b_id=max(chama.id, natasha.id),
        created_at=at(-26, 9),
        last_message_at=at(-25, 10),
    )
    conversation_three = Conversation(
        user_a_id=min(zondiwe.id, chisomo.id),
        user_b_id=max(zondiwe.id, chisomo.id),
        created_at=at(-3, 14),
        last_message_at=now - timedelta(hours=1),
    )
    conversation_four = Conversation(
        user_a_id=min(bwalya.id, grace.id),
        user_b_id=max(bwalya.id, grace.id),
        created_at=at(-5, 15),
        last_message_at=at(-3, 11),
    )
    db.session.add_all([conversation_one, conversation_two, conversation_three, conversation_four])
    db.session.flush()

    messages = [
        Message(
            conversation_id=conversation_one.id,
            sender_id=chama.id,
            body="Hi Kabwe, I have paid for the portrait session on Thursday at 10:00. Is the library steps still a good meeting point?",
            is_read=True,
            created_at=at(-2, 12),
        ),
        Message(
            conversation_id=conversation_one.id,
            sender_id=kabwe.id,
            body="Hi Chama! Yes, library steps works. Wear something comfortable — we will shoot near the trees and by the main entrance. I will be there by 09:50.",
            is_read=False,
            created_at=at(-1, 16),
        ),
        Message(
            conversation_id=conversation_two.id,
            sender_id=chama.id,
            body="Thank you for the session yesterday. Could you send the revision sheet you mentioned?",
            is_read=True,
            created_at=at(-25, 9),
        ),
        Message(
            conversation_id=conversation_two.id,
            sender_id=natasha.id,
            body="Of course — I have attached it to your booking notes. Good luck with the exam and message me if a topic still feels unclear.",
            is_read=True,
            created_at=at(-25, 10),
        ),
        Message(
            conversation_id=conversation_three.id,
            sender_id=chisomo.id,
            body="Your literature review is edited and back in your inbox. I flagged three references that need page numbers in APA.",
            is_read=False,
            created_at=now - timedelta(hours=1),
        ),
        Message(
            conversation_id=conversation_four.id,
            sender_id=bwalya.id,
            body="I have opened a dispute because the deep clean did not cover the bathroom and windows we agreed on.",
            is_read=True,
            created_at=at(-3, 10),
        ),
        Message(
            conversation_id=conversation_four.id,
            sender_id=grace.id,
            body="I am sorry you feel that way. I was only booked for three hours and I did explain that the bathroom would need a second visit.",
            is_read=False,
            created_at=at(-3, 11),
        ),
    ]
    db.session.add_all(messages)

    notifications = [
        Notification(
            user_id=chama.id,
            title="Portrait session coming up",
            body="Your portrait shoot with Kabwe is in 2 days. Payment is held safely in escrow.",
            link=f"/bookings/{bookings['b12'].id}",
            category="booking",
            is_read=False,
            created_at=now - timedelta(hours=2),
        ),
        Notification(
            user_id=chama.id,
            title="New message from Kabwe",
            body="Kabwe confirmed the meeting point for your portrait session.",
            link=f"/messages/{conversation_one.id}",
            category="message",
            is_read=False,
            created_at=at(-1, 16),
        ),
        Notification(
            user_id=chama.id,
            title="Payment held in escrow",
            body="K250.00 is held safely for CML portrait shoot. It will be released after you confirm completion.",
            link=f"/bookings/{bookings['b12'].id}",
            category="payment",
            is_read=True,
            created_at=at(-1, 9),
        ),
        Notification(
            user_id=zondiwe.id,
            title="Service delivered — please confirm",
            body="Chisomo marked your literature review proofreading as delivered. Confirm completion to release the escrowed payment.",
            link=f"/bookings/{bookings['b13'].id}",
            category="booking",
            is_read=False,
            created_at=now - timedelta(hours=2),
        ),
        Notification(
            user_id=zondiwe.id,
            title="New offer received",
            body="Kabwe offered K450.00 for your 21st birthday photography request.",
            link=f"/requests/{request_one.id}",
            category="request",
            is_read=False,
            created_at=at(-1, 9),
        ),
        Notification(
            user_id=luyando.id,
            title="New booking request",
            body="Kelvin requested an event poster and social kit for a hackathon.",
            link=f"/bookings/{bookings['b14'].id}",
            category="booking",
            is_read=False,
            created_at=at(-2, 15),
        ),
        Notification(
            user_id=kabwe.id,
            title="New message from Chama",
            body="Chama confirmed the portrait booking and asked about the meeting point.",
            link=f"/messages/{conversation_one.id}",
            category="message",
            is_read=False,
            created_at=at(-2, 12),
        ),
        Notification(
            user_id=admin.id,
            title="New dispute needs review",
            body="Bwalya Mwansa opened a dispute on CML room deep clean.",
            link="/admin/disputes",
            category="dispute",
            is_read=False,
            created_at=at(-2, 10),
        ),
        Notification(
            user_id=natasha.id,
            title="Booking accepted — waiting for payment",
            body="Naomi's revision session is confirmed. Payment will be held in escrow.",
            link=f"/bookings/{bookings['b15'].id}",
            category="booking",
            is_read=True,
            created_at=at(-1, 13),
        ),
    ]
    db.session.add_all(notifications)

    db.session.flush()
    for provider in providers:
        refresh_provider_stats(provider)
    db.session.commit()
    print("Seeded demo data:")
    print("  Admin:    admin@campuslink.zm / Admin@12345")
    print("  Seeker:   chama@student.cavendish.ac.zm / Demo@123")
    print("  Provider: luyando@student.cavendish.ac.zm / Demo@123")
    print("  Provider: natasha@student.cavendish.ac.zm / Demo@123")
