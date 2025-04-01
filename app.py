import markdown
from flask import Flask, request, render_template, jsonify
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import os
from dotenv import load_dotenv
import google.generativeai as genai
from connect import neo4j_conn

app = Flask(__name__)

load_dotenv()
genai_api_key = os.getenv('GENAI_API_KEY')
if not genai_api_key:
    print("Error: GENAI_API_KEY not found in environment variables.")
    exit()

genai.configure(api_key=genai_api_key)

if not os.path.exists('static/graphs'):
    os.makedirs('static/graphs')

deliveries = pd.read_csv('deliveries.csv')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/player_names')
def player_names():
    try:
        query = """
        MATCH (p:Player)
        RETURN DISTINCT p.player_of_match AS player
        """
        result = neo4j_conn.query(query)
        players = [record['player'] for record in result]
        return jsonify({'players': players})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/analyze', methods=['POST'])
def analyze():
    query_type = request.form.get('query_type')
    player_name = request.form.get('player_name', '').strip()
    match_id = request.form.get('id', '').strip()
    player1 = request.form.get('player1', '').strip()
    player2 = request.form.get('player2', '').strip()
    custom_prompt = request.form.get('custom_prompt', '').strip()

    player_data = []
    knowledge_base = ""

    if query_type == 'compare':
        if not player1 or not player2 or player1 == player2:
            return render_template('result.html', result="Error: Please provide two different player names for comparison.")
        graph_path = generate_graph(player1, player2)
        return render_template('result.html', graph_url=graph_path) if graph_path else render_template('result.html', result="Error generating graph.")

    try:
        if query_type in ['situation', 'report'] and match_id:
            knowledge_base = get_match_knowledge_base(match_id)
        
        elif query_type in ['performance', 'commentary'] and player_name:
            knowledge_base = get_player_knowledge_base(player_name)
        
        if custom_prompt:
            knowledge_base = f"User's Custom Request: {custom_prompt}\n"
            
        if match_id:
            knowledge_base += f"Match Data:\n{get_match_knowledge_base(match_id)}"

        elif player_name:
            knowledge_base += f"Player Data:\n{get_player_knowledge_base(player_name)}"

        else:
            knowledge_base += "Error: No match ID or player name provided."

        print("Knowledge Base Retrieved:")
        print(knowledge_base)

    except Exception as e:
        return render_template('result.html', result=f"Error querying Neo4j: {e}")

    prompt = generate_prompt(query_type, player_name, match_id, knowledge_base, custom_prompt)

    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content(prompt)
        result_markdown = response.text.strip() if response.text else "No response generated."
        result_html = markdown.markdown(result_markdown)
    except Exception as e:
        result_html = f"<p>Error during AI generation: {e}</p>"

    return render_template('result.html', result=result_html, player_data=player_data, query_type=query_type, knowledge_base=knowledge_base)


def generate_prompt(query_type, player_name='', match_id='', knowledge_base='', custom_prompt=''):
    if query_type == 'performance':
        return (
            f"You are a cricket analyst. Perform a detailed analysis of {player_name}'s IPL career using the following match data: {knowledge_base}\n"
            f"Step 1: Identify {player_name}'s strengths and weaknesses in batting and bowling.\n"
            f"Step 2: Analyze their performance against specific bowler types, conditions, and match scenarios.\n"
            f"Step 3: Provide actionable insights on how {player_name} can improve their game."
        )

    elif query_type == 'situation':
        examples = (
            "Example 1: In a match where the target is 180 in 20 overs, the team opted for aggressive batting in the powerplay.\n"
            "Example 2: When defending a low score of 150, the captain strategically used spinners on a turning pitch.\n"
            "Example 3: With 30 runs needed off 12 balls, bowlers focused on yorkers and slower balls to restrict scoring.\n"
        )
        return (
            f"You are a cricket strategist. Based on the following examples, analyze the current match situation (Match ID: {match_id}):\n\n"
            f"{examples}\nMatch Data: {knowledge_base}\n"
            f"Provide clear tactical recommendations for the batting and bowling sides."
        )

    elif query_type == 'commentary':
        return (
            f"Act as a cricket commentator and provide expert insights into {player_name}'s performance using the following match data: {knowledge_base}\n"
            f"You can take on different roles:\n"
            f"1. Batting Coach: Analyze {player_name}'s shot selection, footwork, and mindset.\n"
            f"2. Bowling Coach: Examine how bowlers approached {player_name} and suggest improvements.\n"
            f"3. Field Strategist: Discuss fielding placements and strategies applied to counter {player_name}.\n"
            f"Provide detailed, engaging commentary with relevant cricket terminology."
        )

    elif query_type == 'report':
        return (
            f"You are a cricket journalist. Generate a detailed match report for Match ID: {match_id} using the provided data.\n"
            f"Ensure your report follows this structure:\n"
            f"1. **Match Summary:** Provide a brief overview of the match result and key moments.\n"
            f"2. **Top Performers:** Highlight standout performances from both teams.\n"
            f"3. **Turning Points:** Discuss critical moments that influenced the outcome.\n"
            f"4. **Key Statistics:** Include data such as top scorers, best bowlers, and partnership details.\n"
            f"5. **Conclusion:** Provide a brief commentary on the match's impact on the tournament.\n"
            f"Match Data: {knowledge_base}"
        )
    
    elif custom_prompt:
        return ( 
            f"\n\nUser's Custom Request: {custom_prompt}"
            f"Match Data: {knowledge_base}"
            f"Player Name: {player_name}"
        )

    else:
        return "Invalid query type. Please select a valid query."
    

def get_player_knowledge_base(player_name):
    try:
        query = """
        MATCH (m:Match)
        WHERE m.player_of_match = $player_name
        RETURN m.id AS id, m.season AS season, m.city AS city, m.date AS date, m.match_type AS match_type,
               m.player_of_match AS player_of_match, m.venue AS venue, m.team1 AS team1, m.team2 AS team2,
               m.toss_winner AS toss_winner, m.toss_decision AS toss_decision, m.winner AS winner, 
               m.result AS result, m.result_margin AS result_margin, m.target_runs AS target_runs,
               m.target_overs AS target_overs, m.super_over AS super_over, m.method AS method, 
               m.umpire1 AS umpire1, m.umpire2 AS umpire2
        """
        result = neo4j_conn.query(query, {"player_name": player_name})
        player_data = [dict(record) for record in result] if result else []
        knowledge_base = "\n".join([str(data) for data in player_data])
        return knowledge_base
    except Exception as e:
        print(f"Error querying Neo4j for player {player_name}: {e}")
        return ""

def get_match_knowledge_base(match_id):
    try:
        query = """
        MATCH (m:Match)
        WHERE m.id = $match_id
        RETURN m.id AS id, m.season AS season, m.city AS city, m.date AS date, m.match_type AS match_type,
               m.player_of_match AS player_of_match, m.venue AS venue, m.team1 AS team1, m.team2 AS team2,
               m.toss_winner AS toss_winner, m.toss_decision AS toss_decision, m.winner AS winner, 
               m.result AS result, m.result_margin AS result_margin, m.target_runs AS target_runs,
               m.target_overs AS target_overs, m.super_over AS super_over, m.method AS method, 
               m.umpire1 AS umpire1, m.umpire2 AS umpire2
        """
        result = neo4j_conn.query(query, {"match_id": match_id})
        match_data = [dict(record) for record in result] if result else []
        knowledge_base = "\n".join([str(data) for data in match_data])
        return knowledge_base
    except Exception as e:
        print(f"Error querying Neo4j for match {match_id}: {e}")
        return ""

def generate_graph(player1, player2):
    try:
        if player1 not in deliveries['batter'].values or player2 not in deliveries['batter'].values:
            print(f"Player '{player1}' or '{player2}' not found.")
            return None
        
        player1_data = deliveries[deliveries['batter'] == player1]
        player2_data = deliveries[deliveries['batter'] == player2]

        if player1_data.empty or player2_data.empty:
            print(f"No data available for {player1} or {player2}.")
            return None

        player1_runs = player1_data.groupby('match_id')['batsman_runs'].sum().reset_index()
        player2_runs = player2_data.groupby('match_id')['batsman_runs'].sum().reset_index()

        plt.figure(figsize=(10, 6))
        plt.plot(player1_runs['match_id'].to_numpy(), player1_runs['batsman_runs'].to_numpy(), label=player1, marker='o', color='blue')
        plt.plot(player2_runs['match_id'].to_numpy(), player2_runs['batsman_runs'].to_numpy(), label=player2, marker='s', color='red')
        plt.xlabel('Match ID')
        plt.ylabel('Total Runs')
        plt.title(f'{player1} vs {player2} - Performance Comparison')
        plt.legend()
        plt.grid(True)

        graph_path = f"static/graphs/{player1}_vs_{player2}.png"
        plt.savefig(graph_path)
        plt.close()

        print(f"Graph saved to {graph_path}")
        return f"/{graph_path}"

    except Exception as e:
        print(f"Error generating graph: {e}")
        return None
if __name__ == '__main__':
    app.run(debug=True)
