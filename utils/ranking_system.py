import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import joblib
import os

class ResumeRankingSystem:
    def __init__(self):
        # Utiliser le modèle français par défaut
        self.nlp = spacy.load("fr_core_news_sm")
        
    def extract_unique_entities(self, text):
        """Extract unique entities from text using the French NER model."""
        doc = self.nlp(text)
        entities = {}
        for ent in doc.ents:
            if ent.label_ not in entities:
                entities[ent.label_] = set()
            entities[ent.label_].add(ent.text.lower())
        return {key: list(values) for key, values in entities.items()}

    def compute_similarity(self, cv_entities, job_entities, keyword_weights):
        """Computes similarity between CV entities and job description entities."""
        cv_text = " ".join([" ".join(values) for values in cv_entities.values()])
        job_text = " ".join([" ".join(values) for values in job_entities.values()])
        
        vectorizer = TfidfVectorizer()
        vectors = vectorizer.fit_transform([cv_text, job_text])
        
        # Compute cosine similarity
        similarity_score = cosine_similarity(vectors[0], vectors[1])[0][0]
        
        # Apply keyword weights
        weighted_score = 0
        for keyword, weight in keyword_weights.items():
            if any(keyword in " ".join(cv_entities.get(k, [])) for k in cv_entities):
                weighted_score += weight
        
        final_score = similarity_score * weighted_score
        return final_score

    def rank_applications(self, applications, job_description, keyword_weights):
        """Rank applications based on similarity with job description."""
        job_entities = self.extract_unique_entities(job_description)
        ranked_applications = []
        
        for application in applications:
            # Extraire le texte du CV depuis le chemin du fichier
            cv_text = self._extract_text_from_file(application.get('resume_path', ''))
            if not cv_text:
                continue
                
            # Extraire les entités du CV
            cv_entities = self.extract_unique_entities(cv_text)
            
            # Calculer le score de similarité
            similarity_score = self.compute_similarity(cv_entities, job_entities, keyword_weights)
            
            # Convertir le score en pourcentage (0-100)
            match_percentage = round(similarity_score * 100, 2)
            
            # Ajouter le score à l'application
            application['match_percentage'] = match_percentage
            ranked_applications.append(application)
        
        # Trier les applications par score décroissant
        ranked_applications.sort(key=lambda x: x.get('match_percentage', 0), reverse=True)
        return ranked_applications

    def _extract_text_from_file(self, file_path):
        """Extract text from a file (PDF or TXT)."""
        if not file_path:
            return ""
            
        try:
            if file_path.lower().endswith('.pdf'):
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                text = ""
                for page in doc:
                    text += page.get_text("text") + "\n"
                return text
            elif file_path.lower().endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                return ""
        except Exception as e:
            print(f"Error extracting text from file: {e}")
            return "" 