import streamlit as st
from statsbombpy import sb
import pandas as pd

# Streamlit Title
st.title("StatsBomb Data Dashboard - Match Dates for Selected Team")

# Load competitions
st.header("Step 1: Select Competition and Season")
competitions = sb.competitions()

# Competition selection
competition_name = st.selectbox("Select Competition", competitions['competition_name'].unique())
competition_id = competitions[competitions['competition_name'] == competition_name]['competition_id'].values[0]

# Manually set the season_id (replace with valid season ID)
season_id = st.selectbox("Select Season", ['2020-2021', '2021-2022', '2022-2023', '2023-2024'])

# Team input (home or away)
team_name = st.text_input("Enter Team Name", placeholder="e.g., Manchester United")

# Fetch matches for the selected competition and season
if competition_id and season_id and team_name:
    st.write("Fetching match data for the selected team...")

    try:
        # Fetch matches for the selected competition and season using statsbombpy
        matches = sb.matches(competition_id=competition_id, season_id=season_id)

        # Filter matches by team (home or away)
        filtered_matches = matches[
            (matches['home_team'].str.contains(team_name, case=False)) | 
            (matches['away_team'].str.contains(team_name, case=False))
        ]

        if not filtered_matches.empty:
            st.write(f"Matches for {team_name} in {season_id}:")
            match_dates = filtered_matches[['home_team', 'away_team', 'date']]
            
            # Show dates of the matches
            match_dates['date'] = pd.to_datetime(match_dates['date'])
            match_dates_sorted = match_dates.sort_values(by='date', ascending=True)
            st.dataframe(match_dates_sorted[['home_team', 'away_team', 'date']])

        else:
            st.write(f"No matches found for {team_name} in the {season_id} season.")
    
    except Exception as e:
        st.error(f"Error fetching data: {e}")