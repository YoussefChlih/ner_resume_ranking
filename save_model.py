import spacy
from spacy.training import Example
import os

# Create data/model directory if it doesn't exist
os.makedirs("data/model", exist_ok=True)

# Load blank model
nlp = spacy.blank("fr")

# Add NER pipe
ner = nlp.add_pipe("ner")

# Add labels
ner.add_label("COMPETENCES")
ner.add_label("EXPERIENCE")
ner.add_label("DIPLOME")
ner.add_label("POSTE")

# Train the model
# Note: You'll need to add your training data here
# For now, we'll just save the model structure
nlp.to_disk("data/model")

print("Model saved to data/model") 