import spacy
from spacy.training import Example
import os
from merged_dataset import TRAIN_DATA_MERGED

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

# Convert training data to spaCy format
train_examples = []
for text, annotations in TRAIN_DATA_MERGED:
    train_examples.append(Example.from_dict(nlp.make_doc(text), annotations))

# Train the model
print("Training model...")
nlp.begin_training()
for epoch in range(30):
    losses = {}
    nlp.update(train_examples, losses=losses)
    print(f"Epoch {epoch}, Loss: {losses['ner']}")

# Save the trained model
nlp.to_disk("data/model")
print("Model saved to data/model") 