# Phase 7 : rapport de la parité du reste (première partie)

**Date** : 11 novembre 2026. **Résultat** : l'entretien et les réglages sont dans la 3.0.
- **Reprise après coupure** : le direct survit à un arrêt brutal.
- **Historique du culte** (Ctrl+H), avec ses exports en tableur et en SRT.
- **Sauvegardes** de la base et des réglages.
- **Contrôle avant culte** (Ctrl+Shift+D).
- Une page **Réglages**.
- Le **mode PC modeste**.
- **Section suivante** au clavier (Ctrl+Alt+N).

La phase 7 est la plus grosse du plan (XL). Son livrable, la [liste de parité](PARITE.md), donne
chaque fonction de la 2.8 et où elle en est :
- 29 sont faites ;
- 3 sont faites en partie ;
- 16 restent à faire ;
- 2 sont retirées volontairement.

Ce qui reste est surtout **les médias** (images et vidéos dans la playlist, PowerPoint, diaporama),
**les écrans de l'Église**, **l'éditeur de cantiques** et **les imports** (PDF, Bibles).

## Ce qui a été construit

| Module | Contenu |
|---|---|
| `project-on/src/recovery.rs` | La reprise après coupure (`live_recovery.py` de la 2.8) :<br>– à chaque slide au direct, le programme entier, sa position, son origine et le masquage sont écrits d'un coup dans `data\live-recovery.json` ;<br>– une fermeture normale efface le fichier ;<br>– au démarrage suivant, un bandeau propose « Reprendre le direct » ;<br>– au-delà de 12 heures, rien n'est proposé. |
| `project-on/src/history.rs` | L'historique du culte (`service_log.py`) :<br>– chaque slide mis au direct, avec son heure, dans `data\historique\AAAA-MM-JJ.jsonl` (une ligne ajoutée à la fois, jamais de réécriture) ;<br>– Ctrl+H ouvre la fenêtre du jour ;<br>– export en **tableur** (CSV « ; », lisible par Excel en français) et en **sous-titres SRT**, calés sur le premier slide, au format de `to_srt` de la 2.8. |
| `project-on/src/maintenance.rs` | Les **sauvegardes** : la base (copie cohérente même pendant l'utilisation, l'API de SQLite) et `settings.json`, dans `data\sauvegardes\AAAA-MM-JJ_HHMMSS`. Les 10 dernières sont gardées. Le **contrôle avant culte** : base, écrans, polices, écrans Web, NDI, âge de la dernière sauvegarde, fichiers manquants de la playlist choisie. Chaque point dit quoi faire. |
| `project-on/src/settings_page.rs` | La page **Réglages** (rail, Ctrl+8) ; voir plus bas. |
| `po-program` | Le programme se sérialise (pour la reprise). |

## La page Réglages

- **Entretien** (en tête) : « Sauvegarder maintenant », la dernière sauvegarde et « Ouvrir le
  dossier », « Contrôle avant culte ».
- **Mode PC modeste** : sans transitions ni aperçus de designs, pour un ordinateur ancien.
- **Projection** :
  - le texte : police, graisse, tailles, capitales, couleurs, ombre, alignement, référence ;
  - le fond : couleur, dégradé, image, assombrissement ;
  - la transition et sa durée ;
  - l'écran de la salle.
- **Identification de Branham** : ses 4 styles.
- **Découpage des slides** : longs textes, strophes, refrain répété, compteur « (2/5) ».
- **Diffusion** : la couleur de clé des sorties HDMI (vert, magenta, bleu).
- **Raccourcis** : chaque touche se change ; la touche par défaut est rappelée.

Les réglages sont un brouillon : rien ne change avant « Enregistrer », et « Annuler les
changements » revient en arrière. L'écriture suit les règles de la 2.x : un seul coup, et une
copie `.bak`. Ce sont les réglages **de la bêta** : la 2.8 garde les siens. Les réglages propres à
la 3.0 (mode PC modeste, style de l'identification) sont rangés dans une section à part, que la
2.x ignore.

## Les raccourcis ajoutés

| Touche | Action |
|---|---|
| Ctrl+Alt+N | Déroulé : section suivante (comme la 2.8) |
| Ctrl+Shift+D | Contrôle avant culte (comme la 2.8) |
| Ctrl+H | Historique du culte (comme la 2.8) |
| Ctrl+7, Ctrl+8 | Pages Designs et Réglages |

Avec L, S et F8 (phase 6), il ne reste plus, dans l'aide, que les raccourcis des écrans de
l'Église.

## Les essais

| Essai | Vérifie |
|---|---|
| Reprise | Le programme, sa position, son origine, ses éléments et le masquage reviennent tels quels. Une fermeture normale ne laisse rien. Un fichier trop vieux ou abîmé est ignoré. |
| Historique | Une ligne par slide ; le même slide deux fois de suite n'est noté qu'une fois. Le CSV gère les guillemets et les « ; ». Le SRT est calé sur le début de la vidéo, avec 30 s au plus par slide. |
| Sauvegardes | Douze sauvegardes : les 10 dernières restent, la plus récente d'abord, et chacune s'ouvre. |
| Contrôle avant culte | Tout va bien : tout est vert. Un seul écran, un fichier de playlist manquant, pas de sauvegarde : chaque point est signalé avec ce qu'il faut faire. |
| Régie : arrêt brutal | Sur un vrai dossier de données d'essai : deux slides au direct, l'historique en compte deux. La régie disparaît sans fermeture normale ; la suivante propose la reprise, « Reprendre le direct » remet le slide 3:17 au direct, et la fermeture normale efface le fichier. |
| Régie : Réglages | Le mode PC modeste, enregistré, est écrit dans `settings.json` et retire les transitions. « Sauvegarder maintenant » crée la sauvegarde, avec les réglages. Le contrôle avant culte voit la base ouverte et la sauvegarde récente. |

## Ce qui reste (voir la liste de parité)

- **Médias** : images et vidéos dans la playlist et la projection, fond vidéo et Ken Burns,
  PowerPoint, diaporama d'un dossier, import et export d'une playlist. C'est le plus gros
  morceau : il faut un lecteur vidéo dans la régie (celui de Pgraphics, à reprendre).
- **L'Église** : écran d'accueil, orateur du jour, réseaux sociaux, image de citation, galerie,
  profil de l'église.
- **Données** :
  - éditeur de cantiques ;
  - imports PDF et Bibles ;
  - restauration d'une sauvegarde ;
  - archive avec médias ;
  - rapport imprimable du culte.
- **Diffusion** :
  - pilotage d'OBS (WebSocket) ;
  - réglages détaillés du bandeau et de la sortie HDMI dans la page Réglages (pour l'instant, ceux
    de la 2.x sont repris tels quels).
- **Mise à jour de l'application** : avec l'installateur de la bascule.

**Conséquence pour la phase 8** : la 3.0 ne peut pas encore **remplacer** la 2.8 dans un culte qui
projette des vidéos, des PowerPoint ou les écrans de l'Église. La bascule doit attendre ces
morceaux, ou se faire en gardant la 2.8 à côté pour eux. La phase 8 prépare donc l'installateur de
la bascule, sans le publier ni retirer la 2.8 : ces deux gestes vous seront demandés.

## Refaire les vérifications

```powershell
cd project-on-rs
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```
