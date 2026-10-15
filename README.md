# Hub Éducatif & Créatif Multimodal

Projet universitaire Django (MVT) — Bootstrap 5, SQLite.

## Lancer le projet

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo      # rôles, 3 comptes, cours et exercices de démonstration
python manage.py runserver
```

Ouvrir http://127.0.0.1:8000/

| Compte | Mot de passe | Rôle |
|---|---|---|
| `admin` | `Admin1234!` | Administrateur |
| `prof` | `Prof1234!` | Enseignant / Coach |
| `eleve` | `Eleve1234!` | Apprenant |

(Comptes de démonstration uniquement.)

## Périmètre

| Module | Statut |
|---|---|
| `accounts` — User, Role (groupes Django) | CRUD fonctionnel |
| `pedagogie` — Cours, Exercice | CRUD fonctionnel |
| `coaching`, `ressources`, `objectifs` | Pages **statiques** de démonstration (aucun modèle, aucune migration) |

Les permissions sont gérées par les permissions Django attachées aux rôles. Un enseignant ne modifie/supprime que ses propres cours et leurs exercices ; l'administrateur peut tout gérer. Les rôles système (Administrateur, Enseignant / Coach, Apprenant) ne peuvent être ni supprimés ni renommés.

Voir `GUIDE_INTEGRATION.md` pour intégrer les modules des collègues.
