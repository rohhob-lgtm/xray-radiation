"""
Technical Glossary Seeder — X-ray Security Engineering Domain.

Seeds the custom_dictionary_entries table with shared (user_id=NULL)
engineering terminology for X-ray security screening systems.

Run via:
  from api.utils.glossary_seed import seed_glossary
  seed_glossary(db)
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# ── English → Arabic glossary ──────────────────────────────────────────────────
_EN_AR = [
    # Manufacturers and product brands (preserve official names)
    ("Rapiscan",                 "Rapiscan",            "manufacturer"),
    ("Smiths Detection",         "Smiths Detection",    "manufacturer"),
    ("Nuctech",                  "Nuctech",             "manufacturer"),
    ("CEIA",                     "CEIA",                "manufacturer"),
    ("Garrett",                  "Garrett",             "manufacturer"),
    # Core domain terms
    ("Radiation Physics",        "فيزياء الإشعاع",       "radiation"),
    ("Nuclear Security",         "الأمن النووي",         "security"),
    ("Threat Detection",         "كشف التهديدات",        "security"),
    ("Cargo Inspection",         "تفتيش الشحنات",        "security"),
    ("Aviation Security",        "أمن الطيران",          "security"),
    # X-Ray system terminology
    ("X-ray",                    "أشعة سينية",         "xray"),
    ("X-ray system",             "نظام الأشعة السينية", "xray"),
    ("baggage screening",        "فحص الأمتعة",         "xray"),
    ("cargo screening",          "فحص البضائع",         "xray"),
    ("passenger screening",      "فحص المسافرين",       "xray"),
    ("security screening",       "الفحص الأمني",        "xray"),
    ("dual-energy imaging",      "التصوير بالطاقة المزدوجة", "xray"),
    ("tunnel",                   "نفق الفحص",           "xray"),
    ("conveyor",                 "حزام ناقل",            "mechanical"),
    ("conveyor belt",            "حزام التحريك",         "mechanical"),
    ("gantry",                   "الجسر الدوّار",        "mechanical"),
    ("detector array",           "مصفوفة الكواشف",       "xray"),
    ("detector",                 "كاشف",                "xray"),
    ("scintillator",             "مُومِض",              "xray"),
    ("photodiode",               "صمام ثنائي ضوئي",     "electronics"),
    ("image acquisition",        "اكتساب الصورة",        "xray"),
    ("image processing",         "معالجة الصورة",        "xray"),
    ("threat detection",         "كشف التهديدات",        "xray"),
    ("prohibited items",         "المواد المحظورة",      "xray"),
    ("false alarm",              "إنذار كاذب",           "xray"),
    # Radiation terminology
    ("radiation",                "إشعاع",               "radiation"),
    ("radiation dose",           "جرعة الإشعاع",        "radiation"),
    ("absorbed dose",            "الجرعة الممتصة",       "radiation"),
    ("effective dose",           "الجرعة الفعّالة",      "radiation"),
    ("dose rate",                "معدل الجرعة",          "radiation"),
    ("ALARA",                    "مبدأ ألارا",           "radiation"),
    ("radiation shielding",      "الحجب الإشعاعي",       "radiation"),
    ("focal spot",               "البؤرة",               "xray"),
    ("anode",                    "أنود",                 "xray"),
    ("cathode",                  "كاثود",               "xray"),
    ("filament",                 "خيط التوهج",           "xray"),
    ("HV generator",             "مولّد الجهد العالي",   "electrical"),
    ("high voltage",             "جهد عالٍ",             "electrical"),
    ("kilovoltage peak",         "ذروة الجهد الكيلوفولتي", "radiation"),
    ("milliampere",              "ميلي أمبير",           "electrical"),
    # Mechanical engineering
    ("calibration",              "المعايرة",             "mechanical"),
    ("calibration phantom",      "وهم المعايرة",         "mechanical"),
    ("dark current correction",  "تصحيح التيار المظلم",  "xray"),
    ("flat field correction",    "تصحيح المجال المستوي", "xray"),
    ("pixel pitch",              "خطوة البكسل",          "xray"),
    ("maintenance",              "الصيانة",              "mechanical"),
    ("preventive maintenance",   "الصيانة الوقائية",     "mechanical"),
    ("corrective maintenance",   "الصيانة التصحيحية",    "mechanical"),
    ("inspection",               "الفحص",               "mechanical"),
    ("overhaul",                 "الإصلاح الشامل",       "mechanical"),
    ("troubleshooting",          "استكشاف الأخطاء",      "mechanical"),
    ("spare parts",              "قطع الغيار",           "mechanical"),
    # Electrical / Electronics
    ("power supply",             "مصدر الطاقة",          "electrical"),
    ("circuit breaker",          "قاطع دائرة",           "electrical"),
    ("interlock",                "قفل أمان",             "electrical"),
    ("safety interlock",         "قفل السلامة",          "electrical"),
    ("grounding",                "التأريض",              "electrical"),
    ("PCB",                      "لوحة دوائر مطبوعة",    "electronics"),
    ("printed circuit board",    "لوحة الدوائر المطبوعة", "electronics"),
    ("firmware",                 "البرنامج الثابت",      "electronics"),
    ("software",                 "البرمجيات",            "electronics"),
    ("interface",                "واجهة",               "electronics"),
    # Diagnostics / Errors
    ("fault",                    "عطل",                  "diagnostics"),
    ("fault code",               "رمز العطل",            "diagnostics"),
    ("error code",               "رمز الخطأ",            "diagnostics"),
    ("alarm",                    "إنذار",               "diagnostics"),
    ("warning",                  "تحذير",               "diagnostics"),
    ("system status",            "حالة النظام",          "diagnostics"),
    ("self-test",                "الاختبار الذاتي",      "diagnostics"),
    # Safety
    ("safety warning",           "تحذير السلامة",        "safety"),
    ("radiation warning",        "تحذير الإشعاع",        "safety"),
    ("lockout tagout",           "قفل وبطاقة",           "safety"),
    ("personal protective equipment", "معدات الحماية الشخصية", "safety"),
    ("emergency stop",           "الإيقاف الطارئ",       "safety"),
    ("interlock bypass",         "تجاوز القفل",          "safety"),
]

# ── English → French ───────────────────────────────────────────────────────────
_EN_FR = [
    ("X-ray",               "rayons X",              "xray"),
    ("baggage screening",   "contrôle des bagages",  "xray"),
    ("detector",            "détecteur",             "xray"),
    ("conveyor",            "convoyeur",             "mechanical"),
    ("gantry",              "portique",              "mechanical"),
    ("calibration",         "étalonnage",            "mechanical"),
    ("maintenance",         "maintenance",           "mechanical"),
    ("fault code",          "code de défaut",        "diagnostics"),
    ("high voltage",        "haute tension",         "electrical"),
    ("radiation dose",      "dose de rayonnement",   "radiation"),
    ("focal spot",          "foyer",                 "xray"),
    ("safety warning",      "avertissement de sécurité", "safety"),
    ("spare parts",         "pièces de rechange",    "mechanical"),
    ("troubleshooting",     "dépannage",             "mechanical"),
    ("firmware",            "micrologiciel",         "electronics"),
    ("PCB",                 "carte électronique",    "electronics"),
    ("emergency stop",      "arrêt d'urgence",       "safety"),
    ("interlock",           "verrouillage",          "electrical"),
    ("anode",               "anode",                 "xray"),
    ("cathode",             "cathode",               "xray"),
]

# ── English → German ───────────────────────────────────────────────────────────
_EN_DE = [
    ("X-ray",               "Röntgen",               "xray"),
    ("baggage screening",   "Gepäckkontrolle",       "xray"),
    ("detector",            "Detektor",              "xray"),
    ("conveyor",            "Förderband",            "mechanical"),
    ("gantry",              "Portal",                "mechanical"),
    ("calibration",         "Kalibrierung",          "mechanical"),
    ("maintenance",         "Wartung",               "mechanical"),
    ("fault code",          "Fehlercode",            "diagnostics"),
    ("high voltage",        "Hochspannung",          "electrical"),
    ("radiation dose",      "Strahlendosis",         "radiation"),
    ("focal spot",          "Brennfleck",            "xray"),
    ("safety warning",      "Sicherheitswarnung",    "safety"),
    ("spare parts",         "Ersatzteile",           "mechanical"),
    ("troubleshooting",     "Fehlerbehebung",        "mechanical"),
    ("firmware",            "Firmware",              "electronics"),
    ("PCB",                 "Leiterplatte",          "electronics"),
    ("emergency stop",      "Not-Aus",               "safety"),
    ("interlock",           "Verriegelung",          "electrical"),
    ("anode",               "Anode",                 "xray"),
    ("cathode",             "Kathode",               "xray"),
]

# ── English → Spanish ──────────────────────────────────────────────────────────
_EN_ES = [
    ("X-ray",               "rayos X",               "xray"),
    ("baggage screening",   "control de equipaje",   "xray"),
    ("detector",            "detector",              "xray"),
    ("conveyor",            "transportador",         "mechanical"),
    ("gantry",              "pórtico",               "mechanical"),
    ("calibration",         "calibración",           "mechanical"),
    ("maintenance",         "mantenimiento",         "mechanical"),
    ("fault code",          "código de fallo",       "diagnostics"),
    ("high voltage",        "alta tensión",          "electrical"),
    ("radiation dose",      "dosis de radiación",    "radiation"),
    ("focal spot",          "punto focal",           "xray"),
    ("safety warning",      "advertencia de seguridad", "safety"),
    ("spare parts",         "repuestos",             "mechanical"),
    ("troubleshooting",     "resolución de problemas", "mechanical"),
    ("firmware",            "firmware",              "electronics"),
    ("PCB",                 "placa de circuito impreso", "electronics"),
    ("emergency stop",      "parada de emergencia",  "safety"),
    ("interlock",           "enclavamiento",         "electrical"),
    ("anode",               "ánodo",                 "xray"),
    ("cathode",             "cátodo",                "xray"),
]

_GLOSSARY_DATA = {
    ("en", "ar"): _EN_AR,
    ("en", "fr"): _EN_FR,
    ("en", "de"): _EN_DE,
    ("en", "es"): _EN_ES,
}


def seed_glossary(db: Session) -> int:
    """
    Seed shared glossary entries (user_id=NULL).
    Skips existing entries to be idempotent.
    Returns the number of new entries added.
    """
    from api.db.models import CustomDictionaryEntry

    added = 0
    for (src_lang, tgt_lang), entries in _GLOSSARY_DATA.items():
        # Get existing shared terms for this language pair
        existing = {
            e.source_term.lower()
            for e in db.query(CustomDictionaryEntry)
            .filter(
                CustomDictionaryEntry.source_lang == src_lang,
                CustomDictionaryEntry.target_lang == tgt_lang,
                CustomDictionaryEntry.user_id.is_(None),
            )
            .all()
        }

        for source_term, target_term, domain in entries:
            if source_term.lower() in existing:
                continue
            db.add(CustomDictionaryEntry(
                user_id=None,  # shared
                source_term=source_term,
                target_term=target_term,
                source_lang=src_lang,
                target_lang=tgt_lang,
                domain=domain,
                notes="Auto-seeded: X-ray security engineering glossary",
            ))
            added += 1

    if added > 0:
        db.commit()
        log.info("Glossary: seeded %d new shared entries", added)
    return added
