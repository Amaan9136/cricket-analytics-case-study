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

# environment variables
load_dotenv()
genai_api_key = os.getenv('GENAI_API_KEY')
if not genai_api_key:
    print("Error: GENAI_API_KEY not found in environment variables.")
    exit()

genai.configure(api_key=genai_api_key)

if not os.path.exists('static/graphs'):
    os.makedirs('static/graphs')

# used for graph generation
deliveries = pd.read_csv('deliveries.csv')
# matches.csv is imported in neo4j to do RAG

@app.route('/')
def index():
    return render_template('index.html')

# get All Player Names
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

# analyze or Compare Players with display
@app.route('/analyze', methods=['POST'])
def analyze():
    query_type = request.form.get('query_type')
    player_name = request.form.get('player_name', '').strip()
    id = request.form.get('id', '').strip()
    player1 = request.form.get('player1', '').strip()
    player2 = request.form.get('player2', '').strip()

    # comparison
    if query_type == 'compare':
        if not player1 or not player2:
            return render_template('result.html', result="Error: Both player names are required for comparison.")
        graph_path = generate_graph(player1, player2)
        return render_template('result.html', graph_url=graph_path) if graph_path else render_template('result.html', result="Error generating graph.")
    
    player_data = []
    knowledge_base = ""

    if player_name:
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
            
            if result:
                player_data = [{"id": record['id'], 
                                "season": record['season'], 
                                "city": record['city'],
                                "date": record['date'],
                                "match_type": record['match_type'],
                                "player_of_match": record['player_of_match'],
                                "venue": record['venue'],
                                "team1": record['team1'],
                                "team2": record['team2'],
                                "toss_winner": record['toss_winner'],
                                "toss_decision": record['toss_decision'],
                                "winner": record['winner'],
                                "result": record['result'],
                                "result_margin": record['result_margin'],
                                "target_runs": record['target_runs'],
                                "target_overs": record['target_overs'],
                                "super_over": record['super_over'],
                                "method": record['method'],
                                "umpire1": record['umpire1'],
                                "umpire2": record['umpire2']} for record in result]
                
                # knowledge base from player data for RAG
                knowledge_base = "\n".join([f"Match {data['id']} - {data['team1']} vs {data['team2']}: {data['result']} ({data['result_margin']})" for data in player_data])
                print("Knowledge Base:", knowledge_base)
            else:
                return render_template('result.html', result=f"No data found for player: {player_name}")
        except Exception as e:
            return render_template('result.html', result=f"Error querying Neo4j: {e}")

    # AI Prompt with Knowledge Base for RAG
    prompt = generate_prompt(query_type, player_name, id, knowledge_base)
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content(prompt)
        result_markdown = response.text.strip() if response.text else "No response generated."
        result_html = markdown.markdown(result_markdown)
    except Exception as e:
        result_html = f"<p>Error during AI generation: {e}</p>"

    return render_template('result.html', result=result_html, player_data=player_data)

# Generate AI Prompt based on query type with Knowledge Base
def generate_prompt(query_type, player_name='', id='', knowledge_base=''):
    if query_type == 'performance':
        return f"Analyze {player_name}'s IPL career, evaluating batting and bowling stats. Here is the match history: {knowledge_base}"
    elif query_type == 'situation':
        return f"Provide strategic recommendations for match {id}. Here is the match history: {knowledge_base}"
    elif query_type == 'commentary':
        return f"Simulate expert commentary for {player_name}. Here is the match history: {knowledge_base}"
    elif query_type == 'report':
        return f"Generate a match report for Match ID: {id}. Here is the match history: {knowledge_base}"
    else:
        return f"Invalid query type. Please select a valid query."

def generate_graph(player1, player2):
    try:
        if player1 not in deliveries['batter'].values or player2 not in deliveries['batter'].values:
            print(f"Player '{player1}' or '{player2}' not found.")
            return None
        
        player1_data = deliveries[deliveries['batter'] == player1]
        player2_data = deliveries[deliveries['batter'] == player2]

        # if any data is found for either player
        if player1_data.empty or player2_data.empty:
            print(f"No data available for {player1} or {player2}.")
            return None

        # total runs for each player grouped by match_id
        player1_runs = player1_data.groupby('match_id')['batsman_runs'].sum().reset_index()
        player2_runs = player2_data.groupby('match_id')['batsman_runs'].sum().reset_index()

        # the total runs by match_id for both players
        plt.figure(figsize=(10, 6))
        plt.plot(player1_runs['match_id'].to_numpy(), player1_runs['batsman_runs'].to_numpy(), label=player1, marker='o', color='blue')
        plt.plot(player2_runs['match_id'].to_numpy(), player2_runs['batsman_runs'].to_numpy(), label=player2, marker='s', color='red')
        plt.xlabel('Match ID')
        plt.ylabel('Total Runs')
        plt.title(f'{player1} vs {player2} - Performance Comparison')
        plt.legend()
        plt.grid(True)

        # the graph to a file
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
