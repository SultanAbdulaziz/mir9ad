"""
Pipeline: Datathon Database - Resume Text  →  CV Database schema
Pure pandas + regex — no LLM or API calls.

Reads:  DATA/Datathon Database - Resume Text.csv
Writes: DATA/Datathon Database - CV Database - Generated.csv
"""

import re
from pathlib import Path
from datetime import date

import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
DATA   = Path(__file__).parent / "DATA"
INPUT  = DATA / "Datathon Database - Resume Text.csv"
OUTPUT = DATA / "generated.csv"

# Reference "today" for open-ended (Present) roles
REFERENCE_DATE = date.today()

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,  "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10,"nov": 11, "dec": 12,
}

# ── role → field ──────────────────────────────────────────────────────────────
ROLE_FIELD = {
    "project manager":      "Management",
    "operations":           "Management",
    "strategy":             "Management",
    "financial analyst":    "Finance",
    "finance":              "Finance",
    "accountant":           "Finance",
    "fp&a":                 "Finance",
    "marketing":            "Marketing",
    "brand":                "Marketing",
    "digital marketing":    "Marketing",
    "growth":               "Marketing",
    "content":              "Marketing",
    "data scientist":       "Tech / Data",
    "data analyst":         "Tech / Data",
    "data engineer":        "Tech / Data",
    "ml engineer":          "Tech / Data",
    "bi analyst":           "Tech / Data",
    "business intelligence":"Tech / Data",
    "software engineer":    "Tech / Software",
    "developer":            "Tech / Software",
    "devops":               "Tech / Software",
    "qa engineer":          "Tech / Software",
    "backend":              "Tech / Software",
    "frontend":             "Tech / Software",
}


# ── section extractor ─────────────────────────────────────────────────────────
SECTION_HEADERS = [
    "PROFESSIONAL SUMMARY",
    "CORE SKILLS",
    "TOOLS",
    "PROFESSIONAL EXPERIENCE",
    "SELECTED PROJECTS",
    "EDUCATION",
    "CERTIFICATIONS",
    "LANGUAGES",
]

def extract_section(text: str, section: str) -> str:
    """Return the text between `section` and the next known header (or end)."""
    pattern = re.compile(
        rf"\b{re.escape(section)}\b(.*?)(?={'|'.join(re.escape(h) for h in SECTION_HEADERS if h != section)}|$)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


# ── individual field parsers ──────────────────────────────────────────────────
def parse_name(text: str) -> str:
    first_line = text.strip().split("\n")[0].strip()
    return first_line.title()


def parse_field(role: str) -> str:
    role_lower = role.lower()
    for keyword, field in ROLE_FIELD.items():
        if keyword in role_lower:
            return field
    return "Management"


def parse_skills(text: str) -> str:
    raw = extract_section(text, "CORE SKILLS")
    # Remove bullet points and extra whitespace; return comma-separated
    items = [s.strip().lstrip("•–-").strip() for s in re.split(r"[,\n]", raw) if s.strip()]
    return ", ".join(i for i in items if i)


def parse_tools(text: str) -> str:
    raw = extract_section(text, "TOOLS")
    items = [s.strip().lstrip("•–-").strip() for s in re.split(r"[,\n]", raw) if s.strip()]
    return ", ".join(i for i in items if i)


def parse_education(text: str) -> str:
    raw = extract_section(text, "EDUCATION")
    # First non-empty line, strip trailing year " | YYYY"
    for line in raw.split("\n"):
        line = line.strip().lstrip("•–-").strip()
        if line:
            return re.sub(r"\s*\|\s*\d{4}.*$", "", line).strip()
    return ""


def parse_certification(text: str) -> str:
    raw = extract_section(text, "CERTIFICATIONS")
    certs = []
    for line in raw.split("\n"):
        line = line.strip().lstrip("•–-").strip()
        if line:
            # Strip "| Issued YYYY"
            cert = re.sub(r"\s*\|\s*Issued.*$", "", line, flags=re.IGNORECASE).strip()
            if cert:
                certs.append(cert)
    return ", ".join(certs)


def _parse_date(month_str: str, year_str: str) -> date:
    m = MONTH_MAP.get(month_str[:3].lower(), 1)
    return date(int(year_str), m, 1)


def parse_years_experience(text: str) -> int:
    """
    Find all date ranges in the PROFESSIONAL EXPERIENCE section,
    return rounded total years from earliest start to latest end.
    """
    exp_text = extract_section(text, "PROFESSIONAL EXPERIENCE")

    # Match patterns like "May 2022 – Present" or "Mar 2019 – Mar 2022"
    date_pattern = re.compile(
        r"([A-Za-z]{3})\s+(\d{4})\s*[–—-]+\s*(?:(Present)|([A-Za-z]{3})\s+(\d{4}))",
        re.IGNORECASE,
    )

    starts, ends = [], []
    for m in date_pattern.finditer(exp_text):
        starts.append(_parse_date(m.group(1), m.group(2)))
        if m.group(3):  # Present
            ends.append(REFERENCE_DATE)
        else:
            ends.append(_parse_date(m.group(4), m.group(5)))

    if not starts:
        return 0

    earliest = min(starts)
    latest   = max(ends)
    delta    = (latest - earliest).days / 365.25
    return max(0, round(delta))


def parse_experience_summary(text: str) -> str:
    """
    Build a one-sentence summary from the PROFESSIONAL EXPERIENCE section:
    list job titles and companies in chronological order.
    """
    exp_text = extract_section(text, "PROFESSIONAL EXPERIENCE")

    # Match job header lines: "Title | Company | Dates"
    job_pattern = re.compile(
        r"^([^|•\n]+?)\s*\|\s*([^|•\n]+?)\s*\|[^|\n]*$",
        re.MULTILINE,
    )
    jobs = [(m.group(1).strip(), m.group(2).strip()) for m in job_pattern.finditer(exp_text)]

    if not jobs:
        return ""

    # Chronological order (earliest first = last in list since they're reverse-chron in resume)
    jobs_chrono = list(reversed(jobs))
    parts = " → ".join(f"{title} at {company}" for title, company in jobs_chrono)
    n = len(jobs)
    return f"{parts}; {n} role{'s' if n > 1 else ''} with progressive responsibility."


def parse_surprise(text: str) -> str:
    """
    Extract "Additional context:" line from the PROFESSIONAL SUMMARY section.
    Present only in Unusual/Surprise candidates.
    """
    summary = extract_section(text, "PROFESSIONAL SUMMARY")
    m = re.search(r"Additional context:\s*(.+)", summary, re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ── level / score / recommendation ───────────────────────────────────────────
def determine_level(years: int, surprise_text: str, summary_text: str) -> str:
    if surprise_text or re.search(
        r"nontraditional|career switcher|additional context", summary_text, re.IGNORECASE
    ):
        return "Unusual/Surprise"
    if years >= 4:
        return "Strong"
    if years >= 2:
        return "Average"
    return "Weak"


def determine_fit_score(years: int, level: str) -> int:
    if level == "Strong":
        # 80–95 scaled by years beyond 4
        return min(95, 80 + (years - 4) * 3)
    if level == "Average":
        # 60–75 for 2–3 years
        return min(75, 60 + (years - 2) * 10)
    if level == "Weak":
        # 25–35 for 0–1 years
        return max(25, 25 + years * 10)
    # Unusual/Surprise — mid range, explore further
    return 55


def determine_recommendation(level: str) -> str:
    return {
        "Strong":           "Recommend",
        "Average":          "Maybe / needs further assessment",
        "Weak":             "Do not recommend",
        "Unusual/Surprise": "Conditional / requires follow-up interview",
    }[level]


def determine_strengths(level: str) -> str:
    base = {
        "Strong":           "clear evidence of role-specific results; structured problem-solving and strong ownership",
        "Average":          "adequate exposure to key areas; shows growing practical experience",
        "Weak":             "foundational skills present; shows motivation and willingness to learn",
        "Unusual/Surprise": "transferable skills from prior background; unique perspective and adaptability",
    }[level]
    return base


def determine_weaknesses(level: str) -> str:
    return {
        "Strong":           "may need onboarding on company-specific processes; limited enterprise-scale experience",
        "Average":          "could improve cross-domain exposure; needs more ownership of end-to-end delivery",
        "Weak":             "limited hands-on experience in core responsibilities; requires significant mentoring",
        "Unusual/Surprise": "limited technical depth in target role; may face credibility gap without domain track record",
    }[level]


def determine_testing_use(level: str) -> str:
    return {
        "Strong":           "Use as a normal fit case.",
        "Average":          "Use as a normal fit case.",
        "Weak":             "Use to test weak candidate rejection.",
        "Unusual/Surprise": "Use to test edge case handling.",
    }[level]


# ── main transform ────────────────────────────────────────────────────────────
def transform_row(row: pd.Series) -> pd.Series:
    text   = row["Resume Text"]
    cid    = row["Candidate ID"]
    role   = row["Role"]

    return pd.Series({
        "Candidate ID":            cid,
        "Role":                    role,
        "Field":                   parse_field(role),
        "Candidate Level":         "",
        "Candidate Name":          parse_name(text),
        "Years Experience":        parse_years_experience(text),
        "Education":               parse_education(text),
        "Certification":           parse_certification(text),
        "Core Skills":             parse_skills(text),
        "Tools":                   parse_tools(text),
        "Experience Summary":      parse_experience_summary(text),
        "Expected Strengths":      "",
        "Expected Weaknesses":     "",
        "Surprise / Edge Case":    "",
        "Testing Use":             "",
        "Expected Fit Score":      "",
        "Expected Recommendation": "",
        "Privacy Note":            "Synthetic CV profile; no real personal data.",
    })


def run():
    df_in = pd.read_csv(INPUT)
    print(f"Loaded {len(df_in)} resumes.")

    df_out = df_in.apply(transform_row, axis=1)

    df_out.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df_out)} rows → {OUTPUT}")
    print(df_out[["Candidate ID", "Candidate Level", "Years Experience", "Expected Fit Score"]].to_string(index=False))


if __name__ == "__main__":
    run()
