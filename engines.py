"""Structured guidance for the case-study checker.

This is a safety-rules engine. It does not diagnose disease and it does not
recommend medicine doses. Wording stays conditional on purpose.
"""

URGENCY_RANK = {"self_care": 0, "soon": 1, "urgent": 2, "emergency": 3}

URGENCY_META = {
    "emergency": {"label": "Emergency", "tone": "emergency"},
    "urgent": {"label": "Care today", "tone": "urgent"},
    "soon": {"label": "Arrange a review", "tone": "soon"},
    "self_care": {"label": "Home care for now", "tone": "self"},
}

SYMPTOMS = [
    ("fever", "Fever", "General"),
    ("chills", "Chills", "General"),
    ("fatigue", "Fatigue", "General"),
    ("appetite", "Loss of appetite", "General"),
    ("sweats", "Night sweats", "General"),
    ("headache", "Headache", "Head and nervous system"),
    ("dizziness", "Dizziness", "Head and nervous system"),
    ("confusion", "Confusion", "Head and nervous system"),
    ("fainting", "Fainting", "Head and nervous system"),
    ("vision", "Vision changes", "Head and nervous system"),
    ("cough", "Cough", "Chest and breathing"),
    ("sore_throat", "Sore throat", "Chest and breathing"),
    ("runny_nose", "Runny or blocked nose", "Chest and breathing"),
    ("breath", "Shortness of breath", "Chest and breathing"),
    ("wheeze", "Wheezing", "Chest and breathing"),
    ("chest", "Chest pain", "Chest and breathing"),
    ("nausea", "Nausea", "Stomach and digestion"),
    ("vomiting", "Vomiting", "Stomach and digestion"),
    ("diarrhea", "Diarrhea", "Stomach and digestion"),
    ("constipation", "Constipation", "Stomach and digestion"),
    ("abdomen", "Abdominal pain", "Stomach and digestion"),
    ("heartburn", "Heartburn", "Stomach and digestion"),
    ("joint", "Joint pain", "Muscles and joints"),
    ("muscle", "Muscle aches", "Muscles and joints"),
    ("back", "Back pain", "Muscles and joints"),
    ("neck", "Stiff neck", "Muscles and joints"),
    ("rash", "Rash", "Skin"),
    ("itch", "Itching", "Skin"),
    ("swelling", "Swelling", "Skin"),
    ("urination_pain", "Pain when urinating", "Urinary"),
    ("urination_freq", "Frequent urination", "Urinary"),
    ("low_mood", "Low mood", "Sleep and mood"),
    ("anxiety", "Anxiety", "Sleep and mood"),
    ("sleep", "Trouble sleeping", "Sleep and mood"),
]

SYMPTOM_IDS = {item[0] for item in SYMPTOMS}
SYMPTOM_LABELS = {item[0]: item[1] for item in SYMPTOMS}

DURATIONS = [
    ("under_24h", "Under 24 hours"),
    ("1_3_days", "1–3 days"),
    ("4_7_days", "4–7 days"),
    ("over_a_week", "More than a week"),
]
SEVERITIES = [
    ("mild", "Mild — I can carry on with most of the day"),
    ("moderate", "Moderate — it is hard to carry on as usual"),
    ("severe", "Severe — I need help with ordinary activities"),
]
AGE_GROUPS = [
    ("under_12", "Under 12"),
    ("teen", "12–17"),
    ("adult", "18–59"),
    ("older", "60 or older"),
]
PREGNANCY = [
    ("no", "No"),
    ("yes", "Yes"),
    ("unsure", "Not sure"),
]

GOALS = [
    ("general", "General wellness"),
    ("energy", "More daily energy"),
    ("sleep", "Better sleep"),
    ("weight", "A steadier weight"),
    ("heart", "Heart-healthy habits"),
    ("stress", "Less day-to-day stress"),
    ("recovery", "Recovering while unwell"),
]
ACTIVITIES = [
    ("sedentary", "Mostly sitting"),
    ("light", "Light movement a few days a week"),
    ("moderate", "Regular walks or similar activity"),
    ("active", "Hard exercise most days"),
]
DIETS = [
    ("mixed", "Mixed meals"),
    ("vegetarian", "Vegetarian"),
    ("low_appetite", "Little appetite right now"),
    ("salty", "I often eat salty or packaged food"),
]
SLEEP = [
    ("under_5", "Under 5 hours"),
    ("5_6", "5–6 hours"),
    ("7_9", "7–9 hours"),
    ("over_9", "More than 9 hours"),
]

CRISIS_TERMS = (
    "suicide",
    "suicidal",
    "kill myself",
    "end my life",
    "want to die",
    "self-harm",
    "self harm",
    "hurt myself",
)
EMERGENCY_TEXT = (
    "coughing blood",
    "coughing up blood",
    "vomiting blood",
    "vomit blood",
    "blood in stool",
    "heavy bleeding",
    "can't breathe",
    "cannot breathe",
    "unable to breathe",
    "face drooping",
    "slurred speech",
    "seizure",
    "throat closing",
    "swelling of the tongue",
)


def grouped_symptoms():
    groups = []
    index = {}
    for symptom_id, label, group in SYMPTOMS:
        if group not in index:
            index[group] = {"name": group, "items": []}
            groups.append(index[group])
        index[group]["items"].append({"id": symptom_id, "label": label})
    return groups


def label_for(options, value):
    for key, text in options:
        if key == value:
            return text
    return value


def _raise(current, minimum):
    if URGENCY_RANK[minimum] > URGENCY_RANK[current]:
        return minimum
    return current


def _has_term(text, terms):
    return any(term in text for term in terms)


def evaluate_symptoms(symptom_ids, duration, severity, age_group, pregnancy, notes):
    chosen = set(symptom_ids)
    text = (notes or "").lower()
    labels = [SYMPTOM_LABELS[item] for item in symptom_ids if item in SYMPTOM_LABELS]

    if _has_term(text, CRISIS_TERMS):
        guidance = {
            "associations": [],
            "steps": [
                "Call 112 (emergency) or 912 (ambulance) now.",
                "Go to the nearest emergency department if you can do that safely.",
                "Tell someone you trust, and stay with another person if possible.",
                "This application cannot provide crisis counseling or emergency treatment.",
            ],
            "lifestyle": [],
            "warnings": [
                "If you are having thoughts of suicide or self-harm, seek in-person help immediately.",
            ],
            "symptom_labels": labels,
            "duration_label": label_for(DURATIONS, duration),
            "severity_label": label_for(SEVERITIES, severity),
            "age_label": label_for(AGE_GROUPS, age_group),
        }
        return {
            "urgency": "emergency",
            "title": "Please get immediate help",
            "summary": (
                "What you wrote suggests you may be in crisis. This checker cannot keep you safe by itself. "
                "Contact emergency services now, or go to the nearest emergency department."
            ),
            "guidance": guidance,
        }

    urgency = "self_care"
    warnings = []
    extra_steps = []

    if _has_term(text, EMERGENCY_TEXT):
        urgency = "emergency"
        warnings.append("The extra detail you wrote includes a warning sign that needs emergency care.")
    if "fainting" in chosen or "confusion" in chosen:
        urgency = "emergency"
    if "swelling" in chosen and "breath" in chosen:
        urgency = "emergency"
    if "chest" in chosen and (severity == "severe" or "breath" in chosen or "fainting" in chosen):
        urgency = "emergency"
    elif "breath" in chosen and severity == "severe":
        urgency = "emergency"
    elif "chest" in chosen:
        urgency = _raise(urgency, "urgent")
    elif "breath" in chosen:
        urgency = _raise(urgency, "urgent")

    if "neck" in chosen and "fever" in chosen:
        urgency = _raise(urgency, "urgent")
        warnings.append(
            "A stiff neck together with fever should be assessed promptly. This checker cannot rule out a serious infection."
        )
    if severity == "severe":
        urgency = _raise(urgency, "urgent")
    if "abdomen" in chosen and severity == "severe":
        urgency = _raise(urgency, "urgent")
    elif "abdomen" in chosen:
        urgency = _raise(urgency, "soon")
    if "urination_pain" in chosen or ("urination_freq" in chosen and "fever" in chosen):
        urgency = _raise(urgency, "soon")
    if "vision" in chosen or "dizziness" in chosen or "wheeze" in chosen:
        urgency = _raise(urgency, "soon")
    if "dizziness" in chosen and severity == "severe":
        urgency = _raise(urgency, "urgent")
    if duration == "over_a_week" and ("fever" in chosen or "low_mood" in chosen or "cough" in chosen):
        urgency = _raise(urgency, "soon")

    associations = _associations(chosen)
    if not associations:
        associations.append(
            {
                "title": "No single common pattern",
                "detail": (
                    "The symptoms you selected do not line up with one everyday pattern in this checker. "
                    "That does not measure how serious they are. A clinician can sort through causes this tool cannot see."
                ),
            }
        )
        if urgency == "self_care" and severity != "mild":
            urgency = "soon"

    if age_group in ("under_12", "teen") and urgency == "self_care":
        urgency = "soon"
    if age_group == "under_12":
        warnings.append(
            "For a child, a parent or guardian should involve a clinician. Do not give adult medicines to a child."
        )
    elif age_group == "teen":
        warnings.append(
            "For anyone under 18, confirm the plan with a clinician, pharmacist, or guardian before using medicine."
        )
    if age_group == "older" and "fever" in chosen:
        urgency = _raise(urgency, "soon")
        warnings.append("Fever in an older adult is a reason to arrange a clinical review rather than wait it out alone.")
    if age_group != "under_12" and pregnancy in ("yes", "unsure"):
        urgency = _raise(urgency, "soon")
        warnings.append(
            "If you are pregnant or might be, ask a maternity clinician or pharmacist before taking any medicine."
        )

    if "headache" in chosen and urgency != "emergency":
        warnings.append(
            "Seek emergency care if this is the worst headache of your life, or it comes with confusion, fainting, weakness, or a stiff neck and fever."
        )
    if "chest" in chosen:
        warnings.append(
            "If chest pain spreads to the arm, jaw, or back, or you feel sweaty, sick, or short of breath, call 912."
        )

    steps = _steps(urgency) + extra_steps
    lifestyle = [] if urgency == "emergency" else _illness_lifestyle(chosen)
    title, summary = _headline(urgency, chosen)

    guidance = {
        "associations": associations[:3],
        "steps": steps,
        "lifestyle": lifestyle,
        "warnings": warnings,
        "symptom_labels": labels,
        "duration_label": label_for(DURATIONS, duration),
        "severity_label": label_for(SEVERITIES, severity),
        "age_label": label_for(AGE_GROUPS, age_group),
        "pregnancy_label": "Not asked for young children"
        if age_group == "under_12"
        else label_for(PREGNANCY, pregnancy),
    }
    return {"urgency": urgency, "title": title, "summary": summary, "guidance": guidance}


def _associations(chosen):
    found = []
    cold = {"cough", "sore_throat", "runny_nose"}
    if chosen & cold and "chest" not in chosen and "breath" not in chosen:
        found.append(
            {
                "title": "Common upper-respiratory illness",
                "detail": "Cough, sore throat, and a blocked nose often appear together with ordinary viral colds. Other causes are possible.",
            }
        )
    if "fever" in chosen and chosen & {"cough", "muscle", "fatigue", "chills"}:
        found.append(
            {
                "title": "Flu-like illness",
                "detail": "Fever with cough, chills, fatigue, or muscle aches can appear with influenza and with other infections. A test or exam is the way to tell them apart.",
            }
        )
    if chosen & {"diarrhea", "vomiting"} and chosen & {"nausea", "abdomen", "diarrhea", "vomiting"}:
        if "diarrhea" in chosen or "vomiting" in chosen:
            found.append(
                {
                    "title": "Stomach upset or gastroenteritis",
                    "detail": "Nausea, vomiting, or diarrhea often come from a short-lived stomach infection or something that disagreed with you. Persistent pain or blood needs an exam.",
                }
            )
    if "headache" in chosen and "confusion" not in chosen and "fainting" not in chosen:
        found.append(
            {
                "title": "Headache",
                "detail": "Many headaches relate to tension, too little sleep, dehydration, or a viral illness. A new or severe pattern still needs a clinician.",
            }
        )
    if chosen & {"urination_pain", "urination_freq"}:
        found.append(
            {
                "title": "Urinary irritation",
                "detail": "Pain or frequency can happen with a urine infection. This checker will not suggest antibiotics. A clinician should decide if treatment is needed.",
            }
        )
    if chosen & {"joint", "muscle", "back"} and not chosen & {"chest", "breath", "confusion"}:
        found.append(
            {
                "title": "Muscle or joint strain",
                "detail": "Aches can follow unfamiliar effort, a long day of sitting, or a viral illness. Pain after an injury, or pain with weakness, should be examined.",
            }
        )
    if chosen & {"rash", "itch"} and "breath" not in chosen:
        found.append(
            {
                "title": "Skin irritation",
                "detail": "Rashes have many causes, including heat, allergy, and infection. Spreading rash, rash with fever, or rash with breathing trouble needs prompt care.",
            }
        )
    if chosen & {"low_mood", "anxiety", "sleep"} and not chosen & {"chest", "confusion", "fainting"}:
        found.append(
            {
                "title": "Sleep and mood strain",
                "detail": "Short sleep, worry, and low mood often travel together. If this has lasted more than a week or is getting in the way of daily life, talk with a clinician or counsellor.",
            }
        )
    # Keep the list specific: drop weaker overlaps when stronger chest items exist.
    if "chest" in chosen:
        found.insert(
            0,
            {
                "title": "Chest symptoms need a person, not an app",
                "detail": "Chest pain has causes that range from muscle strain to heart and lung emergencies. Only an in-person assessment can tell the difference.",
            },
        )
    return found


def _headline(urgency, chosen):
    if urgency == "emergency":
        return (
            "Seek emergency care now",
            "This combination can be a medical emergency. This tool cannot tell you the cause. Call 912 or go to the nearest emergency department.",
        )
    if urgency == "urgent":
        return (
            "Get medical care today",
            "These symptoms should be assessed by a clinician today. If they suddenly worsen, treat that as an emergency.",
        )
    if urgency == "soon":
        return (
            "Arrange a clinical review",
            "Home care alone is not the right plan for what you entered. Book a review with a clinician, and go earlier if you get worse.",
        )
    if chosen & {"cough", "sore_throat", "runny_nose", "headache", "heartburn"}:
        return (
            "Home care may be reasonable for now",
            "This looks like a pattern many people manage at home for a short time. It is not a diagnosis. Seek care if you worsen, develop a warning sign, or are not improving.",
        )
    return (
        "Home care may be reasonable for now",
        "Nothing you entered raised an emergency rule in this checker. That is not a clean bill of health. Use the steps below and get a review if you are worried or not improving.",
    )


def _steps(urgency):
    if urgency == "emergency":
        return [
            "Call 912 for an ambulance or 112 for emergency help.",
            "Do not drive yourself if you feel faint, confused, or short of breath.",
            "Tell the clinician every symptom you selected, including when it started.",
        ]
    if urgency == "urgent":
        return [
            "Arrange same-day care at a hospital outpatient clinic, emergency unit, or another clinician.",
            "If breathing, pain, or alertness gets worse while you wait, call 912.",
            "Take a list of the symptoms and any medicines you already use.",
        ]
    if urgency == "soon":
        return [
            "Book a clinical review in the next day or two, sooner if you feel worse.",
            "Ask a pharmacist or clinician before starting a medicine, especially for a child or during pregnancy.",
            "Return to emergency care for chest pain, trouble breathing, fainting, confusion, or heavy bleeding.",
        ]
    return [
        "Rest, drink fluids, and notice whether you are getting better or worse over the next day.",
        "Ask a pharmacist or clinician before using medicine if you are pregnant, under 18, or living with a long-term condition.",
        "Seek care if symptoms last more than a week, become severe, or you develop trouble breathing, a stiff neck with fever, fainting, or confusion.",
    ]


def _illness_lifestyle(chosen):
    tips = [
        "Pause hard exercise while you have fever, chest pain, or shortness of breath.",
        "Wash your hands and cover coughs, especially around other people.",
    ]
    if chosen & {"diarrhea", "vomiting"}:
        tips.append(
            "Sip water often. If diarrhea is making you thirsty, use prepared oral rehydration salts and follow the packet."
        )
    if "appetite" in chosen or "nausea" in chosen:
        tips.append("Small, plain meals are enough until your appetite returns. There is no need to force a large plate.")
    else:
        tips.append("Keep regular meals with fruit, vegetables, and a protein food if you can eat comfortably.")
    if chosen & {"sleep", "low_mood", "anxiety", "fatigue"}:
        tips.append("Keep a steady wake-up time, and dim screens in the last hour before bed.")
    return tips[:4]


def build_lifestyle(goal, activity, diet, sleep_hours):
    nutrition = [
        "Build meals around vegetables, fruit, beans or another protein, and a staple such as rice, potatoes, or whole grains.",
        "Drink water through the day. Tea and coffee can count toward fluids, but let water be the main drink.",
    ]
    movement = [
        "Walking is enough to count. A brisk 10 to 30 minutes most days is a solid base.",
    ]
    rest = [
        "Keep a regular wake-up time, including on weekends, so sleep becomes easier to predict.",
    ]
    habits = [
        "If you smoke, cutting down is one of the highest-yield changes you can make. A clinician can help you plan it.",
        "Keep alcohol, if you drink, modest. Alcohol disrupts sleep and adds strain on the heart and liver.",
    ]
    cautions = [
        "This is general public-health guidance for a case study, not a personal diet or exercise prescription.",
        "If you are pregnant, under 18, recovering from surgery, or living with heart, kidney, or eating-disorder care, adapt this with your clinician.",
    ]

    if diet == "vegetarian":
        nutrition.append(
            "Beans, lentils, groundnuts, eggs, and dairy if you eat them cover protein. Pair leafy greens or beans with fruit rich in vitamin C at the same meal."
        )
    elif diet == "low_appetite":
        nutrition.append(
            "If appetite is low, eat smaller amounts more often. Soups, yoghurt, fruit, and eggs are easier than a heavy plate."
        )
    elif diet == "salty":
        nutrition.append(
            "Cook one more meal at home this week and taste food before adding salt. Packaged soups and snacks carry more salt than they taste."
        )
    else:
        nutrition.append("Fill half the plate with vegetables or fruit when you can. Keep fried food as the exception.")

    if activity == "sedentary":
        movement = [
            "Start with a 10-minute walk after a meal. Add minutes only when that feels ordinary.",
            "Stand and move for a few minutes each hour if your day is spent sitting.",
        ]
    elif activity == "light":
        movement.append("Add one extra walk this week, or a short session of stretching for the back and hips.")
    elif activity == "moderate":
        movement.append("Keep the routine you have. Include one easier day so joints and sleep can recover.")
    else:
        movement = [
            "Hard training most days needs an easier day in the week. Soreness that changes how you walk is a signal to rest that area.",
            "Replace one intense session with a walk if sleep has been short.",
        ]

    if sleep_hours == "under_5":
        rest = [
            "Under five hours most nights will blunt energy and mood. Protect a wind-down of 30 quiet minutes.",
            "Leave caffeine for the earlier part of the day.",
            "Treat the schedule as the project, not a single early night.",
        ]
    elif sleep_hours == "5_6":
        rest = [
            "Five or six hours is on the short side for most adults. Protect a wind-down of 30 quiet minutes.",
            "Leave caffeine for the earlier part of the day.",
        ]
    elif sleep_hours == "over_9":
        rest.append(
            "Sleeping much more than 9 hours and still waking unrefreshed is worth mentioning to a clinician, especially with low mood or snoring."
        )
    else:
        rest.append("Seven to nine hours is a healthy range for most adults. Keep the room dark and the phone out of the bed.")

    if goal == "energy":
        headline = "Energy comes from sleep, meals, and a little daily movement"
        intro = "Chasing energy with late caffeine usually costs the next night. These habits stack more gently."
        habits.append("Get daylight in the first half of the day. A short outdoor walk does more than another cup of coffee.")
    elif goal == "sleep":
        headline = "A steadier night starts in the evening, not at the pillow"
        intro = "The aim is a repeatable wind-down. One perfect night is less useful than a week of similar bedtimes."
        rest.append("If you cannot sleep after about 20 minutes, sit somewhere dim and quiet until you feel sleepy again.")
    elif goal == "weight":
        headline = "Steadier weight follows ordinary meals, not a crash plan"
        intro = "This checker will not set a calorie target. A plate you can repeat on a busy day beats a strict plan you abandon."
        nutrition.append("Serve food onto a plate and sit to eat it, rather than snacking from the packet while doing something else.")
        cautions.append("Rapid weight-loss plans, diet pills, and long fasts are not part of this advice.")
    elif goal == "heart":
        headline = "Heart-healthy habits are mostly kitchen and walking habits"
        intro = "Movement, less salt, not smoking, and a good night of sleep all move blood pressure and cholesterol in a kinder direction."
        movement.append("If walking already feels tight in the chest, stop and get that symptom checked before you push the pace.")
    elif goal == "stress":
        headline = "Lower the load in small, scheduled ways"
        intro = "Stress advice fails when it asks for an hour you do not have. Ten quiet minutes counts."
        habits.append("Write tomorrow's first task before bed so it is not spinning in your head.")
        rest.append("A short walk without your phone is a practical way to let a tense day finish.")
    elif goal == "recovery":
        headline = "While you are unwell, recovery outranks fitness"
        intro = "This plan is for the days around an illness. Go back to normal training only when fever and unusual breathlessness have settled."
        movement = [
            "Skip hard workouts until you have been free of fever for a day and breathing feels like your normal.",
            "A slow walk indoors or outdoors is enough movement while you recover.",
        ]
        nutrition = [
            "Fluids first. Eat what appeals in small portions: porridge, fruit, soup, yoghurt, or rice with beans.",
            "There is no special superfood required. Appetite usually returns as the illness settles.",
        ]
        cautions.append("If you are getting worse, this plan is the wrong tool. Use the symptom checker warnings or contact a clinician.")
    else:
        headline = "A simple week of looking after the basics"
        intro = "General wellness here means meals you recognize, some walking, and enough sleep. Nothing on this page replaces a clinician."

    return {
        "headline": headline,
        "intro": intro,
        "goal_label": label_for(GOALS, goal),
        "activity_label": label_for(ACTIVITIES, activity),
        "diet_label": label_for(DIETS, diet),
        "sleep_label": label_for(SLEEP, sleep_hours),
        "sections": [
            {"title": "Nutrition", "items": nutrition[:4]},
            {"title": "Movement", "items": movement[:3]},
            {"title": "Sleep and recovery", "items": rest[:3]},
            {"title": "Everyday habits", "items": habits[:3]},
        ],
        "cautions": cautions,
    }
