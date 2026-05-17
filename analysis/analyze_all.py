"""
Comprehensive Datathon Analysis Script
Analyses the full CV database, with deep focus on Project Manager candidates.
Outputs: summary stats, charts (PNG), and a detailed markdown report.
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import json
import textwrap

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "DATA")
OUT_DIR  = os.path.dirname(__file__)  # analysis folder
CHARTS   = os.path.join(OUT_DIR, "charts")
os.makedirs(CHARTS, exist_ok=True)

# ── Load data ──────────────────────────────────────────────────────────────────
cv_db   = pd.read_csv(os.path.join(DATA_DIR, "Datathon Database - CV Database.csv"))
resume  = pd.read_csv(os.path.join(DATA_DIR, "Datathon Database - Resume Text.csv"))
jd_db   = pd.read_csv(os.path.join(DATA_DIR, "Datathon Database - Job Descriptions.csv"))
q_db    = pd.read_csv(os.path.join(DATA_DIR, "Datathon Database - General Questionnaire.csv"))
pm135   = pd.read_csv(os.path.join(DATA_DIR, "PROJECT MANAGER 135 csv.csv"))

# ── Style ──────────────────────────────────────────────────────────────────────
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)
COLORS = {"Strong": "#2ecc71", "Average": "#f39c12", "Weak": "#e74c3c", "Unusual/Surprise": "#9b59b6"}

# ══════════════════════════════════════════════════════════════════════════════
# 1. OVERALL DATABASE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("DATATHON CV DATABASE — FULL ANALYSIS")
print("=" * 60)

total = len(cv_db)
roles = cv_db["Role"].unique()
print(f"\nTotal candidates : {total}")
print(f"Roles            : {', '.join(roles)}")
print(f"Fields           : {', '.join(cv_db['Field'].unique())}")

# Distribution by role and level
role_level = cv_db.groupby(["Role", "Candidate Level"]).size().unstack(fill_value=0)
print("\n── Candidates by Role × Level ──")
print(role_level.to_string())

# ── Chart 1: Overall distribution ──────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 1a. By role
role_counts = cv_db["Role"].value_counts()
axes[0].barh(role_counts.index, role_counts.values, color=sns.color_palette("viridis", len(role_counts)))
axes[0].set_xlabel("Count")
axes[0].set_title("Candidates by Role")
for i, v in enumerate(role_counts.values):
    axes[0].text(v + 0.3, i, str(v), va="center", fontweight="bold")

# 1b. By level
level_counts = cv_db["Candidate Level"].value_counts()
colors_ordered = [COLORS.get(l, "#95a5a6") for l in level_counts.index]
axes[1].bar(level_counts.index, level_counts.values, color=colors_ordered)
axes[1].set_ylabel("Count")
axes[1].set_title("Candidates by Level")
for i, v in enumerate(level_counts.values):
    axes[1].text(i, v + 0.5, str(v), ha="center", fontweight="bold")

plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "01_overall_distribution.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 01_overall_distribution.png")

# ── Chart 2: Fit score distribution ───────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
for level in ["Strong", "Average", "Weak", "Unusual/Surprise"]:
    subset = cv_db[cv_db["Candidate Level"] == level]["Expected Fit Score"]
    ax.hist(subset, bins=15, alpha=0.6, label=level, color=COLORS[level], edgecolor="white")
ax.set_xlabel("Expected Fit Score")
ax.set_ylabel("Frequency")
ax.set_title("Fit Score Distribution by Candidate Level (All Roles)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "02_fit_score_distribution.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 02_fit_score_distribution.png")

# ── Chart 3: Experience vs Fit Score ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
for level in ["Strong", "Average", "Weak", "Unusual/Surprise"]:
    subset = cv_db[cv_db["Candidate Level"] == level]
    ax.scatter(subset["Years Experience"], subset["Expected Fit Score"],
               alpha=0.6, label=level, color=COLORS[level], s=60, edgecolors="white", linewidth=0.5)
ax.set_xlabel("Years of Experience")
ax.set_ylabel("Expected Fit Score")
ax.set_title("Experience vs Fit Score (All Roles)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "03_experience_vs_fitscore.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 03_experience_vs_fitscore.png")

# ══════════════════════════════════════════════════════════════════════════════
# 2. PROJECT MANAGER DEEP DIVE
# ══════════════════════════════════════════════════════════════════════════════
pm = cv_db[cv_db["Role"] == "Project Manager"].copy()
print(f"\n{'='*60}")
print("PROJECT MANAGER DEEP DIVE")
print(f"{'='*60}")
print(f"Total PM candidates: {len(pm)}")

# Level breakdown
pm_levels = pm["Candidate Level"].value_counts()
print(f"\n── PM Level Distribution ──")
for lvl, cnt in pm_levels.items():
    print(f"  {lvl:20s}: {cnt}")

# Experience stats by level
print(f"\n── PM Experience Stats by Level ──")
for lvl in ["Strong", "Average", "Weak", "Unusual/Surprise"]:
    sub = pm[pm["Candidate Level"] == lvl]
    if len(sub) > 0:
        print(f"  {lvl:20s}: mean={sub['Years Experience'].mean():.1f}, "
              f"min={sub['Years Experience'].min()}, max={sub['Years Experience'].max()}, "
              f"fit_score_mean={sub['Expected Fit Score'].mean():.1f}")

# Fit score stats
print(f"\n── PM Fit Score Summary ──")
print(f"  Mean  : {pm['Expected Fit Score'].mean():.1f}")
print(f"  Median: {pm['Expected Fit Score'].median():.1f}")
print(f"  Std   : {pm['Expected Fit Score'].std():.1f}")
print(f"  Min   : {pm['Expected Fit Score'].min()}")
print(f"  Max   : {pm['Expected Fit Score'].max()}")

# Recommendation breakdown
rec_counts = pm["Expected Recommendation"].value_counts()
print(f"\n── PM Recommendation Breakdown ──")
for rec, cnt in rec_counts.items():
    print(f"  {rec:45s}: {cnt}")

# ── Chart 4: PM Fit Score by Level ────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5))
level_order = ["Strong", "Average", "Weak", "Unusual/Surprise"]
pm_plot = pm.copy()
pm_plot["Candidate Level"] = pd.Categorical(pm_plot["Candidate Level"], categories=level_order, ordered=True)
box_colors = [COLORS[l] for l in level_order]
bp = pm_plot.boxplot(column="Expected Fit Score", by="Candidate Level", ax=ax, patch_artist=True, return_type="dict")
for patch, color in zip(bp["Expected Fit Score"]["boxes"], box_colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
ax.set_title("PM Fit Score Distribution by Level")
ax.set_xlabel("Candidate Level")
ax.set_ylabel("Expected Fit Score")
fig.suptitle("")
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "04_pm_fitscore_by_level.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 04_pm_fitscore_by_level.png")

# ── Chart 5: PM Experience by Level ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5))
bp2 = pm_plot.boxplot(column="Years Experience", by="Candidate Level", ax=ax, patch_artist=True, return_type="dict")
for patch, color in zip(bp2["Years Experience"]["boxes"], box_colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
ax.set_title("PM Years of Experience by Level")
ax.set_xlabel("Candidate Level")
ax.set_ylabel("Years of Experience")
fig.suptitle("")
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "05_pm_experience_by_level.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 05_pm_experience_by_level.png")

# ── Chart 6: PM Recommendation Pie ───────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 7))
rec_colors = {"Recommend": "#2ecc71", "Maybe / needs further assessment": "#f39c12",
              "Do not recommend": "#e74c3c", "Conditional / requires follow-up interview": "#9b59b6"}
colors_pie = [rec_colors.get(r, "#95a5a6") for r in rec_counts.index]
wedges, texts, autotexts = ax.pie(rec_counts.values, labels=rec_counts.index, autopct="%1.0f%%",
                                   colors=colors_pie, startangle=90, textprops={"fontsize": 9})
ax.set_title("PM Recommendation Distribution")
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "06_pm_recommendation_pie.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 06_pm_recommendation_pie.png")

# ── Skills Analysis ───────────────────────────────────────────────────────
all_skills = []
for skills_str in pm["Core Skills"].dropna():
    for s in str(skills_str).split(","):
        s = s.strip().lower()
        if s and s != "basic communication":
            all_skills.append(s)

skill_counts = Counter(all_skills).most_common(15)
print(f"\n── Top 15 PM Skills ──")
for skill, cnt in skill_counts:
    print(f"  {skill:35s}: {cnt}")

# ── Chart 7: Top PM Skills ───────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
skills_df = pd.DataFrame(skill_counts, columns=["Skill", "Count"])
ax.barh(skills_df["Skill"][::-1], skills_df["Count"][::-1], color=sns.color_palette("coolwarm", len(skills_df)))
ax.set_xlabel("Frequency")
ax.set_title("Top 15 Skills Among PM Candidates")
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "07_pm_top_skills.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 07_pm_top_skills.png")

# ── Tools Analysis ────────────────────────────────────────────────────────
all_tools = []
for tools_str in pm["Tools"].dropna():
    for t in str(tools_str).split(","):
        t = t.strip()
        if t:
            all_tools.append(t)

tool_counts = Counter(all_tools).most_common(10)
print(f"\n── Top 10 PM Tools ──")
for tool, cnt in tool_counts:
    print(f"  {tool:25s}: {cnt}")

# ── Chart 8: PM Tools ────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5))
tools_df = pd.DataFrame(tool_counts, columns=["Tool", "Count"])
ax.bar(tools_df["Tool"], tools_df["Count"], color=sns.color_palette("Set2", len(tools_df)))
ax.set_ylabel("Frequency")
ax.set_title("Top 10 Tools Among PM Candidates")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "08_pm_top_tools.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 08_pm_top_tools.png")

# ── Education Analysis ────────────────────────────────────────────────────
edu_counts = pm["Education"].value_counts()
print(f"\n── PM Education Distribution ──")
for edu, cnt in edu_counts.items():
    print(f"  {edu:35s}: {cnt}")

# ── Certification Analysis ────────────────────────────────────────────────
cert_counts = pm["Certification"].value_counts()
print(f"\n── PM Certification Distribution ──")
for cert, cnt in cert_counts.items():
    print(f"  {cert:40s}: {cnt}")

# ── Chart 9: Education vs Fit Score ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
edu_fit = pm.groupby("Education")["Expected Fit Score"].mean().sort_values(ascending=False)
ax.barh(edu_fit.index, edu_fit.values, color=sns.color_palette("viridis", len(edu_fit)))
ax.set_xlabel("Mean Fit Score")
ax.set_title("PM: Average Fit Score by Education")
for i, (idx, v) in enumerate(edu_fit.items()):
    ax.text(v + 0.5, i, f"{v:.1f}", va="center", fontsize=9)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "09_pm_education_fitscore.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 09_pm_education_fitscore.png")

# ══════════════════════════════════════════════════════════════════════════════
# 3. PM CANDIDATE PROFILES — STRONG vs WEAK vs UNUSUAL
# ══════════════════════════════════════════════════════════════════════════════
pm_strong  = pm[pm["Candidate Level"] == "Strong"].sort_values("Expected Fit Score", ascending=False)
pm_weak    = pm[pm["Candidate Level"] == "Weak"].sort_values("Expected Fit Score")
pm_unusual = pm[pm["Candidate Level"] == "Unusual/Surprise"]

print(f"\n{'='*60}")
print("PM STRONG CANDIDATES (Top Performers)")
print(f"{'='*60}")
for _, row in pm_strong.iterrows():
    print(f"  {row['Candidate ID']} | {row['Candidate Name']:20s} | "
          f"Exp: {row['Years Experience']}yr | Score: {row['Expected Fit Score']} | "
          f"Ed: {row['Education']} | Cert: {row['Certification']}")

print(f"\n{'='*60}")
print("PM WEAK CANDIDATES")
print(f"{'='*60}")
for _, row in pm_weak.iterrows():
    print(f"  {row['Candidate ID']} | {row['Candidate Name']:20s} | "
          f"Exp: {row['Years Experience']}yr | Score: {row['Expected Fit Score']} | "
          f"Weakness: {row['Expected Weaknesses'][:60]}")

print(f"\n{'='*60}")
print("PM UNUSUAL / SURPRISE CANDIDATES")
print(f"{'='*60}")
for _, row in pm_unusual.iterrows():
    print(f"  {row['Candidate ID']} | {row['Candidate Name']:20s} | "
          f"Exp: {row['Years Experience']}yr | Score: {row['Expected Fit Score']} | "
          f"Edge: {row['Surprise / Edge Case']}")

# ══════════════════════════════════════════════════════════════════════════════
# 4. CROSS-ROLE COMPARISON
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("CROSS-ROLE COMPARISON")
print(f"{'='*60}")

role_stats = cv_db.groupby("Role").agg(
    count=("Candidate ID", "count"),
    mean_score=("Expected Fit Score", "mean"),
    median_score=("Expected Fit Score", "median"),
    mean_exp=("Years Experience", "mean"),
    std_score=("Expected Fit Score", "std"),
).round(1)
print(role_stats.to_string())

# ── Chart 10: Cross-role comparison ──────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

role_mean = cv_db.groupby("Role")["Expected Fit Score"].mean().sort_values()
axes[0].barh(role_mean.index, role_mean.values, color=sns.color_palette("rocket", len(role_mean)))
axes[0].set_xlabel("Mean Fit Score")
axes[0].set_title("Mean Fit Score by Role")
for i, v in enumerate(role_mean.values):
    axes[0].text(v + 0.3, i, f"{v:.1f}", va="center", fontsize=9)

role_exp = cv_db.groupby("Role")["Years Experience"].mean().sort_values()
axes[1].barh(role_exp.index, role_exp.values, color=sns.color_palette("mako", len(role_exp)))
axes[1].set_xlabel("Mean Years Experience")
axes[1].set_title("Mean Experience by Role")
for i, v in enumerate(role_exp.values):
    axes[1].text(v + 0.1, i, f"{v:.1f}", va="center", fontsize=9)

plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "10_crossrole_comparison.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 10_crossrole_comparison.png")

# ── Chart 11: PM Heatmap — Level × Education ─────────────────────────────
fig, ax = plt.subplots(figsize=(10, 4))
pm_heat = pm.groupby(["Candidate Level", "Education"]).size().unstack(fill_value=0)
# Reorder levels
heat_order = [l for l in level_order if l in pm_heat.index]
pm_heat = pm_heat.loc[heat_order]
sns.heatmap(pm_heat, annot=True, fmt="d", cmap="YlOrRd", ax=ax, linewidths=0.5)
ax.set_title("PM Candidates: Level × Education Heatmap")
plt.tight_layout()
plt.savefig(os.path.join(CHARTS, "11_pm_level_education_heatmap.png"), dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ Chart: 11_pm_level_education_heatmap.png")

# ── Load results.json if exists ───────────────────────────────────────────
results_path = os.path.join(os.path.dirname(__file__), "..", "results.json")
results_data = []
if os.path.exists(results_path):
    with open(results_path, "r", encoding="utf-8") as f:
        results_data = json.load(f)

if results_data:
    print(f"\n{'='*60}")
    print(f"AGENT RESULTS ANALYSIS ({len(results_data)} evaluated)")
    print(f"{'='*60}")
    
    scores = [r["overall_fit_score"] for r in results_data if "overall_fit_score" in r]
    recs   = [r["recommendation"] for r in results_data if "recommendation" in r]
    flags  = []
    for r in results_data:
        flags.extend(r.get("risk_flags", []))
    
    print(f"  Scores: mean={np.mean(scores):.1f}, min={min(scores)}, max={max(scores)}")
    print(f"  Recommendations: {Counter(recs)}")
    if flags:
        print(f"  Risk flags: {Counter(flags)}")

# ══════════════════════════════════════════════════════════════════════════════
# 5. PM WEAKNESS PATTERNS
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print("PM WEAKNESS / STRENGTH PATTERN ANALYSIS")
print(f"{'='*60}")

weakness_all = []
for w_str in pm["Expected Weaknesses"].dropna():
    for w in str(w_str).split(";"):
        w = w.strip().lower()
        if w:
            weakness_all.append(w)

strength_all = []
for s_str in pm["Expected Strengths"].dropna():
    for s in str(s_str).split(";"):
        s = s.strip().lower()
        if s:
            strength_all.append(s)

print("\n── Top PM Weaknesses ──")
for w, c in Counter(weakness_all).most_common(10):
    print(f"  {w[:60]:60s}: {c}")

print("\n── Top PM Strengths ──")
for s, c in Counter(strength_all).most_common(10):
    print(f"  {s[:60]:60s}: {c}")

print("\n✅ Analysis complete. All charts saved to analysis/charts/")
print(f"   Total charts generated: 11")
