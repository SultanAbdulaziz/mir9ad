import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

# Load data
df = pd.read_csv('../DATA/Datathon Database - CV Database.csv')
df = df[df['Candidate Level'] != 'Unusual/Surprise'].copy()

# Feature Engineering
def count_items(text):
    if pd.isna(text): return 0
    return len([x for x in str(text).split(',') if x.strip() and x.strip().lower() != 'basic communication'])

df['Num_Skills'] = df['Core Skills'].apply(count_items)
df['Num_Tools'] = df['Tools'].apply(count_items)

# Fit Linear Regression
X = df[['Years Experience', 'Num_Skills', 'Num_Tools']]
y = df['Expected Fit Score']

model = LinearRegression()
model.fit(X, y)

print("--- FIT SCORE FORMULA ---")
print(f"Base Score (Intercept) : {model.intercept_:.2f}")
print(f"Weight for Experience  : {model.coef_[0]:.2f} per year")
print(f"Weight for Skills      : {model.coef_[1]:.2f} per skill")
print(f"Weight for Tools       : {model.coef_[2]:.2f} per tool")

# Check R2 to see if this simple formula perfectly explains it
print(f"R-squared of simple formula: {model.score(X, y):.4f}")

# Let's also test if there is a flat base score per Role or Level
cat_cols = ['Role', 'Education', 'Candidate Level']
df_encoded = pd.get_dummies(df, columns=cat_cols, drop_first=False)
X_full = df_encoded[['Years Experience', 'Num_Skills', 'Num_Tools'] + 
                    [col for col in df_encoded.columns if col.startswith('Role_') or col.startswith('Candidate Level_')]]

model_full = LinearRegression()
model_full.fit(X_full, y)
print("\n--- FIT SCORE FORMULA (WITH ROLE/LEVEL) ---")
print(f"Base Score (Intercept) : {model_full.intercept_:.2f}")
print(f"R-squared: {model_full.score(X_full, y):.4f}")

print("\nCoefficients:")
for col, coef in zip(X_full.columns, model_full.coef_):
    if abs(coef) > 0.5:  # Only print meaningful weights
        print(f"  {col:25s}: {coef:.2f}")
