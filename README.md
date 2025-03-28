## **Tech Stack**
- **Python (Flask)** for API and Web App
- **Neo4j** for Knowledge Graph
- **FAISS or Chroma** for Vector Search (optional)
- **Gemini** for Generation
- **Matplotlib** for Visualizations

## **Steps to Implement RAG with Knowledge Graph**

### 1. **Set up Neo4j for the Knowledge Graph**
- Install Neo4j using Docker or directly:
```bash
docker pull neo4j
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j
```
- Go to `http://localhost:7474` and log in with the username `neo4j` and password `password`.

---

### 2. **Create a Knowledge Graph Schema**


---

### 3. **Connect to Neo4j in Python**  
Install the necessary packages:
```bash
pip install neo4j pandas matplotlib flask google-generativeai
```
TO ADD DATA TO DOCKER CONTAINER OF NEO4J
```bash
docker cp "C:\Users\Amaan M k\OneDrive\Desktop\Kreat Task RAG\matches.csv" neo4j:/var/lib/neo4j/import/
docker cp "C:\Users\Amaan M k\OneDrive\Desktop\Kreat Task RAG\deliveries.csv" neo4j:/var/lib/neo4j/import/
```

TEST FILES ADDED:
```bash
docker exec -it neo4j ls -l /var/lib/neo4j/import/
```

IN NEO4J :
```cypher
LOAD CSV WITH HEADERS FROM 'file:///matches.csv' AS row
MERGE (m:Match {id: row.id})
SET m.date = row.date, m.team1 = row.team1, m.team2 = row.team2, m.venue = row.venue;
```
