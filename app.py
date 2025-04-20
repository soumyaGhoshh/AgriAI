import os
from datetime import datetime
from io import BytesIO
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import google.generativeai as genai
import requests
from dotenv import load_dotenv
from flask import send_from_directory


# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
app.config.update({
    'UPLOAD_FOLDER': os.getenv('UPLOAD_FOLDER', '/tmp/uploads'),  # Default to writable `/tmp` in GAE
    'MAX_CONTENT_LENGTH': int(os.getenv('MAX_UPLOAD_SIZE', 5 * 1024 * 1024)),
    'ALLOWED_EXTENSIONS': {'png', 'jpg', 'jpeg'},
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
})

# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Environment variables
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)
ai_models = {
    'text': genai.GenerativeModel('gemini-1.5-pro'),
    'vision': genai.GenerativeModel('gemini-1.5-flash')
}


SYSTEM_PROMPT = """<system>
You are Krishi Bandhu, an AI agricultural expert for small farmers in India. Follow these rules:

1. Language Matching: Respond in the same language as the query, primarily English
2. Response Depth:
   - Simple queries (greetings, yes/no): 1-line response
   - Basic questions: 2-3 line summary + ► Details
   - Complex questions: Detailed steps + resources

3. Never show ► Details for:
   - Greetings
   - Simple questions
   - Yes/no answers
   - Weather greetings

4. Structure:
   <response>
   <summary>[Concise answer]</summary>
   <details>[Optional elaboration]</details>
   <resources>[Relevant schemes/links]</resources>
   </response>

Focus Areas:
- Climate-resilient crops (wheat, rice, pulses)
- Soil health (sandy loam soils of Siddharthnagar)
- Water conservation (drip irrigation)
- Pest management (IPM for regional pests)
- Government schemes (PM-KISAN, Soil Health Card)
- Market prices (local mandi rates)

Regional Data:
- Avg rainfall: 980mm | Temp range: 8°C-45°C
- Common crops: Rice, Wheat, Lentils, Mustard
- Soil type: Alluvial (Gangetic plains)

Current Date: {date}
</system>
"""
SCAN_PROMPT = """<system>
You are an agricultural image analysis expert. Analyze uploaded crop images and provide:

1. Crop Identification (common & scientific name)
2. Disease Detection (if any)
3. Growth Stage Analysis
4. Seasonal Suitability (for Uttar Pradesh)
5. Care Recommendations
6. Yield Optimization Tips

Format response:
<response>
<identification>
[Species Name]
[Common Names]
</identification>
<analysis>
[Health Status]
[Growth Stage]
[Seasonal Compatibility]
</analysis>
<recommendations>
[Care Instructions]
[Prevention Measures]
</recommendations>
<seasonal>
[Best Season]
[Yield Tips]
</seasonal>
</response>
</system>
""" 

SOIL_PROMPT = """<system>
You are an agricultural soil analysis expert. Analyze soil sample images and provide:

1. Soil Type Classification (per USDA system)
2. Texture Analysis (sand/silt/clay percentages)
3. Color Identification (Munsell system)
4. Nutrient Deficiency Detection (N/P/K)
5. pH Level Estimation
6. Organic Matter Content
7. Improvement Recommendations

Format response:
<response>
<classification>
[Soil Type]
[Texture Class]
</classification>
<composition>
[Sand %]
[Silt %]
[Clay %]
</composition>
<properties>
[Color (Munsell)]
[pH Estimate]
[Organic Matter]
</properties>
<nutrients>
[Nitrogen Status]
[Phosphorus Status]
[Potassium Status]
</nutrients>
<recommendations>
[Fertilization Tips]
[Soil Amendment]
[Crop Suggestions]
</recommendations>
</response>
</system>
"""    

def handle_file_upload(file_field: str) -> tuple:
    """Handle common file upload validation and processing"""
    if file_field not in request.files:
        return None, jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files[file_field]
    if not file or file.filename == '':
        return None, jsonify({'error': 'No selected file'}), 400

    if not allowed_file(file.filename):
        return None, jsonify({'error': 'Invalid file type'}), 400

    if not validate_image(file.stream):
        return None, jsonify({'error': 'Invalid image file'}), 400

    file.stream.seek(0)
    return file, None, None

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_image(file_stream) -> bool:
    """Validate image file integrity"""
    try:
        with Image.open(BytesIO(file_stream.read())) as img:
            img.thumbnail((1, 1))
        file_stream.seek(0)
        return True
    except Exception as e:
        app.logger.error(f"Image validation error: {str(e)}")
        file_stream.seek(0)
        return False

def process_forecast(data: dict) -> list:
    """Process weather forecast data"""
    daily_data = {}
    for item in data['list']:
        date = item['dt_txt'].split()[0]
        daily_data.setdefault(date, {
            'temp_min': item['main']['temp_min'],
            'temp_max': item['main']['temp_max'],
            'humidity': item['main']['humidity'],
            'wind_speed': item['wind']['speed'],
            'rain': item.get('rain', {}).get('3h', 0),
            'description': item['weather'][0]['description'],
            'icon': item['weather'][0]['icon']
        })
        daily_data[date].update({
            'temp_min': min(daily_data[date]['temp_min'], item['main']['temp_min']),
            'temp_max': max(daily_data[date]['temp_max'], item['main']['temp_max']),
            'rain': daily_data[date]['rain'] + item.get('rain', {}).get('3h', 0)
        })
    
    return [{
        'date': date,
        'temp_min': values['temp_min'],
        'temp_max': values['temp_max'],
        'rain': round(values['rain'], 1),
        'wind_speed': values['wind_speed'],
        'description': values['description'],
        'icon': values['icon']
    } for date, values in list(daily_data.items())[1:5]]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.method == 'POST':
        try:
            data = request.get_json()
            prompt = SYSTEM_PROMPT.format(date=datetime.now().strftime("%d %B %Y")) + \
                    f"\n\nUser: {data['message']}\nKrishi Bandhu:"
            response = ai_models['text'].generate_content(prompt)
            return jsonify({'response': response.text.replace("**", "").replace("<response>", "").replace("</response>", "")})
        except Exception as e:
            app.logger.error(f"Chat error: {str(e)}")
            return jsonify({'error': str(e)}), 500
    return render_template('chat.html')

@app.route('/analyze', methods=['POST'])
def analyze_image():
    file, error, code = handle_file_upload('file')
    if error:
        return error, code
    
    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        response = ai_models['vision'].generate_content([SCAN_PROMPT, genai.upload_file(file_path)])
        return jsonify({'response': response.text})
    except Exception as e:
        app.logger.error(f"Image analysis error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.route('/analyze_soil', methods=['POST'])
def analyze_soil():
    file, error, code = handle_file_upload('file')
    if error:
        return error, code
    
    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        response = ai_models['vision'].generate_content([SOIL_PROMPT, genai.upload_file(file_path)])
        return jsonify({'response': response.text})
    except Exception as e:
        app.logger.error(f"Soil analysis error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.route('/get_weather', methods=['GET', 'POST'])
def get_weather():
    try:
        if request.method == 'POST':
            city = request.get_json().get('city', '').strip()
            if not city:
                return jsonify({'error': 'City name required'}), 400
            
            geo_response = requests.get(
                f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={WEATHER_API_KEY}"
            ).json()
            
            if not geo_response:
                return jsonify({'error': 'City not found'}), 404
            
            lat, lon = geo_response[0]['lat'], geo_response[0]['lon']
        else:
            lat, lon = request.args.get('lat'), request.args.get('lon')
            if not (lat and lon):
                return jsonify({'error': 'Coordinates required'}), 400

        current_data = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        ).json()
        
        return jsonify({
            'current': {
                'city': current_data.get('name', 'Unknown Location'),
                'temp': current_data['main']['temp'],
                'feels_like': current_data['main']['feels_like'],
                'humidity': current_data['main']['humidity'],
                'wind_speed': current_data['wind']['speed'],
                'description': current_data['weather'][0]['description'],
                'icon': current_data['weather'][0]['icon']
            },
            'forecast': process_forecast(requests.get(
                f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
            ).json())
        })
    except Exception as e:
        app.logger.error(f"Weather error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_shops', methods=['GET'])
def get_nearby_shops():
    try:
        lat, lng = request.args.get('lat'), request.args.get('lng')
        if not (lat and lng):
            return jsonify({'error': 'Coordinates required'}), 400

        response = requests.get(
            f"https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                'location': f"{lat},{lng}",
                'radius': 5000,
                'keyword': 'fertilizer',
                'type': 'store',
                'key': GOOGLE_MAPS_API_KEY
            }
        ).json()
        
        return jsonify({'shops': [{
            'name': p.get('name'),
            'address': p.get('vicinity'),
            'rating': p.get('rating'),
            'open': p.get('opening_hours', {}).get('open_now'),
            'location': p.get('geometry', {}).get('location')
        } for p in response.get('results', [])]})
    except Exception as e:
        app.logger.error(f"Shop lookup error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Other routes remain unchanged
@app.route('/scan')
def scan(): return render_template('scan.html')

@app.route('/weather')
def weather(): return render_template('weather.html')

@app.route('/fertilizer')
def fertilizer_shops(): return render_template('fertilizer.html')

@app.route('/about')
def about(): return render_template('about.html')

@app.route('/faq')
def faq(): return render_template('faq.html')

@app.route('/soil')
def soil(): return render_template('soil.html')

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')