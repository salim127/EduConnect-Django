# Cours, chapitres et documents Office

Après une mise à jour : `pip install -r requirements.txt` puis `python manage.py migrate`.

## Enseignant

- **Cours → Créer un cours** : rédiger une introduction, puis ajouter les chapitres. L’éditeur propose titres, gras, italique, couleurs et listes.
- L’introduction et les chapitres utilisent HugeRTE 1.0.14, installé localement avec une interface française : polices, tailles, alignements, couleurs, tableaux, liens, images par URL, recherche/remplacement, aperçu et plein écran. Aucune clé API n’est nécessaire. La mise en forme autorisée est conservée côté serveur.
- **Cours → Importer des cours** : sélectionner jusqu’à 10 fichiers `.docx` / `.pptx` (15 Mo par fichier, 50 Mo par envoi). Chaque fichier crée un cours. La matière et le niveau choisis s’appliquent à l’ensemble de l’envoi.
- Word : les paragraphes de style « Titre 1 » / « Titre 2 » deviennent des chapitres ; le texte et les formats simples sont importés.
- PowerPoint : chaque diapositive devient un chapitre avec son titre et son texte.
- Les images, tableaux, graphiques, animations et mises en page complexes ne sont pas convertis dans le lecteur. Les fichiers originaux sont conservés et téléchargeables.
- Dans la modification d’un cours, **Documents du cours** permet aussi de joindre plusieurs documents sans créer de nouveaux cours.
- Dans chaque chapitre, **Documents de ce chapitre** accepte plusieurs PDF ou Word `.docx`. Le texte du chapitre peut rester vide si des documents sont joints. Les documents sont téléchargés depuis le chapitre correspondant par l’apprenant. Les PDF sont des pièces jointes ; ils ne sont pas convertis dans l’éditeur. Les limites de 15 Mo par fichier et 50 Mo par envoi s’appliquent aussi aux pièces jointes des chapitres.
- Dans un chapitre, **Ajouter un exercice ici** présélectionne le cours et le chapitre. Le chapitre reste modifiable dans le formulaire de l’exercice. Sans sélection, l’exercice est général au cours.
- **Mes cours** filtre le catalogue sur les cours de l’enseignant connecté.
- Pour un document déjà envoyé, choisir **Visible aux étudiants**, **Masquer aux étudiants** ou **Supprimer à l’enregistrement**, puis cliquer sur **Enregistrer**. Masquer conserve le fichier pour le professeur ; supprimer retire définitivement le document et son fichier stocké après validation du formulaire.
- Les cases **Masquer ce cours aux étudiants** et **Masquer ce chapitre aux étudiants** conservent les données mais retirent ces éléments de la consultation étudiante. Décocher la case puis enregistrer pour les réafficher. Un chapitre masqué retire aussi ses exercices, ses documents et son contenu des exports étudiants ; les liens directs sont protégés.

Les chapitres possèdent un identifiant stable. Leur renommage conserve les liens avec leurs exercices. Si un chapitre est supprimé, ses exercices deviennent des exercices généraux du cours ; ils ne sont pas supprimés.
Les documents d’un chapitre supprimé deviennent des documents généraux du cours pour éviter leur perte.

## Apprenant

Le catalogue présente tous les cours. Le programme de chaque cours permet de choisir un chapitre. Le lecteur affiche un chapitre à la fois, avec les boutons précédent/suivant et ses exercices associés. Les exercices généraux sont dans la présentation du cours.

Le lecteur découpe les longs chapitres en pages avec une navigation numérotée. Dans le navigateur, la pagination mesure la hauteur réelle du texte, des images et des tableaux selon l’écran. Les tableaux peuvent continuer sur la page suivante, ligne par ligne. La zone de lecture suit la hauteur du contenu, sans hauteur minimale qui laisserait un grand espace vide. Sans JavaScript, une pagination serveur reste disponible. Le texte enregistré dans HugeRTE reste modifiable ; cette présentation ne modifie pas les données du cours.

Les exports Word et PDF conservent les paragraphes, les retours à la ligne, les formats de texte, les titres, les listes, les tableaux et les images. Leur mise en page est celle d’un document A4 avec un enchaînement naturel du contenu ; aucun espace fixe n’est réservé à chaque paragraphe. PowerPoint conserve un découpage en diapositives adapté à la présentation. Les images publiques doivent être accessibles au moment de l’export ; si une image distante n’est plus disponible, un emplacement explicatif la remplace. Les adresses locales et privées ne sont pas téléchargées par le serveur. Pour retrouver exactement la mise en page d’un document importé, télécharger son original.

Le PDF utilise Chrome / Chromium / Edge en mode sans interface, détecté sur le serveur ou indiqué par la variable d’environnement `COURSE_PDF_BROWSER`. Le HTML est nettoyé et les images publiques sont incorporées au document avant l’impression ; aucune ressource réseau n’est chargée par le navigateur. Si ce moteur n’est pas disponible, un export A4 avec texte enrichi et enchaînement naturel est produit par ReportLab. La pagination peut varier selon les polices disponibles et les dimensions A4.

## Fonctionnement

Les imports/exports utilisent `python-docx` et `python-pptx` sur le serveur. Aucune clé Microsoft n’est nécessaire. Cela ne fournit pas l’éditeur Microsoft Office dans le navigateur. Une intégration Office pour le web serait un chantier distinct avec les prérequis Microsoft 365/WOPI.

Les originaux sont stockés dans `MEDIA_ROOT` (dossier `media/`, ignoré par Git). Leur téléchargement passe par Django et exige la permission de consultation des cours. Ne pas exposer ce dossier via une route publique en production. Sauvegarder le dossier `media/` avec la base de données.

Un envoi contenant un document invalide n’importe aucun cours. Les droits habituels s’appliquent : un enseignant ne modifie que ses propres cours et exercices ; un apprenant consulte et répond.

Validation : `python manage.py test pedagogie`.

## IA pédagogique par chapitre

Depuis un chapitre, **Générer des exercices IA** permet au professeur propriétaire (ou à un administrateur) de demander 1 à 10 questions QCM, Vrai/Faux ou ouvertes, avec une difficulté. L’aperçu est modifiable : questions, bonnes réponses, explications et suppression de questions. Rien n’est publié avant **Valider et enregistrer l’exercice**. Le résultat devient un exercice de plusieurs questions associé au chapitre. Un brouillon expire après 30 minutes ; si le chapitre ou ses documents changent entre-temps, il faut générer un nouvel aperçu. Les explications sont visibles par l’étudiant après vérification de ses réponses.

**Poser une question sur ce chapitre** ouvre un chatbot. Il utilise le contenu textuel du chapitre et les PDF / Word rattachés à ce chapitre que l’utilisateur a le droit de consulter. Les corrigés des exercices ne sont pas envoyés au modèle. Chaque réponse dans le sujet doit citer un extrait retrouvé exactement dans les sources ; les citations inventées sont refusées. L’historique est conservé dans la session de l’utilisateur, pour ce chapitre uniquement, et peut être effacé avec **Nouvelle discussion**. Un changement de contenu ou de visibilité invalide l’ancien contexte. Les scans sans texte sélectionnable ne sont pas lus par OCR.

Les appels utilisent `GEMINI_API_KEY` et `PEDAGOGIE_GEMINI_MODEL` (par défaut `gemini-3.1-flash-lite`), configurés dans `.env`, ignoré par Git. La clé reste dans les requêtes du serveur vers Google. Les contenus nécessaires au traitement sont transmis à l’API Gemini. Limites : une demande simultanée par utilisateur, 60 demandes par heure, 28 000 caractères de sources et les 15 premières pages de chaque PDF. Les réponses signalent si le contexte est tronqué. Les erreurs de quota ou de connexion sont affichées sans publier de question ni produire une fausse réponse.

Contrôles réels facultatifs : `python docs/check_gemini_connection.py` vérifie l’accès au modèle sans afficher la clé ; `python docs/check_chapter_ai.py` effectue deux petits appels sur un texte fictif sans créer d’exercice.

Les sources, versions et empreintes de HugeRTE et de sa traduction sont dans `static/vendor/hugerte/SOURCES.json`. Pour réinstaller ces versions : `python docs/install_editor_assets.py` (accès réseau nécessaire). Les licences tierces sont conservées dans ce dossier. Vérification navigateur optionnelle : `docs/check_editor_browser.mjs`, avec un profil Chrome de test isolé sur le port 9223 et les variables `EDITOR_USER` / `EDITOR_PASSWORD`.

## Révision et entraînement personnel

- Dans un chapitre, **Résumé et fiches de révision** ouvre une page proposant un résumé (notions essentielles et exemples) et six cartes question / réponse. Les passages cités sont vérifiés dans les sources accessibles. Les réponses des cartes sont repliées pour permettre de se tester. Les supports générés sont réutilisés dans la session et invalidés lorsque le contenu ou ses documents changent.
- Les indices ont été retirés des exercices et leur ancien appel serveur n’est plus disponible.
- Les réponses complètes et valides aux exercices sont enregistrées dans un historique personnel. Une seule soumission est autorisée au départ, puis le professeur peut autoriser une tentative supplémentaire pour un élève et un exercice. Un double clic ou un ancien onglet ne consomme pas une nouvelle autorisation. Un autre utilisateur ne peut pas consulter cette tentative, même en connaissant son numéro.
- Pour une question ouverte, le professeur définit le **Barème de correction** dans le formulaire de création, de modification ou dans l’aperçu IA. Chaque question a son propre barème : une ligne `Description | points`, par exemple `Définition de HTML | 2`, `Rôle de CSS | 2`, `Exemple pertinent | 1`. Maximum : dix critères, vingt points par critère et cent au total. Les décimales sont acceptées à un chiffre après la virgule. Un ancien exercice sans barème reste utilisable ; le professeur doit ajouter le barème pour activer sa correction IA.
- Après **Soumettre mes réponses**, **Proposer une correction IA** fournit les points par critère, les éléments corrects, les éléments manquants et un conseil. Les maxima viennent du professeur et le total est calculé par le serveur. Cette proposition est indicative, elle ne remplace pas la validation du professeur. Une réponse ouverte n’est plus évaluée par simple égalité de texte. La correction est conservée avec la tentative et réaffichable sans nouvel appel.
- **Mon entraînement adapté** permet de commencer immédiatement avec un à cinq QCM à partir du chapitre, même si le professeur n’a pas encore publié d’exercices. Ensuite, il examine les dernières réponses de l’utilisateur aux exercices et aux entraînements personnels du chapitre, ainsi que les points manquants des questions ouvertes déjà corrigées. Les erreurs répétées sont prioritaires ; une bonne réponse plus récente à la même question retire cette difficulté. Sans erreur active, l’IA propose de nouvelles questions sur le chapitre. Ces questions restent personnelles et ne sont pas publiées dans les exercices du professeur. Le corrigé et l’explication apparaissent après la réponse.

Les tentatives et les entraînements sont stockés dans la base Django ; les résumés et fiches sont associés à la session. Les changements de cours, de documents et de questions invalident les anciennes versions utilisées pour les aides. Les mêmes permissions, contrôles CSRF et limites Gemini s’appliquent aux nouvelles fonctions. Les textes nécessaires, les réponses ouvertes soumises et les difficultés sélectionnées sont transmis à Gemini lorsque l’utilisateur demande l’aide correspondante.

`python docs/check_learning_ai.py` effectue quatre petits appels réels avec un texte fictif et sans requête à la base. `docs/check_learning_browser.mjs` vérifie les nouveaux liens et interactions avec des réponses de correction simulées (profil Chrome de test isolé, variables `EDITOR_USER`, `EDITOR_PASSWORD`, `AI_CHAPTER_URL`).

## Notes, moyennes et nouvelles tentatives

- Les QCM et Vrai/Faux publiés par le professeur reçoivent automatiquement une note sur 20 : `bonnes réponses / nombre de questions × 20`, arrondie à deux décimales. Toutes les questions ont le même poids.
- Une réponse ouverte est remise sans note définitive. L’IA peut toujours proposer sa correction ; **Notes des étudiants → Corriger la copie** permet au professeur du cours ou à un administrateur de consulter la copie et de valider une note entre 0 et 20 avec un commentaire. Une proposition IA n’entre jamais seule dans la moyenne.
- L’élève retrouve ses copies, les notes et les moyennes par cours dans **Mes notes**. La moyenne du cours est la moyenne arithmétique des dernières notes validées, une par exercice. La moyenne générale applique le même poids à chaque exercice noté de tous les cours. Les exercices non remis et les copies en attente ne sont pas comptés comme zéro. Les entraînements personnels restent des activités de révision, sans effet sur les notes officielles.
- **Notes des étudiants** affiche uniquement les résultats des cours du professeur connecté (tous les cours pour un administrateur). Les filtres portent sur le cours et l’étudiant. Les listes de copies sont paginées et proposent l’historique de chaque exercice.
- Après une soumission, l’exercice devient consultable en lecture seule. **Autoriser une nouvelle tentative** accorde un seul passage supplémentaire à l’élève concerné. Cliquer deux fois n’accorde pas deux passages. Le professeur peut retirer une autorisation inutilisée. Un ancien formulaire d’autorisation ne permet pas de renouveler l’accès après un nouveau passage.
- La dernière note validée remplace la précédente pour la moyenne, même si elle est plus basse. Pendant la correction d’une nouvelle réponse ouverte, la note précédemment validée reste retenue. Les anciennes notes et copies sont conservées. Les changements de questions ne débloquent pas automatiquement une nouvelle tentative.
- Une nouvelle copie conserve un instantané de son énoncé, des bonnes réponses et du barème. Une modification ultérieure de l’exercice ne change ni cette copie ni sa note. Pour préserver les résultats, l’interface bloque la suppression d’un cours ou d’un exercice ayant des copies ; un cours peut être masqué.
- Le professeur propriétaire dispose d’un aperçu sans soumission notée. Les anciens résultats QCM / Vrai/Faux sont convertis en notes lors de la migration `0010` ; les anciennes réponses ouvertes restent à noter. Les anciennes copies n’ayant pas d’instantané signalent une ancienne version si l’énoncé a changé.

Contrôle navigateur complet sans API IA : créer les données fictives avec `python docs/grade_browser_fixture.py`, lancer un Chrome de test isolé sur le port 9223, puis `node docs/check_grading_browser.mjs`. Le scénario vérifie une note de 10/20, le refus d’une répétition, l’autorisation du professeur, une nouvelle note de 20/20 et une réponse ouverte validée à 14/20, soit une moyenne de 17/20. Terminer par `python docs/grade_browser_fixture.py cleanup` pour supprimer uniquement ces données de test.
