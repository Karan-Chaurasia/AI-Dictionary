from flask import Flask, render_template_string, request, jsonify
import requests
import re
import logging
from spellchecker import SpellChecker  # For spell correction

# Enable debug logging to terminal
logging.basicConfig(level=logging.DEBUG)

# Initialize spell checker globally (loads once)
spell = SpellChecker()

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Quick Context Finder</title>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: #f8f9fa;
            margin: 0;
            padding: 10px;
            min-height: 100vh;
            color: #333;
        }
        .container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            max-width: 600px;
            margin: 0 auto;
            text-align: center;
        }
        .search-form {
            position: relative;
            margin-bottom: 20px;
        }
        input[type="text"] {
            padding: 12px;
            width: 100%;
            max-width: 400px;
            border: 2px solid #ddd;
            border-radius: 6px;
            font-size: 16px;
        }
        input:focus {
            border-color: #007bff;
            outline: none;
        }
        button {
            padding: 12px 20px;
            border: none;
            border-radius: 6px;
            background: #007bff;
            color: white;
            cursor: pointer;
            font-size: 16px;
            margin-left: 10px;
        }
        button:hover:not(:disabled) {
            background: #0056b3;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .loading {
            display: none;
            margin: 20px 0;
            color: #007bff;
            font-style: italic;
        }
        .result {
            margin-top: 20px;
            text-align: left;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }
        .error {
            color: #dc3545;
            background: #f8d7da;
            border-left-color: #dc3545;
        }
        .formula-result {
            text-align: center;
        }
        .formula-render {
            font-size: 20px;
            margin: 15px 0;
            padding: 10px;
            background: #fff;
            border-radius: 6px;
        }
        .correction-note {
            background: #d4edda;
            padding: 8px;
            border-radius: 4px;
            color: #155724;
            margin-bottom: 10px;
            font-style: italic;
        }
        h1 {
            margin-bottom: 20px;
            color: #333;
        }
        h3 {
            color: #007bff;
            margin-top: 0;
        }
        ul, ol {
            padding-left: 20px;
        }
        li {
            margin-bottom: 5px;
        }
        .history {
            margin-top: 20px;
            text-align: left;
            font-size: 14px;
            color: #666;
        }
        .suggestions {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            border: 1px solid #ddd;
            border-radius: 6px;
            max-height: 150px;
            overflow-y: auto;
            z-index: 1000;
            display: none;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .suggestion-item {
            padding: 10px;
            cursor: pointer;
        }
        .suggestion-item:hover {
            background: #f8f9fa;
        }
        @media (max-width: 600px) {
            .container { padding: 15px; }
            input[type="text"] { max-width: none; margin-bottom: 10px; }
            button { width: 100%; margin-left: 0; margin-top: 10px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AI Dictionary 📚</h1>
        <form id="searchForm" class="search-form" method="POST" action="/">
            <input type="text" id="searchInput" name="word" placeholder="Enter a word, recipe, or formula (e.g., x^2 + y^2 = z^2)..." required>
            <div id="suggestions" class="suggestions"></div>
            <br>
            <button type="submit" id="searchBtn">Search</button>
        </form>
        <div id="loading" class="loading">Searching... 🔍</div>

        {% if word %}
            <div id="result" class="result">
                {% if correction_message %}
                    <div class="correction-note">{{ correction_message }}</div>
                {% endif %}
                {% if formula_detected %}
                    <div class="formula-result">
                        <h3>Formula Detected: {{ word }}</h3>
                        <div class="formula-render">$${{ formula_latex }}$$</div>
                        <p><strong>Explanation:</strong> This is a mathematical expression rendered accurately using LaTeX. For solving specific values, use a calculator or math tool.</p>
                    </div>
                {% elif recipe %}
                    <h3>Recipe: {{ recipe.title }}</h3>
                    {% if recipe.ingredients %}
                        <strong>Ingredients:</strong>
                        <ul>
                            {% for ing in recipe.ingredients %}
                                <li>{{ ing }}</li>
                            {% endfor %}
                        </ul>
                    {% endif %}
                    <strong>Instructions:</strong>
                    <p>{{ recipe.instructions | replace('\n', '<br>') | safe }}</p>
                {% elif definitions %}
                    <strong>{{ word.title() }}:</strong>
                    <ol>
                        {% for d in definitions %}
                            <li>{{ d }}</li>
                        {% endfor %}
                    </ol>
                {% elif error %}
                    <strong>Error:</strong> {{ error }}
                {% else %}
                    No results found. Try another query!
                {% endif %}
            </div>
        {% endif %}

        <div id="history" class="history" style="display: none;">
            <strong>Recent Searches:</strong>
            <ul id="historyList"></ul>
        </div>
    </div>

    <script>
        // Fallback for no JS: Form works normally
        let searchHistory = JSON.parse(localStorage.getItem('searchHistory')) || [];
        const suggestionsData = ['apple', 'pasta', 'chicken', 'love', 'run', 'pythagoras', 'quadratic'];

        function showSuggestions(input) {
            const inputVal = input.toLowerCase();
            const suggestionsDiv = document.getElementById('suggestions');
            suggestionsDiv.innerHTML = '';
            if (inputVal.length < 2) {
                suggestionsDiv.style.display = 'none';
                return;
            }
            const filtered = suggestionsData.filter(word => word.startsWith(inputVal));
            if (filtered.length > 0) {
                filtered.forEach(word => {
                    const item = document.createElement('div');
                    item.className = 'suggestion-item';
                    item.textContent = word;
                    item.onclick = () => {
                        document.getElementById('searchInput').value = word;
                        suggestionsDiv.style.display = 'none';
                        document.getElementById('searchForm').submit();
                    };
                    suggestionsDiv.appendChild(item);
                });
                suggestionsDiv.style.display = 'block';
            } else {
                suggestionsDiv.style.display = 'none';
            }
        }

        const searchInput = document.getElementById('searchInput');
        searchInput.addEventListener('input', (e) => showSuggestions(e.target.value));
        searchInput.addEventListener('focus', () => showSuggestions(searchInput.value));

        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-form')) {
                document.getElementById('suggestions').style.display = 'none';
            }
        });

        function addToHistory(query) {
            if (!searchHistory.includes(query)) {
                searchHistory.unshift(query);
                if (searchHistory.length > 5) searchHistory.pop();
                localStorage.setItem('searchHistory', JSON.stringify(searchHistory));
                updateHistory();
            }
        }

        function updateHistory() {
            const historyDiv = document.getElementById('history');
            const historyList = document.getElementById('historyList');
            historyList.innerHTML = '';
            if (searchHistory.length > 0) {
                historyDiv.style.display = 'block';
                searchHistory.forEach(item => {
                    const li = document.createElement('li');
                    li.textContent = item;
                    li.style.cursor = 'pointer';
                    li.style.color = '#007bff';
                    li.onclick = () => {
                        searchInput.value = item;
                        document.getElementById('searchForm').submit();
                    };
                    historyList.appendChild(li);
                });
            }
        }

        // Intercept form for AJAX (if JS enabled)
        document.getElementById('searchForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const query = searchInput.value.trim();
            if (!query) return;

            addToHistory(query);
            const loading = document.getElementById('loading');
            let result = document.getElementById('result');
            if (!result) {
                result = createResultDiv();
            }
            const btn = document.getElementById('searchBtn');
            loading.style.display = 'block';
            result.innerHTML = '';
            btn.disabled = true;

            try {
                const formData = new FormData();
                formData.append('word', query);
                const response = await fetch('/', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();

                let resultHtml = '';
                let isError = false;
                if (data.correction_message) {
                    resultHtml += `<div class="correction-note">${data.correction_message}</div>`;
                }
                if (data.formula_detected) {
                    resultHtml += `
                        <div class="formula-result">
                            <h3>Formula: ${data.original_word || query}</h3>
                            <div class="formula-render">$${data.formula_latex || query}$$</div>
                            <p><strong>Explanation:</strong> Mathematical expression rendered precisely.</p>
                        </div>
                    `;
                } else if (data.recipe) {
                    resultHtml += `
                        <h3>Recipe: ${data.recipe.title}</h3>
                        ${data.recipe.ingredients ? `<strong>Ingredients:</strong><ul>${data.recipe.ingredients.map(ing => `<li>${ing}</li>`).join('')}</ul>` : ''}
                        <strong>Instructions:</strong><p>${data.recipe.instructions.replace(/\n/g, '<br>')}</p>
                    `;
                } else if (data.definitions && data.definitions.length > 0) {
                    const displayWord = data.corrected_word || data.original_word || query;
                    resultHtml += `<strong>${displayWord}:</strong><ol>${data.definitions.map(d => `<li>${d}</li>`).join('')}</ol>`;
                } else if (data.error) {
                    resultHtml += `<strong>Error:</strong> ${data.error}`;
                    isError = true;
                } else {
                    resultHtml += 'No results found. Try a different query!';
                }

                result.innerHTML = resultHtml;
                result.className = isError ? 'result error' : 'result';
            } catch (err) {
                result.innerHTML = '<strong>Error:</strong> Connection issue. Please refresh and try again.';
                result.className = 'result error';
                console.error('Search error:', err);
            } finally {
                loading.style.display = 'none';
                btn.disabled = false;
                document.getElementById('suggestions').style.display = 'none';
            }
        });

        function createResultDiv() {
            const div = document.createElement('div');
            div.id = 'result';
            div.className = 'result';
            document.querySelector('.container').insertBefore(div, document.getElementById('history') || null);
            return div;
        }

        // Init history
        updateHistory();
    </script>
</body>
</html>
"""

# --------- Spoonacular API for recipes ---------
SPOONACULAR_API_KEY = "YOUR_API_KEY_HERE"  # MUST REPLACE WITH REAL KEY FOR RECIPES!

FOOD_KEYWORDS = {'soup', 'salad', 'cake', 'pasta', 'chicken', 'pizza', 'burger', 'sushi', 'taco', 'curry', 'apple', 'banana'}

def is_food_related(word):
    word_lower = word.lower()
    return word_lower in FOOD_KEYWORDS or any(kw in word_lower for kw in FOOD_KEYWORDS)

def get_food_recipe(word):
    if not SPOONACULAR_API_KEY or SPOONACULAR_API_KEY == "YOUR_API_KEY_HERE":
        return {"error": "Recipe feature requires a valid Spoonacular API key. Definitions and formulas still work!"}
    if not is_food_related(word):
        return None
    try:
        url = f"https://api.spoonacular.com/recipes/complexSearch?query={word}&number=1&addRecipeInformation=true&apiKey={SPOONACULAR_API_KEY}"
        response = requests.get(url, timeout=10)
        logging.debug(f"Recipe API response status: {response.status_code}")
        if response.status_code == 401:
            return {"error": "Invalid Spoonacular API key. Please update it in the code."}
        if response.status_code != 200:
            return {"error": f"Recipe search failed (status: {response.status_code})."}
        data = response.json()
        if data.get("results"):
            recipe = data["results"][0]
            ingredients = [i.get("original", "").strip() for i in recipe.get("extendedIngredients", []) if i.get("original")]
            instructions = recipe.get("instructions", "No instructions available.").replace('\n', ' ')
            return {
                "title": recipe.get("title", f"{word.title()} Recipe"),
                "ingredients": ingredients[:10],  # Limit for brevity
                "instructions": instructions
            }
        return None
    except Exception as e:
        logging.error(f"Recipe error: {e}")
        return {"error": f"Recipe search unavailable: {str(e)}"}

# --------- Dictionary API ---------
def get_definitions(word):
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(url, timeout=10)
        logging.debug(f"Dictionary API status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            definitions = []
            for meaning in data[0].get("meanings", [])[:2]:
                pos = meaning.get("partOfSpeech", "n.")
                for defn in meaning.get("definitions", [])[:2]:
                    text = defn.get("definition", "").strip()
                    if text:
                        definitions.append(f"{pos}: {text}")
            return definitions if definitions else ["No exact definition found."]
        return ["Word not found in dictionary."]
    except Exception as e:
        logging.error(f"Definition error: {e}")
        return ["Unable to fetch definition at this time."]

# --------- Formula Detection ---------
def detect_formula(query):
    math_keywords = ['formula', 'equation', 'pythagoras', 'quadratic', 'integral']
    math_symbols = r'[\+\-\*/=^∫∑√\$\$\{\}\$\$]'
    if re.search(math_symbols, query) or any(kw in query.lower() for kw in math_keywords):
        # Basic LaTeX escaping (accurate for common cases)
        latex = re.sub(r'\^(\d+)', r'^{\1}', query)  # e.g., x^2 -> x^{2}
        latex = latex.replace('**', '')  # Remove any Python-style exponents
        latex = re.sub(r'\\', r'\\\\', latex)  # Escape backslashes if any
        return {"formula_detected": True, "formula_latex": latex}
    return None

# --------- Routes ---------
@app.route("/", methods=["GET"])
def home_get():
    """Serve the initial HTML template (empty form)."""
    return render_template_string(HTML_TEMPLATE)

@app.route("/", methods=["POST"])
def home_post():
    """Process search query and return JSON for AJAX (or render HTML for fallback)."""
    original_word = request.form.get("word", "").strip()  # Keep original case for display
    word = original_word.lower()  # For processing
    corrected_word = word  # Default to original
    correction_message = None

    if not word:
        if request.headers.get('Accept') == 'application/json':  # AJAX request
            return jsonify({"error": "No query provided."})
        else:  # Fallback form submit
            return render_template_string(HTML_TEMPLATE, word=original_word, error="No query provided.")

    # Spell Correction Logic (skip for formulas)
    formula_data = detect_formula(word)
    if not formula_data:  # Only correct if not a formula
        if len(word) < 15 and re.match(r'^[a-zA-Z\s]+$', word):  # Only correct short alphabetic words (skip symbols/numbers)
            corrected_word = spell.correction(word)
            if corrected_word and corrected_word != word:
                logging.debug(f"Spell correction: '{word}' -> '{corrected_word}'")
                correction_message = f"Did you mean '{corrected_word.title()}'? Using it for search."
                word = corrected_word  # Use corrected for APIs

    # Detect formula first (priority for math queries) - use corrected if applicable
    if formula_data:
        response_data = {
            "original_word": original_word,
            "corrected_word": corrected_word if corrected_word != original_word.lower() else None,
            "correction_message": correction_message
        }
        response_data.update(formula_data)
        if request.headers.get('Accept') == 'application/json':
            return jsonify(response_data)
        else:
            return render_template_string(HTML_TEMPLATE, 
                                        word=original_word, 
                                        corrected_word=corrected_word if corrected_word != original_word.lower() else None,
                                        correction_message=correction_message,
                                        formula_detected=formula_data["formula_detected"], 
                                        formula_latex=formula_data["formula_latex"])

    # Try recipe if food-related (use corrected word)
    recipe = get_food_recipe(word)
    if isinstance(recipe, dict) and "error" in recipe:
        error = recipe["error"]
        recipe = None
    else:
        error = None

    # Fallback to definitions if no recipe (use corrected word)
    definitions = None
    if not recipe:
        definitions = get_definitions(word)

    # Prepare response
    if request.headers.get('Accept') == 'application/json':  # AJAX
        response_data = {
            "original_word": original_word,
            "corrected_word": corrected_word if corrected_word != original_word.lower() else None,
            "correction_message": correction_message
        }
        if recipe:
            response_data["recipe"] = recipe
        elif definitions and len(definitions) > 0:
            response_data["definitions"] = definitions
        elif error:
            response_data["error"] = error
        else:
            response_data["error"] = "No relevant results found."
        return jsonify(response_data)
    else:  # Fallback: Render HTML with results
        return render_template_string(HTML_TEMPLATE, 
                                    word=original_word, 
                                    corrected_word=corrected_word if corrected_word != original_word.lower() else None,
                                    correction_message=correction_message,
                                    recipe=recipe, 
                                    definitions=definitions, 
                                    error=error)

# --------- Run App ---------
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
