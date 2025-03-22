from utils.ranking_system import ResumeRankingSystem

def test_ranking():
    # Créer une instance du système de classement
    ranking_system = ResumeRankingSystem()
    
    # Description du poste (exemple)
    job_description = """
    Nous recherchons un Data Scientist Junior pour rejoindre notre équipe.
    Compétences requises :
    - Python
    - Machine Learning
    - SQL
    - Git
    - Traitement de données
    """
    
    # Liste des candidatures (exemple)
    applications = [
        {
            'candidate_id': '1',
            'resume_path': 'data/resumes/00b94848-00d0-41ae-b8a7-7f2e5f6612ec_Youssef-CHLIH-CV-fr.pdf',  # Remplacez par le chemin de votre CV
            'applied_date': '2024-03-20'
        }
        # Ajoutez d'autres candidatures ici
    ]
    
    # Poids des mots-clés
    keyword_weights = {
        'python': 0.8,
        'machine learning': 0.7,
        'sql': 0.6,
        'git': 0.5,
        'traitement de données': 0.7
    }
    
    # Classer les candidatures
    ranked_applications = ranking_system.rank_applications(
        applications=applications,
        job_description=job_description,
        keyword_weights=keyword_weights
    )
    
    # Afficher les résultats
    print("\nRésultats du classement :")
    print("-" * 50)
    for i, app in enumerate(ranked_applications, 1):
        print(f"\n{i}. Candidat {app['candidate_id']}")
        print(f"Score de correspondance : {app['match_percentage']}%")
        print(f"Date de candidature : {app['applied_date']}")

if __name__ == "__main__":
    test_ranking() 