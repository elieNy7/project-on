# Project-On — Analyse approfondie et plan d’évolution

Date : 17 septembre 2026. Référence analysée : commit `246cf65` (v2.3.0).

## Conclusion

Project-On possède une bonne base de régie hors ligne. Une réécriture complète n’est pas justifiée : conserver PyQt6, SQLite, le moteur SlideCanvas et les sorties existantes est moins risqué qu’un remplacement global. En revanche, une modernisation transversale est justifiée : fiabilité des données, état du direct, imports, sorties réseau, ergonomie et publication.

Objectif : pouvoir améliorer tous les domaines, par lots indépendants et réversibles, sans sacrifier les fonctions déjà utilisées en culte.

## Portée et degré de vérification

Trois analyses spécialisées ont couvert l’architecture/projection, les données/imports et la sécurité locale/livraison. Une lecture complémentaire a porté sur le démarrage, la navigation, les réglages, les raccourcis et les tests de projection.

- Les constats sont principalement issus de la lecture du code ; les scénarios conditionnels ne prouvent pas un incident sur le poste.
- L’agent architecture rapporte une reproduction en mémoire des deux défauts d’annonces. La perte de l’édition préalable est établie ; le comportement précis du suivi Exposé et de chaque état vidéo devra être caractérisé séparément.
- Aucun test d’intrusion, audit CVE en ligne, téléchargement de runtime ou publication effectué.
- Aucun test physique de projecteur, mélangeur HDMI, réception NDI ou instance OBS réelle.
- Pas de revue visuelle exhaustive de l’application : les propositions UX sont des recommandations issues du code, non une certification de son rendu.
- La suite complète a été interrompue : les 183 tests historiques ne sont pas déclarés verts pour cette session.
- Validation effectivement terminée : **23 tests de projection passent**, dont **7 nouveaux cas** sur l’écran initial. Ces tests utilisent un dossier temporaire et le mode Qt hors écran.

## Atouts à conserver

1. Moteur SlideCanvas partagé entre aperçu et projection : bonne base de fidélité visuelle.
2. Écritures atomiques des états de projection, découplant l’application de ses consommateurs.
3. Transactions SQLite, clés étrangères, WAL et sauvegarde par l’API SQLite.
4. Bibliothèques métier et navigation clavier déjà riches : Bible, cantiques, sermons, Exposé, médias, playlists.
5. Modes plein écran, scène, OBS, NDI et HDMI chroma déjà intégrés.
6. Socle de thèmes, réglages simplifiés, aide clavier et diagnostic avant service déjà présents : les compléter plutôt que les recréer.

## Changements recommandés, par priorité

### Priorité 1 — Préserver les données et le direct

**Import des médias sans collision.** `app/utils/app_paths.py:219–231` compare nom et taille, ce qui peut réutiliser un mauvais contenu ou écraser un média référencé par d’autres playlists. Utiliser une identité de contenu, des noms uniques et une copie temporaire publiée atomiquement. N’insérer en base qu’après réussite.

**Initialisation des bases résistante aux interruptions.** `app/utils/app_paths.py:297–323` copie vers le nom définitif puis se fie à son existence. Une copie partielle peut empêcher la reprise. Copier temporairement, vérifier puis publier ; ne jamais remplacer silencieusement une base utilisateur existante.

**Pack éditorial et recherche cohérents.** `app/utils/app_paths.py:361–417`, `app/database/connection.py:669–674` et `main.py:176–194` dissocient remplacement de contenu et reconstruction de recherche. Un nombre identique de paragraphes ne prouve pas que leur index est à jour. Valider le pack et reconstruire dans la transaction ou conserver un marqueur durable de reconstruction nécessaire. Sauvegarder avant migration.

**Boucle d’annonces fiable.** `app/utils/announcement_controller.py:69–143` ne préserve pas complètement l’état du direct et ne transmet pas les visuels des médias. Introduire une capture/restauration publique de l’état live, transmettre les visuels, refuser un programme vide. Tester texte édité avant boucle, masquage, vidéo, playlist mixte, arrêt et navigation. Définir explicitement le sort des modifications faites pendant une boucle plutôt que supposer qu’elles appartiennent au programme précédent.

**Playlists transportables.** `app/utils/library_controller.py:1285–1323` exporte texte/référence sans conserver les médias. D’abord avertir de toute perte ; ensuite créer un format versionné avec manifeste et fichiers associés, compatible en lecture avec les anciens exports. La playlist source n’est pas détruite par l’export actuel.

### Priorité 1 — Sécuriser les limites réseau et la livraison

**OBS local par défaut.** `app/utils/obs_web_server.py:420` écoute sur toutes les interfaces alors que l’URL présentée est locale. Lier à `127.0.0.1`. Prévoir un mode réseau distinct et explicite si nécessaire ; protéger ses routes de données et médias. Ne pas casser silencieusement une installation utilisant OBS sur un second ordinateur. L’exposition effective dépend du pare-feu. Le masquage visuel ne constitue pas une protection de confidentialité.

**Configuration HTML sûre.** `app/utils/obs_web_server.py:246–256` insère du JSON directement dans un élément script. Préférer une réponse JSON séparée ou une sérialisation adaptée au contexte HTML. Conserver le rendu textuel par `textContent`.

**Installation NDI vérifiée.** `tools/setup_ndi_runtime.ps1:4,52–58` télécharge initialement en HTTP puis exécute sans vérification d’identité. Exiger HTTPS et une signature/identité d’éditeur approuvée avant exécution ; aucune exécution en cas d’échec.

**Publication strictement contrôlée.** `installer/sign.ps1:30–64`, `build_installer.bat:199–220` et `tools/publish_github.ps1:38–65` ne rendent pas toutes les erreurs de signature bloquantes. Séparer build de développement et release stricte ; vérifier certificat attendu, validité selon la politique de signature, horodatage et empreintes des artefacts avant publication. Ne pas supposer qu’un certificat présent implique une chaîne de confiance reconnue sur un autre poste.

### Priorité 2 — Réactivité et imports prévisibles

- **Réponses de recherche obsolètes** : numéro de génération par recherche/sélection ; une réponse ancienne ne doit pas remplacer les résultats récents (`library_controller.py:390–422,526–547,612–639`).
- **Recherche négative coûteuse** : distinguer FTS indisponible et FTS ne trouvant rien avant de lancer un parcours intégral (`dao_sermons.py:346–394`). Préserver les recherches par sous-chaîne si elles font partie du contrat produit.
- **Import asynchrone de bout en bout** : copie, parsing, doublons et insertion hors thread UI ; progression, annulation entre éléments et bilan succès/échecs. Transactions par lots raisonnables.
- **Doublons de cantiques** : identité exacte distincte de la recherche approximative ; « Grâce » ne doit pas être rejeté simplement parce que « Grâce infinie » existe (`dao_hymns.py:312–331`).
- **Office** : tri numérique au-delà de 99 slides, génération dans un cache propre et publication après réussite, verrou par présentation, pré-rendu depuis le fichier réellement stocké (`office_renderer.py:35–199`, `library_controller.py:1544–1554`).
- **PPTX** : suivre l’ordre officiel de `presentation.xml` et ses relations, pas les numéros des fichiers XML ; signaler tout import partiel (`pptx_parser.py:20–52`).
- **PDF/OCR** : diagnostic par page, pages ignorées visibles, OCR facultatif avec délai maximal ; budgets de pages, pixels et volumes décompressés. Les conversions natives lourdes gagnent à être isolées dans un processus annulable.

### Priorité 2 — Récupération et ressources

- Paramètres : distinguer absence et JSON invalide, conserver une dernière version valide et avertir avant réinitialisation (`settings.py:683–689,946–976`). Clarifier la politique d’instance unique plutôt que laisser deux instances partager un temporaire fixe.
- Mot de passe OBS : stockage Windows protégé, migration testée et exclusion des exports de diagnostic. Avec DPAPI, documenter que le secret ne se transporte pas simplement vers un autre utilisateur/poste.
- HTTP : fichiers envoyés par blocs, délais et files d’événements bornées ; ne conserver que l’état récent pour un consommateur en retard (`obs_web_server.py:278–306,349,384–386,478–486`).
- NDI : faire posséder/libérer les ressources natives par le thread émetteur et confirmer sa terminaison avant destruction. La concurrence suspectée reste à caractériser avec un SDK lent simulé.
- Sauvegarde complète : ajouter à la sauvegarde DB existante une archive avec médias, fonds et paramètres non secrets. Une sauvegarde n’est validée fonctionnellement qu’après restauration sur un profil vierge.
- Réordonnancement de playlist : échange de positions dans une transaction DAO unique (`library_controller.py:1226–1231`).

### Priorité 3 — Interface et architecture

**Régie plus claire, pas plus décorée.** Conserver la direction sombre et la lisibilité du contenu. Renforcer les distinctions « sélectionné », « à suivre », « diffusé », « masqué » avec texte et icône, sans dépendre seulement de la couleur.

**Préparation et direct.** Proposer un mode préparation qui permet de sélectionner/modifier sans diffusion involontaire, tout en conservant le mode de projection directe actuel pour les utilisateurs habitués. Ne pas modifier implicitement Entrée ou double-clic.

**Réglages par besoin.** Garder les cartes actuelles et présenter d’abord des profils « Projecteur », « OBS local », « HDMI mixeur » ; options avancées repliables. Une vue d’état commune montre écran choisi, sortie active et problème détecté.

**Retours utiles.** Un import doit afficher progression, éléments acceptés/ignorés et cause des erreurs. Étendre le diagnostic avant service aux fichiers manquants et aux médias des playlists.

**Accessibilité Windows.** Navigation clavier, focus visible, noms accessibles, thèmes clair/sombre et mise à l’échelle 100/125/150/200 %. La barre latérale a une largeur fixe de 210 pixels (`sidebar.py:108`) : mesurer sa place sur petits écrans avant de décider d’un mode compact. Ne pas appliquer mécaniquement des règles mobiles à une régie desktop.

**Découpage du code.** Extraire progressivement du contrôleur bibliothèque les services d’import, de recherche et de transfert de playlists. Exposer une API d’état live plutôt que manipuler les attributs privés. Mutualiser les travailleurs de fond et la politique d’erreurs. Supprimer les branchements réellement morts, dont `settingsApplied` (`main_window.py:227–230`), sans refonte mécanique de tous les gros fichiers.

**Performance mesurée.** Mesurer démarrage, recherche, changement de slide et rendu de l’aperçu avant de remplacer polling ou caches. Un compteur de révision dans le JSON ne résout pas à lui seul une lecture qui reste conditionnée uniquement par la date du fichier. Ne pas classer le tampon QImage du mixeur comme bug : sa copie actuelle protège correctement sa durée de vie.

## Plan de réalisation et critères d’acceptation

| Lot | Livrable | Critère d’acceptation |
|---|---|---|
| 0 — Socle de validation | Tests isolés du profil et des données du dépôt ; scénario de référence | Aucun test ne modifie données, paramètres ou cache réels ; résultat complet enregistré |
| 1 — Protection des données | Copies atomiques, collisions médias, paramètres récupérables, migrations FTS fiables | Interruptions simulées sans écrasement ; nouveau contenu trouvable après migration à nombre de lignes identique |
| 2 — Fiabilité du direct | État live explicite, annonces mixtes, écran initial, navigation documentée | Reprise fidèle après boucle ; aucune fausse activation à vide ; pas de régression du masquage de l’aperçu |
| 3 — Sorties et sécurité | OBS local par défaut, sérialisation sûre, ressources bornées, arrêt NDI robuste, secret protégé | Compatibilité OBS locale ; LAN explicite ; tests de durée de vie et de limites sans test offensif |
| 4 — Imports et recherche | Workers, générations de recherche, doublons exacts, Office/PPTX/PDF corrigés | Import annulable et bilan exact ; ordre correct sur 120 slides et PPTX réordonné ; dernière recherche toujours affichée |
| 5 — Transport et restauration | Export versionné avec médias, archive complète et diagnostic des dépendances | Aller-retour sur profil vierge sans média manquant ; anciens exports encore importables |
| 6 — Ergonomie et organisation | Régie clarifiée, options avancées repliables, services extraits progressivement | Parcours clavier et DPI validés ; pas de perte de fonction ; tests de comportement inchangés |
| 7 — Qualification et livraison | Environnement de build isolé, dépendances verrouillées, tests automatisés, signatures vérifiées | Suite complète réussie, test de restauration, essais matériels et vérification des artefacts avant publication autorisée |

Ordre : lot 0 avant les changements transversaux ; lots 1 et 2 d’abord ; correctifs réseau et téléchargement prioritaires en parallèle sur fichiers distincts ; ergonomie après stabilisation. La qualification et la documentation accompagnent chaque lot, pas seulement le dernier.

Politique de migration : sauvegarde vérifiée avant changement de schéma/format, compatibilité avec la lecture des anciens fichiers, pas de nettoyage destructif automatique. Chaque lot doit rester réversible sans réinitialiser la bibliothèque.

### Validation de sortie à prévoir

- Tests unitaires et d’intégration sur données temporaires.
- Tests d’interruption de copie, JSON invalide, cache incomplet, ordre de réponses inversé.
- Parcours réel : ouvrir un service, chercher, projeter, masquer, éditer, lancer/arrêter annonces, fermer/réouvrir.
- Comparaison des sorties avec texte court/long, référence haute/basse, ticker et média.
- Essais physiques multi-écrans, débranchement/rebranchement, OBS, réception NDI et chroma HDMI.
- Endurance sur une durée représentative d’un culte, avec suivi mémoire et réactivité.
- Restauration d’une sauvegarde et installation/mise à jour dans un environnement dédié.

## Corrections réalisées dans cette session (état final)

Suite complète : **262 tests verts, 0 échec** (3 min). `git diff --check` propre. Aucun commit effectué — à la décision du propriétaire.

**Lot 0 — Isolation des tests** : `tests/conftest.py` redirige tous les chemins de données/caches vers un bac à sable temporaire ; plus aucun test n’écrit dans le profil réel ou dans le dépôt (prouvé par `tests/test_test_isolation.py`).

**Lot 1 — Données** : import média par identité de contenu avec copie atomique (plus d’écrasement entre fichiers homonymes) ; initialisation des bases vérifiée avant publication (une copie interrompue ne bloque plus les démarrages suivants) ; migration du pack éditoriale et reconstruction FTS dans **une seule transaction** (+ correction URI SQLite `uri=True`, cause de l’échec initial) ; dédoublonnage de cantiques par identité exacte ; paramètres : sauvegarde `.bak` + récupération avec avertissement (`load_warning`), secret OBS protégé par DPAPI Windows (jamais en clair), fichier corrompu préservé avant réécriture ; instance unique Windows réellement bloquante.

**Lot 2 — Direct** : la boucle d’annonces capture/restaure l’état complet du direct (texte édité, masquage, lecture/boucle vidéo — timecode exclu, le protocole ne le transporte pas) ; les médias des playlists passent dans la boucle ; un programme vide ne l’active pas ; toute activation bibliothèque clos la boucle sans restauration obsolète (`abandon()` + crochet `before_manual_load`) ; les flèches naviguent d’emblée après l’arrêt de la boucle ; le surlignage Exposé ne suit plus les annonces.

**Lot 3 — Sorties et livraison** : serveur OBS lié à `127.0.0.1` par défaut (LAN explicite possible via API `host=`, non authentifié — à réserver à un réseau isolé) ; JSON inline échappé ; fichiers/vidéos en blocs bornés avec plages HTTP correctes (206) ; SSE plafonné (16 abonnés, file à dernier état, heartbeat, timeouts) ; validation d’enveloppe WebSocket ; **NDI** : le thread émetteur possède sa source et la détruit lui-même, `stop()` ne détruit jamais sous un thread vivant, redémarrage refusé pendant le nettoyage ; **scripts** : téléchargement NDI en HTTPS avec signature Authenticode vérifiée avant toute exécution (fail-closed), `sign.ps1` sans repli silencieux depuis une empreinte explicite + mode strict (`SIGN_STRICT`), build interrompu sur échec de signature en mode strict, publication GitHub refuse un installeur non signé (`-AllowUnsigned` pour dev uniquement).

**Lot 4 — Imports et recherche** : ordre PPTX via `presentation.xml` (bornes 1000 slides / 64 Mo, erreurs explicites) ; cache Office tri numérique jusqu’à 9999 pages, staging publié après réussite, verrou par présentation ; PDF budgets pages/pixels + diagnostics, OCR borné ; ordre 99+ corrigé ; pré-rendu depuis le fichier réellement stocké ; recherches avec générations (une réponse lente ne remplace plus une récente) ; transfert de playlists versionné avec médias embarqués (aller-retour vérifié octets à l’appui), anciens exports toujours lisibles ; réordonnancement transactionnel ; imports en workers avec bilan et annulation entre fichiers.

**Lot 5 — Transport** : API `create_backup_bundle` / `restore_backup_bundle` (ZIP avec manifeste SHA-256, secrets exclus, restauration uniquement vers un dossier vierge, jamais le profil actif) + boutons « Sauvegarde complète » et « Restaurer une archive » dans Réglages.

**Lot 6 — Interface** : avertissement de récupération des paramètres affiché une fois au démarrage ; diagnostics d’import restitués à l’opérateur.

### Non traité / limites connues

- PowerPoint dans la boucle d’annonces (les playlists normales le développent déjà).
- Position temporelle vidéo non restaurable (protocole `slide.json` sans timecode).
- Annulation des appels Office/PDF natifs : seulement entre fichiers et étapes.
- Validation `obs_websocket` imbriquée partielle (authentification coercée, statuts de réponse non exhaustifs).
- LAN OBS non authentifié : réservé réseau isolé/tunnel ; pas de réglage UI volontairement.
- CI/manifeste de dépendances non créés.
- **Validation physique manquante** : multi-écrans, projecteur, mélangeur HDMI, réception NDI et OBS réels non testés (suite offscreen uniquement) ; un seul écran disponible sur ce poste.
