import streamlit as st
from statsbombpy import sb
from fpdf import FPDF
from mplsoccer import Pitch
import matplotlib.pyplot as plt
import pandas as pd

# Streamlit Title
st.title("StatsBomb Data Dashboard with PDF Export")

# Load competitions
st.header("Step 1: Select Competition, Date, and Teams")
competitions = sb.competitions()

# Competition selection
competition_name = st.selectbox("Select Competition", competitions['competition_name'].unique())
competition_id = competitions[competitions['competition_name'] == competition_name]['competition_id'].values[0]

# Load seasons for the selected competition
seasons = sb.seasons(competition_id=competition_id)
season_name = st.selectbox("Select Season", seasons['season_name'].unique())
season_id = seasons[seasons['season_name'] == season_name]['season_id'].values[0]

# Date input for the match
match_date_input = st.text_input("Enter Match Date (DD/MM/YY)", placeholder="e.g., 01/06/19")

# Team input (home or away)
team_name = st.text_input("Enter Team Name", placeholder="e.g., Manchester United")

# Parse the date input
if match_date_input:
    try:
        match_date = pd.to_datetime(match_date_input, format='%d/%m/%y')
        st.write(f"Selected Date: {match_date.strftime('%d/%m/%Y')}")
        
        # Load matches for the selected competition and season
        matches = sb.matches(competition_id=competition_id, season_id=season_id)
        
        # Filter matches by date
        matches['match_date'] = pd.to_datetime(matches['date'])
        filtered_matches = matches[matches['match_date'].dt.strftime('%d/%m/%y') == match_date_input]
        
        # Further filter by team name
        if team_name:
            filtered_matches = filtered_matches[
                (filtered_matches['home_team'].str.contains(team_name, case=False)) | 
                (filtered_matches['away_team'].str.contains(team_name, case=False))
            ]
        
        if not filtered_matches.empty:
            st.write("Matching Matches Found:")
            st.dataframe(filtered_matches)

            # Select a match
            match_id = filtered_matches['match_id'].values[0]
            st.header("Step 2: Visualize and Export Match Data")
            events = sb.events(match_id=match_id)
            st.write(events.head())

            # Filter passes
            pass_data = events[events['type'] == 'Pass']

            # Plot passes on a soccer pitch
            st.subheader("Pass Map")
            pitch = Pitch(pitch_color='grass', line_color='white', figsize=(10, 6))
            fig, ax = pitch.draw()
            pitch.scatter(
                pass_data['location'].str[0],
                pass_data['location'].str[1],
                ax=ax,
                color='blue',
                label='Pass Start'
            )
            plt.legend()
            plt.tight_layout()
            st.pyplot(fig)

            # Button to generate PDF
            if st.button("Export Stats to PDF"):
                # Save the pass map as an image
                fig.savefig("pass_map.png")

                # Create PDF
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)

                # Add title
                pdf.cell(200, 10, txt="Match Stats Report", ln=True, align="C")

                # Add basic match info
                match_info = filtered_matches[filtered_matches['match_id'] == match_id]
                pdf.cell(200, 10, txt=f"Competition: {match_info['competition_name'].values[0]}", ln=True)
                pdf.cell(200, 10, txt=f"Date: {match_date.strftime('%d/%m/%Y')}", ln=True)
                pdf.cell(200, 10, txt=f"Match: {match_info['home_team'].values[0]} vs {match_info['away_team'].values[0]}", ln=True)

                # Add sample stats (e.g., passes)
                pdf.ln(10)
                pdf.cell(200, 10, txt="Top 5 Pass Events:", ln=True)
                for i, row in pass_data.head(5).iterrows():
                    pdf.cell(200, 10, txt=f"Player: {row['player']} | Location: {row['location']}", ln=True)

                # Add the image to the PDF
                pdf.image("pass_map.png", x=10, y=80, w=190)

                # Save PDF
                pdf_file = "match_stats_with_visualization.pdf"
                pdf.output(pdf_file)
                st.success(f"PDF saved: {pdf_file}")
                st.download_button(
                    label="Download PDF",
                    data=open(pdf_file, "rb"),
                    file_name="match_stats_with_visualization.pdf",
                    mime="application/pdf",
                )
        else:
            st.write("No matching matches found for the entered date and team.")
    except ValueError:
        st.error("Invalid date format. Please use DD/MM/YY.")