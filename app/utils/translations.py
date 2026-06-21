"""Translation system for Project-On.
Supports French (fr) and English (en).
"""

from __future__ import annotations

# Current language
_current_language: str = "fr"

# Translation dictionaries
_translations: dict[str, dict[str, str]] = {
    # ===== GENERAL =====
    "app_name": {"fr": "Project-On", "en": "Project-On"},
    "save": {"fr": "Enregistrer", "en": "Save"},
    "cancel": {"fr": "Annuler", "en": "Cancel"},
    "ok": {"fr": "OK", "en": "OK"},
    "yes": {"fr": "Oui", "en": "Yes"},
    "no": {"fr": "Non", "en": "No"},
    "delete": {"fr": "Supprimer", "en": "Delete"},
    "add": {"fr": "Ajouter", "en": "Add"},
    "edit": {"fr": "Modifier", "en": "Edit"},
    "close": {"fr": "Fermer", "en": "Close"},
    "search": {"fr": "Rechercher...", "en": "Search..."},
    "loading": {"fr": "Chargement...", "en": "Loading..."},
    # ===== PLAYLIST =====
    "playlist": {"fr": "Playlist", "en": "Playlist"},
    "playlist_empty": {"fr": "Playlist vide", "en": "Empty playlist"},
    "playlist_empty_hint": {
        "fr": "Double-cliquez sur un élément\npour l'ajouter",
        "en": "Double-click an item\nto add it",
    },
    "playlist_add": {"fr": "Ajouter", "en": "Add"},
    "playlist_folder": {"fr": "Dossier", "en": "Folder"},
    "playlist_list_mode": {"fr": "Liste", "en": "List"},
    "playlist_grid_mode": {"fr": "Grille", "en": "Grid"},
    "playlist_clear": {"fr": "Vider la playlist", "en": "Clear playlist"},
    "playlist_remove": {"fr": "Supprimer l'élément", "en": "Remove item"},
    "playlist_elements": {"fr": "éléments", "en": "items"},
    "playlist_element": {"fr": "élément", "en": "item"},
    "playlist_root": {"fr": "Racine", "en": "Root"},
    "confirm_delete": {"fr": "Confirmer la suppression", "en": "Confirm deletion"},
    "confirm_delete_folder_msg": {
        "fr": "Supprimer ce dossier et toutes les slides qu'il contient ?",
        "en": "Delete this folder and every slide inside it?",
    },
    "confirm_clear_playlist": {"fr": "Vider la playlist", "en": "Clear playlist"},
    "confirm_clear_playlist_msg": {
        "fr": "Voulez-vous vraiment supprimer tous les éléments de la playlist ?",
        "en": "Do you really want to remove every item from the playlist?",
    },
    "move_up": {"fr": "Déplacer vers le haut", "en": "Move up"},
    "move_down": {"fr": "Déplacer vers le bas", "en": "Move down"},
    "duplicate": {"fr": "Dupliquer", "en": "Duplicate"},
    "remove": {"fr": "Supprimer", "en": "Remove"},
    "new_folder": {"fr": "Nouveau dossier", "en": "New folder"},
    "folder_name": {"fr": "Nom du dossier:", "en": "Folder name:"},
    "delete_folder": {"fr": "Supprimer le dossier", "en": "Delete folder"},
    "delete_folder_confirm": {
        "fr": 'Voulez-vous vraiment supprimer le dossier "{name}" ?\n\nLes slides dans ce dossier seront également supprimés.',
        "en": 'Do you really want to delete the folder "{name}"?\n\nSlides in this folder will also be deleted.',
    },
    # ===== CUSTOM SLIDE =====
    "custom_slide_title": {
        "fr": "Nouvelle slide personnalisée",
        "en": "New custom slide",
    },
    "custom_slide_name": {"fr": "Titre (optionnel):", "en": "Title (optional):"},
    "custom_slide_name_placeholder": {
        "fr": "Ex: Annonce, Bienvenue...",
        "en": "E.g.: Announcement, Welcome...",
    },
    "custom_slide_text": {"fr": "Texte:", "en": "Text:"},
    "custom_slide_text_placeholder": {
        "fr": "Entrez le texte à afficher...",
        "en": "Enter the text to display...",
    },
    "add_custom_slide": {"fr": "Ajouter une slide de texte", "en": "Add a text slide"},
    "add_image_slide": {"fr": "Ajouter une image", "en": "Add image"},
    "custom_slide_default": {"fr": "Slide personnalisée", "en": "Custom slide"},
    "custom_slide_split": {"fr": "Découpage:", "en": "Split:"},
    "custom_slide_split_auto": {
        "fr": "Automatique (intelligent)",
        "en": "Automatic (smart)",
    },
    "custom_slide_split_paragraph": {
        "fr": "Par paragraphe (ligne vide)",
        "en": "By paragraph (blank line)",
    },
    "custom_slide_split_single": {"fr": "Une seule diapo", "en": "Single slide"},
    "custom_slide_count_empty": {"fr": "Aucun texte", "en": "No text"},
    "characters": {"fr": "caractères", "en": "characters"},
    "slide": {"fr": "diapo", "en": "slide"},
    "slides": {"fr": "diapos", "en": "slides"},
    # ===== IMAGE BACKGROUNDS =====
    "select_image": {"fr": "Sélectionner une image", "en": "Select an image"},
    "set_background": {"fr": "Image de fond...", "en": "Background image..."},
    "remove_background": {"fr": "Retirer l'image de fond", "en": "Remove background"},
    "backgrounds_title": {"fr": "Choisir une image de fond", "en": "Choose background image"},
    "browse_image": {"fr": "Parcourir...", "en": "Browse..."},
    "no_background": {"fr": "Aucun fond", "en": "No background"},
    "no_backgrounds_hint": {
        "fr": "Aucune image. Cliquez sur «Parcourir» pour en ajouter.",
        "en": "No images yet. Click «Browse» to add one.",
    },
    # ===== LIBRARY =====
    "bible": {"fr": "Bible", "en": "Bible"},
    "hymns": {"fr": "Cantiques", "en": "Hymns"},
    "sermons": {"fr": "Prédications", "en": "Sermons"},
    "settings": {"fr": "Paramètres", "en": "Settings"},
    "add_to_playlist": {"fr": "Ajouter à la playlist", "en": "Add to playlist"},
    "add_verse_tooltip": {
        "fr": "Ajouter le verset sélectionné à la playlist",
        "en": "Add selected verse to playlist",
    },
    "add_hymn_tooltip": {
        "fr": "Ajouter toutes les strophes du cantique sélectionné",
        "en": "Add all stanzas of selected hymn",
    },
    "import": {"fr": "Importer", "en": "Import"},
    "import_hymns": {"fr": "Importer des cantiques", "en": "Import hymns"},
    "import_pptx_file": {
        "fr": "Importer un fichier PPTX...",
        "en": "Import a PPTX file...",
    },
    "import_pptx_folder": {
        "fr": "Importer un dossier de PPTX...",
        "en": "Import a PPTX folder...",
    },
    "import_pdf_file": {
        "fr": "Importer un fichier PDF...",
        "en": "Import a PDF file...",
    },
    "clear_all_hymns": {
        "fr": "Vider tous les cantiques...",
        "en": "Clear all hymns...",
    },
    "delete_hymn": {
        "fr": "Supprimer le cantique sélectionné",
        "en": "Delete selected hymn",
    },
    "hymns_count": {"fr": "cantiques", "en": "hymns"},
    # ===== PREVIEW =====
    "preview": {"fr": "Aperçu", "en": "Preview"},
    "live": {"fr": "EN DIRECT", "en": "LIVE"},
    "hidden": {"fr": "MASQUÉ", "en": "HIDDEN"},
    "show": {"fr": "Afficher", "en": "Show"},
    "hide": {"fr": "Masquer", "en": "Hide"},
    "hide_preview": {"fr": "Masquer l'aperçu", "en": "Hide preview"},
    "show_preview": {"fr": "Afficher l'aperçu", "en": "Show preview"},
    "previous": {"fr": "Précédent", "en": "Previous"},
    "next": {"fr": "Suivant", "en": "Next"},
    "project": {"fr": "Projeter", "en": "Project"},
    "obs": {"fr": "OBS", "en": "OBS"},
    "clear_live": {"fr": "Effacer", "en": "Clear"},
    "quick_edit": {"fr": "Modifier", "en": "Quick Edit"},
    "logo_mode": {"fr": "Logo", "en": "Logo"},
    # ===== SETTINGS =====
    "settings_title": {"fr": "Paramètres", "en": "Settings"},
    "settings_subtitle": {
        "fr": "Personnalisez votre expérience Project-On",
        "en": "Customize your Project-On experience",
    },
    "display": {"fr": "Affichage", "en": "Display"},
    "local_projection": {"fr": "Projection locale", "en": "Local projection"},
    "local_projection_desc": {
        "fr": "Écran secondaire, police et taille du texte",
        "en": "Secondary screen, font and text size",
    },
    "streaming_obs": {"fr": "Streaming & OBS", "en": "Streaming & OBS"},
    "connectivity": {"fr": "Connectivité", "en": "Connectivity"},
    "connectivity_desc": {
        "fr": "Serveur Web local et sortie NDI",
        "en": "Local Web server and NDI output",
    },
    "lower_third_style": {"fr": "Style Lower Third", "en": "Lower Third Style"},
    "lower_third_style_desc": {
        "fr": "Apparence, couleurs, animations et effets",
        "en": "Appearance, colors, animations and effects",
    },
    "application": {"fr": "Application", "en": "Application"},
    "appearance": {"fr": "Apparence", "en": "Appearance"},
    "appearance_desc": {
        "fr": "Theme et langue de l'interface",
        "en": "Interface theme and language",
    },
    "about": {"fr": "À propos", "en": "About"},
    "about_desc": {
        "fr": "Version, licence et informations",
        "en": "Version, license and information",
    },
    # ===== APPEARANCE SETTINGS =====
    "appearance_title": {"fr": "Apparence", "en": "Appearance"},
    "appearance_subtitle": {
        "fr": "Personnalisez l'apparence de l'application",
        "en": "Customize the application appearance",
    },
    "theme": {"fr": "Theme", "en": "Theme"},
    "dark_theme": {"fr": "Mode sombre", "en": "Dark mode"},
    "dark_theme_desc": {
        "fr": "Interface sombre et contrastee",
        "en": "Dark, high-contrast interface",
    },
    "light_theme": {"fr": "Mode clair", "en": "Light mode"},
    "light_theme_desc": {
        "fr": "Interface claire et douce",
        "en": "Bright, soft interface",
    },
    "language": {"fr": "Langue", "en": "Language"},
    "french": {"fr": "Français", "en": "French"},
    "french_desc": {"fr": "Interface en français", "en": "Interface in French"},
    "english": {"fr": "English", "en": "English"},
    "english_desc": {"fr": "Interface in English", "en": "Interface in English"},
    "restart_required": {
        "fr": "Note: Certains changements nécessitent un redémarrage de l'application.",
        "en": "Note: Some changes require restarting the application.",
    },
    "settings_saved": {"fr": "Paramètres enregistrés", "en": "Settings saved"},
    "settings_saved_msg": {
        "fr": "Les paramètres d'apparence ont été enregistrés.\n\nRedémarrez l'application pour appliquer les changements.",
        "en": "Appearance settings have been saved.\n\nRestart the application to apply changes.",
    },
    # ===== BIBLE =====
    "bible_book": {"fr": "Livre", "en": "Book"},
    "bible_chapter": {"fr": "Chapitre", "en": "Chapter"},
    "bible_verse": {"fr": "Verset", "en": "Verse"},
    "bible_version": {"fr": "Version", "en": "Version"},
    # ===== OBS =====
    "obs_server_started": {"fr": "Serveur actif", "en": "Server active"},
    "obs_url_info": {
        "fr": "URL pour OBS (source Navigateur):",
        "en": "URL for OBS (Browser source):",
    },
    "copy_url": {"fr": "Copier", "en": "Copy"},
    "open_browser": {"fr": "Ouvrir dans navigateur", "en": "Open in browser"},
    "server_not_started": {"fr": "Serveur arrêté", "en": "Server stopped"},
    "server_error": {
        "fr": "Impossible de démarrer le serveur web OBS. Vérifiez que le port est libre.",
        "en": "Unable to start OBS web server. Check that the port is free.",
    },
    "start": {"fr": "Démarrer", "en": "Start"},
    "stop": {"fr": "Arrêter", "en": "Stop"},
    "web_server": {"fr": "Serveur Web", "en": "Web Server"},
    "web_server_desc": {
        "fr": "Affiche les slides via une source Navigateur dans OBS",
        "en": "Displays slides via a Browser source in OBS",
    },
    "ndi_desc": {
        "fr": "Envoie le flux vidéo via NDI sur le réseau local",
        "en": "Sends video stream via NDI on the local network",
    },
    "port_label": {"fr": "Port du serveur", "en": "Server port"},
    "port_desc": {
        "fr": "Port local pour le serveur web",
        "en": "Local port for web server",
    },
    "ndi_source_name": {"fr": "Nom de la source", "en": "Source name"},
    "ndi_source_desc": {"fr": "Nom visible dans OBS", "en": "Name visible in OBS"},
    "ndi_unavailable": {
        "fr": "⚠️ NDI SDK non disponible sur ce système",
        "en": "⚠️ NDI SDK not available on this system",
    },
    "recommended": {"fr": "Recommandé", "en": "Recommended"},
    # ===== PDF IMPORT =====
    "pdf_import_title": {"fr": "Importer depuis {name}", "en": "Import from {name}"},
    "pdf_found": {
        "fr": "📄 {count} cantiques trouvés dans {name}",
        "en": "📄 {count} hymns found in {name}",
    },
    "pdf_config": {"fr": "Configuration", "en": "Configuration"},
    "pdf_prefix": {"fr": "Préfixe:", "en": "Prefix:"},
    "pdf_prefix_placeholder": {
        "fr": "Ex: CI, CV, PN, AD",
        "en": "E.g.: CI, CV, PN, AD",
    },
    "pdf_start_number": {"fr": "Numéro de départ:", "en": "Starting number:"},
    "pdf_hymns_to_import": {"fr": "Cantiques à importer:", "en": "Hymns to import:"},
    "pdf_preview": {"fr": "Aperçu:", "en": "Preview:"},
    "pdf_select_all": {"fr": "Tout sélectionner", "en": "Select all"},
    "pdf_select_none": {"fr": "Tout désélectionner", "en": "Select none"},
    "pdf_import": {"fr": "Importer", "en": "Import"},
    "pdf_status": {
        "fr": "{selected}/{total} cantiques sélectionnés pour l'import",
        "en": "{selected}/{total} hymns selected for import",
    },
    "pdf_untitled": {"fr": "Sans titre", "en": "Untitled"},
    "pdf_stanza": {"fr": "Strophe {num}:", "en": "Verse {num}:"},
    "pdf_default_prefix": {"fr": "PDF", "en": "PDF"},
    # ===== SHORTCUTS DIALOG =====
    "keyboard_shortcuts": {"fr": "Raccourcis clavier", "en": "Keyboard shortcuts"},
    "shortcut_action": {"fr": "Action", "en": "Action"},
    "shortcut_key": {"fr": "Raccourci", "en": "Shortcut"},
    "shortcut_nav_next": {"fr": "Slide suivant", "en": "Next slide"},
    "shortcut_nav_prev": {"fr": "Slide précédent", "en": "Previous slide"},
    "shortcut_hide": {
        "fr": "Masquer / Afficher la projection",
        "en": "Toggle projection visibility",
    },
    "shortcut_delete": {
        "fr": "Supprimer l'élément sélectionné",
        "en": "Delete selected item",
    },
    "shortcut_search": {
        "fr": "Rechercher dans la playlist",
        "en": "Search in playlist",
    },
    "shortcut_undo": {"fr": "Annuler la dernière action", "en": "Undo last action"},
    "shortcut_move_up": {"fr": "Déplacer l'élément vers le haut", "en": "Move item up"},
    "shortcut_move_down": {
        "fr": "Déplacer l'élément vers le bas",
        "en": "Move item down",
    },
    "shortcut_duplicate": {"fr": "Dupliquer l'élément", "en": "Duplicate item"},
    "shortcut_help": {"fr": "Afficher les raccourcis", "en": "Show shortcuts"},
    "shortcut_tab_bible": {"fr": "Onglet Bible", "en": "Bible tab"},
    "shortcut_tab_hymns": {"fr": "Onglet Cantiques", "en": "Hymns tab"},
    "shortcut_tab_sermons": {"fr": "Onglet Prédications", "en": "Sermons tab"},
    "shortcut_tab_expose": {"fr": "Onglet Exposé", "en": "Exposé tab"},
    "shortcut_tab_settings": {"fr": "Onglet Paramètres", "en": "Settings tab"},
    "shortcut_projection": {
        "fr": "Ouvrir / Fermer la projection",
        "en": "Open / Close projection",
    },
    "shortcut_escape": {"fr": "Fermer la projection", "en": "Close projection"},
    # ===== UNDO =====
    "undo": {"fr": "Annuler", "en": "Undo"},
    "nothing_to_undo": {"fr": "Rien à annuler", "en": "Nothing to undo"},
    # ===== MULTI-VERSE =====
    "add_verses": {"fr": "Ajouter les versets", "en": "Add verses"},
    "verses_selected": {
        "fr": "{count} versets sélectionnés",
        "en": "{count} verses selected",
    },
    # ===== TIMER =====
    "timer_start": {"fr": "Démarrer", "en": "Start"},
    "timer_pause": {"fr": "Pause", "en": "Pause"},
    "timer_reset": {"fr": "Réinitialiser", "en": "Reset"},
    # ===== RENAME FOLDER =====
    "rename_folder": {"fr": "Renommer le dossier", "en": "Rename folder"},
    "rename_folder_prompt": {"fr": "Nouveau nom:", "en": "New name:"},
    # ===== PREVIEW PANEL =====
    "projection": {"fr": "Projection", "en": "Projection"},
    "waiting": {"fr": "En attente", "en": "Waiting"},
    "ready_to_project": {"fr": "Prêt à diffuser", "en": "Ready to project"},
    "projection_active": {"fr": "Projection active", "en": "Projection active"},
    "output_hidden": {"fr": "Sortie masquée", "en": "Output hidden"},
    # ===== EVENT SLIDES =====
    "add_event_slide": {"fr": "Ajouter une slide d'événement", "en": "Add an event slide"},
    # ===== OBS =====
    "obs_server_title": {"fr": "Serveur OBS", "en": "OBS Server"},
    "server_error_detail": {
        "fr": "Impossible de démarrer le serveur web OBS. Vérifiez que le port est libre.",
        "en": "Unable to start OBS web server. Check that the port is free.",
    },
    "ndi_runtime_missing": {
        "fr": "Installez le NDI Runtime et les dépendances Python NDI.",
        "en": "Install NDI Runtime and Python NDI dependencies.",
    },
    "ndi_unavailable_title": {"fr": "NDI indisponible", "en": "NDI unavailable"},
    "ndi_unavailable_detail": {
        "fr": "Impossible de démarrer NDI.",
        "en": "Unable to start NDI.",
    },
    "ndi_active": {"fr": "NDI Actif", "en": "NDI Active"},
    "ndi_active_detail": {
        "fr": "Sortie NDI démarrée.\nNom de la source: {name}",
        "en": "NDI output started.\nSource name: {name}",
    },
    "project": {"fr": "Projeter", "en": "Project"},
    "hide": {"fr": "Masquer", "en": "Hide"},
    "show": {"fr": "Afficher", "en": "Show"},
    # ===== CONFERENCE / EVENT SLIDES =====
    "event_slides": {"fr": "Slides événement", "en": "Event slides"},
    "event_type": {"fr": "Type d'événement", "en": "Event type"},
    "event_general": {"fr": "Général / Association", "en": "General / Association"},
    "event_corporate": {"fr": "Entreprise / Corporate", "en": "Corporate"},
    "event_training": {"fr": "Formation / Cours", "en": "Training / Course"},
    "event_workshop": {"fr": "Atelier pratique", "en": "Workshop"},
    "event_webinar": {"fr": "Webinaire / Live", "en": "Webinar / Live"},
    "event_panel": {"fr": "Panel / Débat", "en": "Panel / Debate"},
    "event_expo": {"fr": "Salon / Expo", "en": "Trade show / Expo"},
    "slide_format": {"fr": "Format de slide", "en": "Slide format"},
    "slide_kit": {"fr": "Kit événement complet", "en": "Full event kit"},
    "slide_session": {"fr": "Titre / Session", "en": "Title / Session"},
    "slide_agenda": {"fr": "Agenda", "en": "Agenda"},
    "slide_speaker": {"fr": "Intervenant / Invité", "en": "Speaker / Guest"},
    "slide_panel": {"fr": "Panel / Table ronde", "en": "Panel / Round table"},
    "slide_break": {"fr": "Pause", "en": "Break"},
    "slide_networking": {"fr": "Networking", "en": "Networking"},
    "slide_qa": {"fr": "Questions / Réponses", "en": "Q&A"},
    "slide_announcement": {"fr": "Annonce", "en": "Announcement"},
    "slide_sponsor": {"fr": "Sponsor / Partenaire", "en": "Sponsor / Partner"},
    "slide_info": {"fr": "Infos pratiques", "en": "Practical info"},
    "slide_countdown": {"fr": "Compte à rebours", "en": "Countdown"},
    "slide_cta": {"fr": "Appel à l'action", "en": "Call to action"},
    "event_title": {"fr": "Titre / Thème", "en": "Title / Theme"},
    "event_title_placeholder": {
        "fr": "Ex: Leadership, IA, formation sécurité, lancement produit",
        "en": "E.g.: Leadership, AI, safety training, product launch",
    },
    "event_speaker": {"fr": "Intervenant, hôte ou panelistes", "en": "Speaker, host or panelists"},
    "event_speaker_placeholder": {
        "fr": "Ex: Marie Dupont | Jean Paul | Équipe produit",
        "en": "E.g.: John Doe | Jane Smith | Product team",
    },
    "event_org": {"fr": "Organisation / Partenaire", "en": "Organization / Partner"},
    "event_org_placeholder": {
        "fr": "Ex: Project-On, ACME, Université, Sponsor Gold",
        "en": "E.g.: Project-On, ACME, University, Gold Sponsor",
    },
    "event_detail": {"fr": "Lieu, horaire, lien ou sous-titre", "en": "Location, time, link or subtitle"},
    "event_detail_placeholder": {
        "fr": "Ex: Salle A - 14h00 | project-on.app/live",
        "en": "E.g.: Room A - 2:00 PM | project-on.app/live",
    },
    "event_duration": {"fr": "Durée / Compte à rebours", "en": "Duration / Countdown"},
    "minutes": {"fr": "min", "en": "min"},
    "event_notes": {"fr": "Agenda, message ou annonce", "en": "Agenda, message or announcement"},
    "event_notes_placeholder": {
        "fr": "Une ligne par point d'agenda, consigne, annonce ou appel à l'action",
        "en": "One line per agenda item, instruction, announcement or call to action",
    },
    "event_kit_hint": {
        "fr": "Le kit adapte les slides au type d'événement: accueil, agenda, session, pause, questions, infos et fin.",
        "en": "The kit adapts slides to the event type: welcome, agenda, session, break, Q&A, info and closing.",
    },
    # ===== SLIDE CONTENT TEMPLATES =====
    "agenda_header": {"fr": "AGENDA", "en": "AGENDA"},
    "panel_header": {"fr": "PANEL / TABLE RONDE", "en": "PANEL / ROUND TABLE"},
    "qa_header": {"fr": "QUESTIONS / RÉPONSES", "en": "QUESTIONS / ANSWERS"},
    "sponsor_header": {"fr": "MERCI À NOTRE PARTENAIRE", "en": "THANK YOU TO OUR PARTNER"},
    "info_header": {"fr": "INFOS PRATIQUES", "en": "PRACTICAL INFO"},
    "cta_header": {"fr": "PROCHAINE ÉTAPE", "en": "NEXT STEP"},
    "networking_header": {"fr": "NETWORKING", "en": "NETWORKING"},
    "break_template": {"fr": "PAUSE\nRetour dans {minutes} min", "en": "BREAK\nBack in {minutes} min"},
    "countdown_template": {"fr": "DÉBUT DANS\n{minutes}:00", "en": "STARTING IN\n{minutes}:00"},
    "networking_default_text": {"fr": "Rencontrez les participants", "en": "Meet the participants"},
    "info_default_text": {"fr": "Wi-Fi | Sorties | Assistance", "en": "Wi-Fi | Exits | Support"},
    "cta_default_text": {"fr": "Scannez le QR code / Visitez le lien", "en": "Scan the QR code / Visit the link"},
    "agenda_default_1": {"fr": "Accueil", "en": "Welcome"},
    "agenda_default_2": {"fr": "Session principale", "en": "Main session"},
    "agenda_default_3": {"fr": "Pause", "en": "Break"},
    "agenda_default_4": {"fr": "Questions / Réponses", "en": "Q&A"},
    "default_title_corporate": {"fr": "Conférence entreprise", "en": "Corporate conference"},
    "default_title_training": {"fr": "Session de formation", "en": "Training session"},
    "default_title_workshop": {"fr": "Atelier pratique", "en": "Workshop"},
    "default_title_webinar": {"fr": "Webinaire", "en": "Webinar"},
    "default_title_panel": {"fr": "Panel", "en": "Panel"},
    "default_title_expo": {"fr": "Salon / Expo", "en": "Trade show / Expo"},
    "default_title_event": {"fr": "Événement", "en": "Event"},
    "kit_welcome": {"fr": "Accueil", "en": "Welcome"},
    "kit_welcome_header": {"fr": "BIENVENUE", "en": "WELCOME"},
    "kit_objectives": {"fr": "Objectifs", "en": "Objectives"},
    "kit_objectives_header": {"fr": "OBJECTIFS", "en": "OBJECTIVES"},
    "kit_objectives_default": {"fr": "Comprendre | Pratiquer | Appliquer", "en": "Understand | Practice | Apply"},
    "kit_exercise": {"fr": "Exercice", "en": "Exercise"},
    "kit_exercise_text": {"fr": "EXERCICE PRATIQUE\nTravail individuel ou en groupe", "en": "PRACTICAL EXERCISE\nIndividual or group work"},
    "kit_workshop": {"fr": "Atelier", "en": "Workshop"},
    "kit_workshop_header": {"fr": "ATELIER", "en": "WORKSHOP"},
    "kit_workshop_default": {"fr": "Consignes et objectifs", "en": "Instructions and objectives"},
    "kit_debrief": {"fr": "Restitution", "en": "Debrief"},
    "kit_debrief_text": {"fr": "RESTITUTION\nPartage des résultats", "en": "DEBRIEF\nSharing results"},
    "kit_live": {"fr": "Live", "en": "Live"},
    "kit_live_header": {"fr": "LE LIVE COMMENCE", "en": "THE LIVE BEGINS"},
    "kit_interaction_webinar": {"fr": "POSEZ VOS QUESTIONS\nUtilisez le chat", "en": "ASK YOUR QUESTIONS\nUse the chat"},
    "kit_interaction_general": {"fr": "PARTICIPATION\nQuestions et échanges", "en": "PARTICIPATION\nQuestions and discussion"},
    "kit_questions_panel": {"fr": "QUESTIONS DU PUBLIC\nPréparez vos interventions", "en": "AUDIENCE QUESTIONS\nPrepare your interventions"},
    "kit_expo": {"fr": "Expo", "en": "Expo"},
    "kit_expo_header": {"fr": "À DÉCOUVRIR", "en": "TO DISCOVER"},
    "kit_networking_expo": {"fr": "NETWORKING\nRencontrez les exposants", "en": "NETWORKING\nMeet the exhibitors"},
    "kit_decision": {"fr": "Décision", "en": "Decision"},
    "kit_decision_text": {"fr": "POINTS CLÉS\nActions et prochaines étapes", "en": "KEY POINTS\nActions and next steps"},
    "kit_questions": {"fr": "Questions", "en": "Questions"},
    "kit_closing": {"fr": "Clôture", "en": "Closing"},
    "kit_closing_header": {"fr": "MERCI", "en": "THANK YOU"},
    "kit_closing_default": {"fr": "Merci pour votre participation", "en": "Thank you for your participation"},
    "info_default_footer": {"fr": "Merci de suivre les indications de l'équipe", "en": "Please follow the team's guidance"},
    "slide_session": {"fr": "Session", "en": "Session"},
    # ===== QUICK EDIT DIALOG =====
    "quick_edit_ref": {"fr": "Référence / Titre :", "en": "Reference / Title :"},
    "quick_edit_text": {"fr": "Texte de la Slide :", "en": "Slide text :"},
    "quick_edit_apply": {"fr": "Appliquer", "en": "Apply"},
    # ===== SETTINGS DIALOGS =====
    "local_projection_title": {"fr": "Paramètres de projection locale", "en": "Local projection settings"},
    "show_content_frame": {"fr": "Afficher un cadre de contenu", "en": "Show content frame"},
    "show_reference": {"fr": "Afficher la référence", "en": "Show reference"},
    "obs_lower_third_title": {"fr": "Paramètres OBS Lower Third", "en": "OBS Lower Third settings"},
    "show_bible_ref": {"fr": "Afficher la référence biblique", "en": "Show Bible reference"},
    "show_background": {"fr": "Afficher l'arrière-plan", "en": "Show background"},
}


def set_language(lang: str) -> None:
    """Set the current language."""
    global _current_language
    if lang in ("fr", "en"):
        _current_language = lang


def get_language() -> str:
    """Get the current language."""
    return _current_language


def tr(key: str, **kwargs) -> str:
    """Get translated string for the given key.
    Supports format placeholders like {name}.
    """
    if key not in _translations:
        return key

    text = _translations[key].get(_current_language, _translations[key].get("fr", key))

    # Apply format placeholders
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass

    return text


def t(key: str, **kwargs) -> str:
    """Alias for tr()."""
    return tr(key, **kwargs)
