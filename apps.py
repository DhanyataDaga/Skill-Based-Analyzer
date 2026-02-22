import os
import json
import PyPDF2
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
from googleapiclient.discovery import build

app = Flask(__name__)

# ==========================================
# 🔑 PASTE YOUR API KEYS HERE (INSIDE QUOTES)
# ==========================================
# REPLACE YOUR REAL KEYS WITH THESE PLACEHOLDERS
GEMINI_API_KEY = "PASTE YOUR API KEY HERE"
YOUTUBE_API_KEY = "PASTE YOUR API KEY HERE"
SEARCH_ENGINE_ID = "PASTE YOUR SEARCH ID HERE"
# ==========================================

# 2. CONFIGURE APIs
try:
    # Google Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # YouTube API
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

    # Google Search API (For Courses)
    search_service = build('customsearch', 'v1', developerKey=YOUTUBE_API_KEY) 
    
    print("✅ All APIs Configured Successfully")

except Exception as e:
    print(f"⚠️ API Setup Warning: {e}")

# --- HELPER FUNCTION: GET VIDEO (Safe Version) ---
# --- REPLACE YOUR get_youtube_video FUNCTION WITH THIS ---

def get_youtube_video(query):
    """
    1. Tries to search YouTube for the specific skill.
    2. If successful, returns the REAL video.
    3. If Quota Exceeded or Error, returns the Safe Fallback.
    """
    SAFE_VIDEO = "https://www.youtube.com/embed/zJSY8tbf_ys" 

    try:
        # If no query comes in, just return safe video
        if not query: return SAFE_VIDEO

        print(f"🔎 Searching YouTube for: {query}")

        # --- REAL API SEARCH ---
        req = youtube.search().list(
            q=query, 
            part='snippet', 
            type='video', 
            maxResults=1,
            videoEmbeddable='true' # Important: Only get videos that allow embedding
        )
        res = req.execute()

        # --- CHECK RESULTS ---
        if 'items' in res and len(res['items']) > 0:
            # ✅ SUCCESS: Found a specific video!
            vid_id = res['items'][0]['id']['videoId']
            return f"https://www.youtube.com/embed/{vid_id}"
        else:
            # ❌ FOUND NOTHING: Use Fallback
            print(f"⚠️ No results for '{query}'. Using Fallback.")
            return SAFE_VIDEO

    except Exception as e:
        # ❌ QUOTA / API ERROR: Use Fallback
        print(f"⚠️ YouTube Error ({e}). Using Fallback.")
        return SAFE_VIDEO

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        # 1. READ FILES
        resume_file = request.files['resume']
        job_desc = request.form['job_desc']

        # Extract Text from PDF
        reader = PyPDF2.PdfReader(resume_file)
        resume_text = ""
        for page in reader.pages:
            resume_text += page.extract_text()

        # 2. ASK GEMINI (Dynamic Analysis)
        print("🤖 Asking Gemini...")
        prompt = f"""
        Act as a Tech Recruiter. 
        RESUME: {resume_text}
        JOB DESC: {job_desc}
        
        1. Identify MISSING skills vs MATCHED skills.
        2. Create a SINGLE consolidated 4-week "Learning Roadmap".
        
        Return ONLY valid JSON:
        {{
            "match_score": (integer 0-100),
            "summary": "1 sentence summary",
            "matched_skills": ["Skill1", "Skill2"],
            "missing_skills": [
                {{ "skill": "Skill Name", "reason": "Why needed", "search_term": "YouTube search query" }}
            ],
            "roadmap": [
                {{ "step": "Week 1", "task": "Title", "details": "Description" }},
                {{ "step": "Week 2", "task": "Title", "details": "Description" }},
                {{ "step": "Week 3", "task": "Title", "details": "Description" }},
                {{ "step": "Week 4", "task": "Title", "details": "Description" }}
            ]
        }}
        """

        # Call Gemini
        response = model.generate_content(prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(clean_json)

        # 3. FETCH MEDIA (YouTube & Courses)
        # This part runs dynamically based on what Gemini found
        for item in analysis.get('missing_skills', []):
            skill_name = item['skill']
            
            # A. Get Video (Uses the safe helper)
            item['video_url'] = get_youtube_video(item.get('search_term', skill_name))

            # B. Get Course (Udemy/Coursera Search)
            try:
                search_query = f"site:udemy.com {skill_name} complete course"
                search_res = search_service.cse().list(
                    q=search_query, 
                    cx=SEARCH_ENGINE_ID, 
                    num=1
                ).execute()

                if 'items' in search_res:
                    course = search_res['items'][0]
                    item['course_title'] = course['title'].replace(" | Udemy", "")
                    item['course_link'] = course['link']
                    item['course_source'] = "Udemy"
                    
                    # Try to get image
                    pagemap = course.get('pagemap', {})
                    if 'cse_image' in pagemap:
                        item['course_img'] = pagemap['cse_image'][0]['src']
                    else:
                        item['course_img'] = "https://www.udemy.com/staticx/udemy/images/v7/logo-udemy.svg"
                else:
                    raise Exception("No course found")

            except Exception:
                # Fallback Course Link if API fails
                item['course_title'] = f"Browse {skill_name} Courses"
                item['course_link'] = f"https://www.udemy.com/courses/search/?q={skill_name}"
                item['course_source'] = "Udemy"
                item['course_img'] = "https://www.udemy.com/staticx/udemy/images/v7/logo-udemy.svg"

        return jsonify(analysis)

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)