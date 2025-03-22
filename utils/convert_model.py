import spacy
import joblib
import os

def convert_spacy_to_joblib():
    # Charger le modèle spaCy
    nlp = spacy.load("custom_ner_model")
    
    # Créer le dossier models s'il n'existe pas
    os.makedirs("models", exist_ok=True)
    
    # Sauvegarder le modèle au format joblib
    joblib.dump(nlp, "models/ner_model.joblib")
    print("Modèle converti et sauvegardé avec succès dans models/ner_model.joblib")

if __name__ == "__main__":
    convert_spacy_to_joblib() 