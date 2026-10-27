# Préparation Vercel — EduConnect

Cette branche prépare la configuration. Aucun projet Vercel, stockage distant ou
déploiement Vercel n'a été créé. Le projet PostgreSQL Neon `educonnect` existe en
région Frankfurt et ses migrations Django ont été appliquées. Les modules métier
restent inchangés.

## Configuration

| Variable | Local | Vercel / production |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Facultative avec DEBUG actif ; clé locale conservée | Obligatoire : clé aléatoire, au moins 50 caractères et 5 caractères distincts, sans préfixe `django-insecure-` |
| `DJANGO_DEBUG` | `True` par défaut | Toujours `False` sur Vercel, même si la variable est mal configurée |
| `DJANGO_ALLOWED_HOSTS` | Par défaut `localhost,127.0.0.1,[::1]` | Noms exacts séparés par des virgules, sans schéma ; inclure domaine stable et domaine personnalisé |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Liste facultative | Origines HTTPS complètes séparées par des virgules |
| `DATABASE_URL` | Absente : `db.sqlite3` ; présente : PostgreSQL | Obligatoire sur Vercel ; URL du fournisseur PostgreSQL, idéalement endpoint avec pooler |
| `GEMINI_API_KEY` | Facultative, dans `.env` ou l'environnement | Secret de l'environnement concerné ; l'IA reste optionnelle |
| `GEMINI_MODEL` | Défaut existant : `gemini-2.5-flash` | Même valeur par défaut, configurable |
| `PEDAGOGIE_GEMINI_MODEL` | Défaut existant : `gemini-3.1-flash-lite` | Même valeur par défaut, configurable |
| `VERCEL`, `VERCEL_URL` | Non nécessaires | Variables système Vercel ; le domaine de `VERCEL_URL` est ajouté aux hôtes et origines CSRF |

Le chargeur `.env` existant est conservé et étendu à la configuration Django.
Il s'applique uniquement hors Vercel et ne remplace jamais les valeurs déjà
présentes dans l'environnement. Ne pas versionner ni envoyer `.env`.
`.vercelignore` exclut aussi les bases SQLite, sauvegardes associées, médias
locaux et environnements virtuels des envois Vercel CLI.

En production, cookies sécurisés et redirection HTTPS sont activés. Sur Vercel,
Django tient compte de `X-Forwarded-Proto` du proxy. HSTS reste désactivé : son
activation éventuelle attend la validation des domaines HTTPS.

## Entrée et fichiers statiques

La structure actuelle `manage.py` + `WSGI_APPLICATION=config.wsgi.application`
est compatible avec la détection Django native de Vercel. Aucun dossier `api/`
ni `vercel.json` n'est nécessaire pour cette configuration. `.python-version`
sélectionne Python 3.13, pris en charge par la plateforme.

`STATIC_ROOT` pointe vers `staticfiles/`. WhiteNoise suit immédiatement
`SecurityMiddleware`. Le stockage local reste standard ; la production utilise
le stockage WhiteNoise compressé avec manifeste. Le stockage des médias reste
`FileSystemStorage`, sans substitution automatique.

Avec l'intégration native, Vercel exécute `collectstatic` au build et distribue
les statiques via son CDN. Aucune commande `migrate` n'est ajoutée au build, au
démarrage WSGI ou aux requêtes HTTP.

## Points bloquants ou à valider avant déploiement

- **Médias utilisateurs** : `SupportCours.fichier` écrit actuellement dans
  `media/`. Le système de fichiers des fonctions est en lecture seule, sauf
  `/tmp` temporaire. Il faut approuver puis intégrer un stockage objet persistant
  (par exemple S3 compatible ou Vercel Blob), avec accès privé, autorisations et
  URLs signées adaptées. Les téléversements actuels ne sont pas prêts pour Vercel.
- **Exports** : Word/PowerPoint et certains PDF utilisent des buffers mémoire.
  Un chemin PDF tente aussi un navigateur Chrome/Chromium/Edge et un dossier
  temporaire ; ce navigateur n'est pas garanti sur Vercel. Tester le repli PDF
  existant, les images, les polices et les documents volumineux sur Preview.
  Ne pas inclure un navigateur système sans analyse du poids du paquet.
- **Gemini** : les délais réseau existants sont de 35 à 60 secondes selon le
  module. Régler la durée de fonction selon le parcours le plus long et le plan,
  puis mesurer les délais réels ; pas d'appel Gemini réel pendant cette préparation.
  Le cache Django local et les limites de requêtes en mémoire ne sont pas partagés
  entre instances. Prévoir un cache partagé avant une utilisation à grande échelle.
- **Limites** : vérifier le budget mémoire, la durée maximale de la fonction et
  la limite de charge utile (requêtes et réponses, notamment téléversements et
  exports). La documentation indique notamment 4,5 Mo pour les charges utiles ;
  un stockage direct avec URL signée pourra être nécessaire pour les gros fichiers.
- **PostgreSQL** : le projet Neon `educonnect` est situé à Frankfurt et les 42
  migrations Django sont appliquées. TLS est exigé en production,
  `CONN_MAX_AGE=0` et un délai de connexion de 10 secondes sont configurés. Les
  curseurs serveur sont désactivés sur Vercel pour la compatibilité avec le
  pooler transactionnel. Configurer dans Vercel l'URL poolée correspondant à la
  base validée, sans l'ajouter au dépôt.

## Étapes suivantes, après accord

1. Revoir les différences de cette branche et confirmer les tests locaux.
2. Choisir le stockage des médias et décider si Preview doit utiliser une branche
   Neon isolée de Production.
3. Connecter le compte GitHub à Vercel et préparer l'import du dépôt à sa racine,
   avec le framework Django, les hôtes et les secrets ci-dessus. **L'import d'un
   projet peut déclencher un premier déploiement : attendre l'autorisation.**
4. Définir les environnements Preview/Production et la branche de production
   prévue (`main`) dans les paramètres du futur projet, sans modifier `main` ici.
5. Pour toute migration future, valider d'abord la cible et le plan, puis utiliser
   une connexion directe Neon après autorisation explicite. Ne jamais lancer les
   migrations automatiquement depuis une fonction ni confondre Preview et Production.
6. Après autorisation du premier Preview : vérifier TLS/proxy, CSRF, connexion,
   fichiers statiques, fichiers utilisateurs, exports et IA avant publication.

## Références officielles

- [Django natif et statiques sur Vercel](https://vercel.com/docs/frameworks/full-stack/django)
- [Runtime Python et versions](https://vercel.com/docs/functions/runtimes/python)
- [Limites des fonctions](https://vercel.com/docs/functions/limitations)
- [Système de fichiers des fonctions](https://vercel.com/docs/functions/runtimes)
- [En-têtes transmis par Vercel](https://vercel.com/docs/headers/request-headers)
- [WhiteNoise avec Django](https://whitenoise.readthedocs.io/en/stable/django.html)
