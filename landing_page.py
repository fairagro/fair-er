from fastapi.responses import HTMLResponse

def get_landing_page() -> HTMLResponse:
    return HTMLResponse("""
    <html>
        <head>
            <title>FAIR-ER - The FAIR Evaluation Repository</title>
            <link rel="icon" type="image/x-icon" href="/static/favicon.ico">
            <style>
                /* Top menu styling */
                .top-menu {
                    background-color: #6A994E;
                    padding: 10px 0;
                    text-align: center;
                }
                .top-menu a {
                    color: white;
                    text-decoration: none;
                    font-size: 1.2em;
                    margin: 0 15px;
                    font-weight: bold;
                }
                .top-menu a:hover {
                    text-decoration: underline;
                }
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: #f4f4f4;
                    color: #333;
                }
                .container {
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    text-align: center;
                }
                h1 {
                    font-size: 3em;
                    margin-bottom: 0.5em;
                }
                p {
                    font-size: 1.2em;
                    margin-bottom: 1.5em;
                    max-width: 600px;
                }
                .btn {
                    background-color: #6A994E !important;
                    color: white;
                    padding: 15px 25px;
                    font-size: 1.2em;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    text-align: center;
                    text-decoration: none;
                    transition: background-color 0.3s ease;
                    margin-top: 10px;
                }
                .btn:hover {
                    background-color: #4d7a37 !important;
                }
                footer {
                    margin-top: 2em;
                    font-size: 0.9em;
                    color: #666;
                }
                input[type="text"] {
                    padding: 10px;
                    font-size: 1.2em;
                    width: 300px;
                    border: 2px solid #6A994E;
                    border-radius: 5px;
                    margin-bottom: 20px;
                }
                form {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }
                select {
                    padding: 10px;
                    font-size: 1.2em;
                    margin-bottom: 20px;
                    border: 2px solid #6A994E;
                    border-radius: 5px;
                    width: 300px;
                }
                input[type="submit"] {
                    background-color: #6A994E;
                    color: white;
                    padding: 10px 20px;
                    font-size: 1.2em;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    transition: background-color 0.3s ease;
                    margin-top: 10px;
                }
                input[type="submit"]:hover {
                    background-color: #4d7a37;
                }
                .input-container label {
                    display: block;
                    text-align: center;
                    margin-bottom: 10px;
                    font-size: 1.2em;
                }
                .checkbox-group {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    margin-bottom: 15px;
                }
                .checkbox {
                    display: flex;
                    align-items: center;
                    justify-content: flex-start;
                    margin-bottom: 10px;
                    width: 200px;
                }
                .checkbox input {
                    transform: scale(1.5);
                    margin: 0;
                    vertical-align: middle;
                }
                .checkbox label {
                    margin-left: 10px;
                    font-size: 1.2em;
                    line-height: 1;
                    display: flex;
                    align-items: center;
                }
                .favicon-container img {
                    width: 200px;
                    height: auto;
                    margin-top: 20px;
                }
                .spinner-container {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    margin-top: 20px;
                }
                .spinner {
                    display: none;
                    border: 6px solid #f3f3f3;
                    border-radius: 50%;
                    border-top: 6px solid #6A994E;
                    width: 40px;
                    height: 40px;
                    animation: spin 2s linear infinite;
                }
                .chart-caption {
                    text-align: center;
                    font-size: 14px;
                    margin-top: 10px;
                    margin-bottom: 20px;
                    color: #555;
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        </head>
        <body>
             <!-- Top Menu -->
            <div class="top-menu">
                <a href="/">Home</a>
                <a href="https://github.com/fairagro/fair-er" target="_blank">GitHub</a>
                <a href="/docs" target="_blank" rel="noopener noreferrer">API</a>
            </div>
            <div class="container">
                <!--
                <div class="favicon-container">
                    <img src="/static/favicon_1024.ico" alt="FAIR-ER Logo">
                </div>
                -->
                <h1>Welcome to FAIR-ER</h1>
                <p>FAIR-ER, The FAIR Evaluation Repository, provides powerful tools to evaluate and interact with datasets.
                   Use our API to retrieve dataset information, perform FAIR metrics evaluations, and assess the quality of resources using DOIs.
                   Enter a DOI below to generate and download a FAIR evaluation file.</p>

                <div class="input-container">
                    <form action="/generate_dqv_summary/" method="post" onsubmit="handleFormSubmit(event)">
                        <label for="doi">Enter DOI:</label>
                        <input type="text" id="doi" name="doi" value="10.5447/ipk/2017/2" required>
                        <input type="hidden" name="fes" value="false">
                        <input type="hidden" name="fuji" value="false">
                        <div class="checkbox-group">
                            <div class="checkbox">
                                <input type="checkbox" id="fes" name="fes" value="true" checked>
                                <label for="fes">Use FES Evaluation</label>
                            </div>
                            <div class="checkbox">
                                <input type="checkbox" id="fuji" name="fuji" value="true" checked>
                                <label for="fuji">Use FUJI Evaluation</label>
                            </div>
                        </div>
                        <label for="output_format">Select Output Format:</label>
                        <select id="output_format" name="output_format">
                            <option value="ttl">Turtle (.ttl)</option>
                            <option value="jsonld">JSON-LD (.jsonld)</option>
                            <option value="xml">RDF/XML (.xml)</option>
                            <option value="n3">Notation3 (.n3)</option>
                            <option value="nt">N-Triple (.nt)</option>
                            <option value="trig">TriG (.trig, RDF triples with context)</option>
                        </select>
                        <input type="submit" class="btn" value="Generate and Download DQV File">
                    </form>
                    <div class="spinner-container">
                        <div id="spinner" class="spinner"></div>
                    </div>
                </div>
                <!-- Chart for displaying evaluation results -->
                <div style="width: 50%; max-width: 600px; margin: 0 auto; height: 400px;">
                    <canvas id="evaluationChart"></canvas>
                    <p class="chart-caption" style="margin-bottom: 20px;">Averages for each FAIR dimension</p>
                </div>
                <footer>
                    <p>&copy; 2024 FAIR-ER. All rights reserved.</p>
                </footer>
            </div>
            <script src="/static/scripts.js"></script>
            <script>
                document.addEventListener('DOMContentLoaded', (event) => {
                    initializeEmptyChart();
                });
            </script>
        </body>
    </html>
    """)
