import spacy
import fitz  # PyMuPDF
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Path to the trained NER model
MODEL_PATH = os.path.join("data", "model")

# Load the NER model
try:
    nlp = spacy.load(MODEL_PATH)
except:
    # Fallback to English model if custom model not available
    nlp = spacy.load("en_core_web_sm")
    print("Warning: Custom NER model not found, using default English model")

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file."""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text("text") + "\n"  # Extract text from each page
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        text = "Error: Could not extract text from PDF"
    return text

def extract_entities_from_text(text):
    """Extract entities from text using the trained NER model."""
    doc = nlp(text)
    entities = {}
    
    for ent in doc.ents:
        if ent.label_ not in entities:
            entities[ent.label_] = set()  # Store values as sets to ensure uniqueness
        entities[ent.label_].add(ent.text.lower())  # Store lowercase for consistency
    
    # Convert sets back to lists for JSON serialization
    return {key: list(values) for key, values in entities.items()}

def rank_cvs_by_similarity(cv_texts, job_entities, keyword_weights):
    """Rank multiple CVs by their similarity to the job description."""
    # Extract entities from all CVs
    cv_entities_list = []
    for cv_text in cv_texts:
        cv_entities = extract_entities_from_text(cv_text)
        cv_entities_list.append(cv_entities)
    
    # Calculate similarity scores
    ranked_cvs = []
    for i, cv_entities in enumerate(cv_entities_list):
        # Convert entities to text for TF-IDF
        cv_text = " ".join([" ".join(values) for values in cv_entities.values()])
        job_text = " ".join([" ".join(values) for values in job_entities.values()])
        
        # Calculate similarity score
        try:
            vectorizer = TfidfVectorizer()
            vectors = vectorizer.fit_transform([cv_text, job_text])
            similarity_score = cosine_similarity(vectors[0], vectors[1])[0][0]
        except:
            similarity_score = 0
        
        logging.debug(f"CV {i}: Similarity Score: {similarity_score}")
        
        # Calculate category-specific matches
        skill_match = 0
        experience_match = 0
        education_match = 0
        
        # Skills match
        if "COMPETENCES" in cv_entities and "COMPETENCES" in job_entities:
            cv_skills = set([s.lower() for s in cv_entities["COMPETENCES"]])
            job_skills = set([s.lower() for s in job_entities["COMPETENCES"]])
            if job_skills:
                skill_match = min(len(cv_skills.intersection(job_skills)) / len(job_skills) * 100, 100)
        
        logging.debug(f"CV {i}: Skill Match: {skill_match}")
        
        # Experience match
        if "EXPERIENCE" in cv_entities and "EXPERIENCE" in job_entities:
            cv_exp = set([e.lower() for e in cv_entities["EXPERIENCE"]])
            job_exp = set([e.lower() for e in job_entities["EXPERIENCE"]])
            if job_exp:
                experience_match = min(len(cv_exp.intersection(job_exp)) / len(job_exp) * 100, 100)
        
        logging.debug(f"CV {i}: Experience Match: {experience_match}")
        
        # Education match
        if "DIPLOME" in cv_entities and "DIPLOME" in job_entities:
            cv_edu = set([e.lower() for e in cv_entities["DIPLOME"]])
            job_edu = set([e.lower() for e in job_entities["DIPLOME"]])
            if job_edu:
                education_match = min(len(cv_edu.intersection(job_edu)) / len(job_edu) * 100, 100)
        
        logging.debug(f"CV {i}: Education Match: {education_match}")
        
        # Apply keyword weights
        weighted_score = 1.0  # Base score
        keyword_matches = {}
        
        for keyword, weight in keyword_weights.items():
            # Check if keyword appears in any entity
            if any(keyword.lower() in " ".join(cv_entities.get(k, [])).lower() for k in cv_entities):
                weighted_score += weight
                keyword_matches[keyword] = weight
        
        logging.debug(f"CV {i}: Weighted Score: {weighted_score}")
        
        # Final score
        final_score = similarity_score * weighted_score
        logging.debug(f"CV {i}: Final Score: {final_score}")
        
        # Get relevant skills (if available)
        relevant_skills = []
        if "COMPETENCES" in cv_entities:
            relevant_skills = cv_entities["COMPETENCES"][:3]
        
        # Add to results
        ranked_cvs.append({
            "index": i,
            "score": final_score,
            "match_percentage": min(int(final_score * 100), 100),  # Cap at 100%
            "relevant_skills": relevant_skills,
            "entities": cv_entities,
            "skill_match": round(skill_match),
            "experience_match": round(experience_match),
            "education_match": round(education_match),
            "keyword_matches": keyword_matches
        })
    
    # Sort by similarity score (highest first)
    ranked_cvs.sort(key=lambda x: x["score"], reverse=True)
    
    return ranked_cvs