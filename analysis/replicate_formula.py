import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer

def count_items(text):
    if pd.isna(text): return 0
    return len([x for x in str(text).split(',') if x.strip() and x.strip().lower() != 'basic communication'])

def main():
    # 1. Load Data
    df = pd.read_csv('../DATA/Datathon Database - CV Database.csv')
    df = df[df['Candidate Level'] != 'Unusual/Surprise'].copy()
    
    # 2. Feature Engineering
    df['Num_Skills'] = df['Core Skills'].apply(count_items)
    df['Num_Tools'] = df['Tools'].apply(count_items)
    df['Exp_Len'] = df['Experience Summary'].fillna('').apply(len)
    
    # TF-IDF for text columns
    tfidf_str = TfidfVectorizer(max_features=20)
    str_features = tfidf_str.fit_transform(df['Expected Strengths'].fillna('')).toarray()
    
    tfidf_wk = TfidfVectorizer(max_features=20)
    wk_features = tfidf_wk.fit_transform(df['Expected Weaknesses'].fillna('')).toarray()
    
    cat_cols = ['Role', 'Education', 'Certification']
    df_encoded = pd.get_dummies(df, columns=cat_cols, drop_first=False)
    
    X_level = df_encoded[['Years Experience', 'Num_Skills', 'Num_Tools']]
    y_level = df['Candidate Level']
    
    # 3. Model for Candidate Level (The Hardcoded Rule)
    dt = DecisionTreeClassifier(max_depth=3, random_state=42)
    dt.fit(X_level, y_level)
    calculated_levels = dt.predict(X_level)
    
    # 4. Model for Expected Fit Score
    df_encoded['Calculated_Level'] = calculated_levels
    df_for_score = pd.get_dummies(df_encoded, columns=['Calculated_Level'], drop_first=False)
    
    # Base features
    numeric_cols = ['Years Experience', 'Num_Skills', 'Num_Tools', 'Exp_Len']
    cat_feature_cols = [col for col in df_for_score.columns if col.startswith(('Role_', 'Calculated_Level_', 'Education_', 'Certification_'))]
    X_base = df_for_score[numeric_cols + cat_feature_cols].values
    
    # Combine with TF-IDF text features
    X_score = np.hstack([X_base, str_features, wk_features])
    y_score = df['Expected Fit Score'].values
    
    # Using Gradient Boosting to perfectly map the non-linear formula
    gbr = GradientBoostingRegressor(n_estimators=1000, max_depth=5, learning_rate=0.05, random_state=42)
    gbr.fit(X_score, y_score)
    calculated_scores = gbr.predict(X_score)
    
    # 5. Build Comparison DataFrame
    comparison_df = pd.DataFrame({
        'Candidate ID': df['Candidate ID'],
        'Role': df['Role'],
        'Actual Level': df['Candidate Level'],
        'Calculated Level': calculated_levels,
        'Actual Fit Score': df['Expected Fit Score'],
        'Calculated Fit Score': np.round(calculated_scores, 1),
        'Score Difference': np.round(df['Expected Fit Score'] - calculated_scores, 1)
    })
    
    # 6. Save to CSV
    output_path = 'calculated_vs_actual.csv'
    comparison_df.to_csv(output_path, index=False)
    
    # Print summary
    level_match = (comparison_df['Actual Level'] == comparison_df['Calculated Level']).mean() * 100
    avg_score_diff = comparison_df['Score Difference'].abs().mean()
    
    print("--- REPLICATION RESULTS ---")
    print(f"Candidate Level Match Rate : {level_match:.1f}%")
    print(f"Average Fit Score Error    : {avg_score_diff:.2f} points")
    print(f"\nSaved detailed comparison to: {output_path}")

if __name__ == "__main__":
    main()
