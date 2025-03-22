import spacy
from merged_TEST_dataset import TEST_DATA_MERGED

# Load the trained model
nlp = spacy.load("data/model")

# Test the model on test data
print("Testing model on test data...")
for text, annotations in TEST_DATA_MERGED:
    doc = nlp(text)
    print("\nText:", text[:100], "...")
    print("Predicted entities:")
    for ent in doc.ents:
        print(f"- {ent.text} ({ent.label_})")
    print("\nActual entities:")
    for start, end, label in annotations["entities"]:
        print(f"- {text[start:end]} ({label})")
    print("-" * 50) 