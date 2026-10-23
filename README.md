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
| `coaching`, `ressources` | Pages **statiques** de démonstration (aucun modèle, aucune migration) |

Les permissions sont gérées par les permissions Django attachées aux rôles. Un enseignant ne modifie/supprime que ses propres cours et leurs exercices ; l'administrateur peut tout gérer. Les rôles système (Administrateur, Enseignant / Coach, Apprenant) ne peuvent être ni supprimés ni renommés.

Voir `GUIDE_INTEGRATION.md` pour intégrer les modules des collègues.

## Gestion des objectifs

Le module `objectifs` contient les entités `ObjectifApprentissage` et `TacheApprentissage` (relation un-à-plusieurs).
Les pages « Mes objectifs » et « Mes tâches » permettent de créer, consulter, rechercher, modifier et supprimer les données.
Les professeurs créent et gèrent leurs objectifs et leurs tâches, en attribuant chaque objectif à un seul apprenant actif. Les apprenants consultent uniquement leurs objectifs attribués, rédigent leur travail et le soumettent. Les statuts changent automatiquement. Les administrateurs gèrent toutes les données.
La progression est le pourcentage de tâches validées par le professeur. Une tâche ne peut pas dépasser l’échéance de son objectif.
La suppression d’un objectif demande confirmation et supprime également ses tâches.
Les migrations attribuent les permissions aux trois rôles système existants.

Validation : `python manage.py test objectifs`.

Les objectifs personnels existants des apprenants leur restent attribués après migration. Les autres objectifs existants sont affichés « À attribuer » : leur créateur ou un administrateur peut sélectionner un apprenant. Le professeur choisit manuellement un objectif adapté ; aucune attribution automatique n’est effectuée.


### Validation des tâches

Un objectif précise un niveau et un critère de réussite. Une tâche peut avoir une durée estimée en minutes (supérieure à zéro).
L’enregistrement d’un brouillon passe automatiquement la tâche à « En cours » ; la soumission du travail la passe à « Soumise ». Le professeur créateur ou un administrateur décide « Validée » ou « À reprendre » depuis la page de la tâche.
Une tâche soumise attend cette décision ; une tâche à reprendre peut être soumise à nouveau. Une tâche validée n’est plus modifiable par l’apprenant.
Le formulaire général de modification ne permet pas de changer le statut : la validation passe par la page dédiée.
Les anciennes tâches « Terminée » deviennent « Soumise » et attendent une validation ; leur progression peut donc diminuer après migration.
Les anciens objectifs conservent leurs données, avec le niveau Débutant et un critère à préciser lors de leur prochaine modification.


### Travail rendu par l’apprenant

L’apprenant rédige une réponse (texte ou code). « Enregistrer le brouillon » enregistre sa réponse et passe automatiquement la tâche à En cours. « Soumettre mon travail » exige une réponse non vide, enregistre la date et passe la tâche à Soumise.
Aucun choix de statut n’est proposé à l’apprenant. Le professeur lit la réponse sur la page de validation avant de valider ou de demander une reprise. Les réponses soumises ou validées ne peuvent plus être modifiées par l’apprenant ; une reprise autorise une nouvelle rédaction.
Le travail est enregistré en texte dans la base locale ; les pièces jointes ne font pas partie de ce formulaire.


## Statistiques et Gemini

Ouvrir Objectifs → Mes statistiques. Le temps est mesuré uniquement pendant la rédaction sur une page visible et active, avec pause après 60 secondes sans interaction. Des signaux toutes les 10 secondes sont plafonnés côté serveur ; les interruptions de plus de 20 secondes ne sont pas comptées. Une horloge par utilisateur évite de sommer les onglets simultanés. Il s’agit d’une estimation d’activité, pas d’un contrôle de présence. Les données antérieures à l’installation ne sont pas reconstituées.
Le professeur fixe sa décision (En cours / Atteint / À renforcer) dans le formulaire de modification d’objectif. La progression calculée reste le pourcentage de tâches validées.
Configurer GEMINI_API_KEY et GEMINI_MODEL dans .env, puis redémarrer le serveur. Ne jamais committer .env. L’analyse explicite transmet à Google les réponses et les données pédagogiques de l’objectif, sans ajouter le nom de l’utilisateur. Les statistiques restent disponibles sans clé. La réponse IA ne modifie ni les statuts ni la décision du professeur.
API : https://ai.google.dev/api/generate-content


## Besoins, charge et recherche par sens

L’apprenant renseigne ses minutes disponibles par semaine dans Ma disponibilité (aucune valeur supposée). Charge de travail compare les durées estimées restantes aux disponibilités réparties sur sept jours, aujourd’hui inclus. Le cumul couvre uniquement les objectifs accessibles de l’apprenant, selon les échéances des tâches et objectifs. Les durées absentes et échéances manquantes sont signalées. Ce calcul local ne dépend pas de Gemini.
Le professeur ouvre Besoins des apprenants : les brouillons sont exclus, au moins deux apprenants avec travaux rendus sont nécessaires. Gemini propose des groupes justifiés par des tâches existantes, sans modification des données. L’échantillon est limité à 40 travaux et les réponses à 2 000 caractères ; les noms ne sont pas ajoutés au prompt.
Recherche par sens utilise Gemini sur 100 objectifs accessibles au maximum. Si le service est indisponible, la page utilise une recherche locale explicitement identifiée par concepts pédagogiques (boucles, conditions, variables, fonctions). Ce repli n’est pas une IA sémantique générale. Les appels Gemini sont explicites, protégés par CSRF, limités à un appel par session toutes les 30 secondes et utilisent des sorties JSON vérifiées côté serveur.
