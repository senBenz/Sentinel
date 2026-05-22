# SENTINEL - Documentation des Métriques de Détection de Fatigue
Le pipeline complet fonctionne comme suit :

```
Caméra IR
   │
   ▼
MediaPipe FaceLandmarker (478 landmarks)
   │
   ├──▶ 6 landmarks par oeil ──▶ EAR ──▶ PERCLOS + Blink Rate + Blink Duration
   ├──▶ Landmarks bouche ──▶ MAR ──▶ Détection de bâillement
   └──▶ Landmarks visage ──▶ solvePnP ──▶ Head Pose (pitch, yaw, roll)
                                              │
                                              ▼
                                     Score de fatigue (0-100)
                                              │
                                              ▼
                                     Machine à états (5 niveaux)
                                              │
                                              ▼
                                     Actions (alertes, actuation)
```

---

## 1. EAR (Eye Aspect Ratio)

### Description

L'EAR mesure le degré d'ouverture de l'oeil à un instant donné. Il est calculé à partir de 6 landmarks situés sur le contour de chaque oeil : 2 points horizontaux (coins interne et externe) et 4 points verticaux (paupières supérieure et inférieure).

### Formule

```
EAR = (||p2 - p6|| + ||p3 - p5||) / (2 * ||p1 - p4||)
```

Où :
- p1 et p4 sont les coins horizontaux de l'oeil (externe et interne)
- p2 et p6 sont les points supérieur et inférieur de la paupière côté externe
- p3 et p5 sont les points supérieur et inférieur de la paupière côté interne
- || || représente la distance euclidienne entre deux points

### Landmarks MediaPipe utilisés

| Oeil | Indices des landmarks |
|------|----------------------|
| Oeil droit | 33, 160, 158, 133, 153, 144 |
| Oeil gauche | 362, 385, 387, 263, 373, 380 |

### Valeurs de référence

| État | Valeur EAR |
|------|-----------|
| Oeil grand ouvert | 0.30 - 0.35 |
| Oeil ouvert normalement | 0.25 - 0.30 |
| Oeil partiellement fermé | 0.15 - 0.20 |
| Oeil fermé | 0.05 - 0.10 |

### Seuil de décision

```
EAR < 0.20 = oeil considéré fermé
```

Ce seuil peut varier selon la morphologie du conducteur. Une phase de calibration au démarrage du système (5 secondes yeux ouverts) permet de personnaliser ce seuil.

### Rôle dans le système

L'EAR n'entre pas directement dans le score final. C'est la matière première à partir de laquelle sont calculées 3 métriques dérivées : le PERCLOS, le Blink Rate et la Blink Duration. Utiliser l'EAR brut dans le score reviendrait à compter deux fois la même information.

---

## 2. PERCLOS (Percentage of Eye Closure)

### Description

Le PERCLOS est le pourcentage du temps pendant lequel les yeux du conducteur sont fermés, calculé sur une fenêtre glissante de 30 secondes. C'est le standard industriel de référence pour la détection de somnolence, validé par la NHTSA (National Highway Traffic Safety Administration, États-Unis).

### Formule

```
PERCLOS = (nombre de frames où EAR < seuil) / (nombre total de frames sur 30s)
```

Exemple : si la caméra tourne à 30 FPS, une fenêtre de 30 secondes contient 900 frames. Si l'EAR est en dessous du seuil sur 180 frames, alors PERCLOS = 180 / 900 = 0.20 (20%).

### Valeurs de référence

| PERCLOS | État | Interprétation |
|---------|------|---------------|
| < 0.15 | Normal | Conducteur alerte, clignements normaux uniquement |
| 0.15 - 0.30 | Attention | Début de fatigue, clignements plus longs |
| 0.30 - 0.45 | Danger | Fatigue avancée, micro-sommeils possibles |
| > 0.45 | Critique | Perte de vigilance imminente |

### Pourquoi 30 secondes ?

Une fenêtre trop courte (5s) génère trop de faux positifs car quelques clignements naturels suffisent à faire monter le PERCLOS. Une fenêtre trop longue (60s) réagit trop lentement. 30 secondes est le compromis validé par la recherche scientifique.

### Poids dans le score final : 40%

Le PERCLOS est la métrique la plus fiable et la plus étudiée scientifiquement. Elle filtre naturellement les clignements normaux (trop courts pour impacter significativement le pourcentage sur 30s) et ne réagit qu'aux fermetures prolongées caractéristiques de la somnolence.

---

## 3. Blink Rate (Fréquence de clignement)

### Description

Le Blink Rate mesure le nombre de clignements par minute. Un clignement est défini comme un événement où l'EAR passe en dessous du seuil puis repasse au-dessus dans un intervalle de temps court (< 500ms).

### Détection d'un clignement

```
1. EAR descend en dessous de 0.20       → début du clignement
2. EAR reste bas pendant 100-500ms       → clignement confirmé
3. EAR remonte au-dessus de 0.20         → fin du clignement
4. Incrémenter le compteur de clignements
```

Si l'EAR reste bas pendant plus de 500ms, ce n'est plus un clignement mais une fermeture prolongée (comptée par le PERCLOS, pas par le Blink Rate).

### Valeurs de référence

| Blink Rate (par minute) | État | Interprétation |
|------------------------|------|---------------|
| 15 - 20 | Normal | Fréquence physiologique standard |
| 20 - 25 | Attention légère | Légère augmentation, stress ou écran |
| > 25 | Fatigue (phase de lutte) | Le conducteur lutte contre le sommeil, clignements rapides et fréquents |
| < 10 | Danger (phase de perte) | Le conducteur perd le combat, les micro-sommeils remplacent les clignements |

### Pattern typique de la fatigue

La fatigue suit un pattern en deux phases :
1. Phase de lutte : le Blink Rate augmente (> 25/min), les clignements deviennent rapides et irréguliers
2. Phase de perte : le Blink Rate chute (< 10/min), les clignements sont remplacés par des fermetures prolongées

La détection des deux phases permet d'anticiper la transition de la phase 1 (récupérable) à la phase 2 (dangereuse).

### Poids dans le score final

Le Blink Rate contribue au bloc "Blink Pattern" qui pèse **20%** du score total, combiné avec la Blink Duration.

---

## 4. Blink Duration (Durée des clignements)

### Description

La Blink Duration mesure la durée moyenne des clignements en millisecondes. C'est un indicateur complémentaire au Blink Rate : un conducteur fatigué a des clignements plus lents car ses paupières "traînent".

### Formule

```
Blink Duration = timestamp(EAR remonte au-dessus du seuil) - timestamp(EAR descend sous le seuil)
```

La valeur utilisée est la moyenne mobile des 10 derniers clignements pour lisser les variations naturelles.

### Valeurs de référence

| Durée moyenne | État | Interprétation |
|--------------|------|---------------|
| 100 - 200 ms | Rapide | Clignement réflexe, très alerte |
| 200 - 300 ms | Normal | Clignement physiologique standard |
| 300 - 500 ms | Lent | Paupières lourdes, début de somnolence |
| > 500 ms | Micro-sommeil | N'est plus un clignement mais une fermeture involontaire |

### Poids dans le score final

La Blink Duration contribue au bloc "Blink Pattern" qui pèse **20%** du score total, combiné avec le Blink Rate.

---

## 5. Head Pose (Orientation de la tête)

### Description

Le Head Pose mesure l'orientation 3D de la tête du conducteur à partir des landmarks faciaux. En utilisant la fonction `solvePnP` d'OpenCV, on projette les points 2D de l'image vers un modèle 3D du visage pour calculer 3 angles de rotation.

### Les 3 angles

| Angle | Axe de rotation | Ce qu'il mesure |
|-------|----------------|----------------|
| Pitch | Axe horizontal (gauche-droite) | La tête qui tombe vers l'avant ou se relève vers l'arrière |
| Yaw | Axe vertical (haut-bas) | La tête qui tourne vers la gauche ou la droite |
| Roll | Axe de profondeur (avant-arrière) | La tête qui penche sur le côté |

### Landmarks utilisés pour solvePnP

| Point | Indice MediaPipe | Rôle |
|-------|-----------------|------|
| Bout du nez | 1 | Point central de référence |
| Menton | 152 | Ancrage bas du visage |
| Coin oeil gauche | 263 | Référence latérale gauche |
| Coin oeil droit | 33 | Référence latérale droite |
| Coin bouche gauche | 291 | Ancrage bas latéral gauche |
| Coin bouche droit | 61 | Ancrage bas latéral droit |

### Valeurs de référence

| Angle | Normal | Attention | Danger |
|-------|--------|-----------|--------|
| Pitch (avant/arrière) | < 15° | 15° - 25° | > 25° pendant > 2s |
| Yaw (gauche/droite) | < 20° | 20° - 35° | > 35° pendant > 2s |
| Roll (inclinaison) | < 15° | 15° - 25° | > 25° pendant > 2s |

### Signe principal de fatigue

Le **pitch** est l'angle le plus révélateur. La tête qui tombe vers l'avant (pitch positif croissant) est le signe physique direct de la perte de conscience. C'est le "head nodding" caractéristique du conducteur qui s'endort.

### Condition temporelle

Un mouvement brusque de la tête (regarder un angle mort, se tourner vers un passager) ne doit pas déclencher d'alerte. Le système ne réagit que si l'angle dépasse le seuil **pendant plus de 2 secondes consécutives**.

### Poids dans le score final : 25%

Le Head Pose est le deuxième indicateur le plus fiable après le PERCLOS. Il détecte un stade avancé de la fatigue où le corps commence à perdre le contrôle musculaire. Son avantage est qu'il fonctionne même si les yeux ne sont pas parfaitement visibles (lunettes, reflets).

---

## 6. MAR (Mouth Aspect Ratio)

### Description

Le MAR mesure le degré d'ouverture de la bouche, de la même manière que l'EAR mesure l'ouverture de l'oeil. Il sert à détecter les bâillements, qui sont un signal précoce de fatigue.

### Formule

```
MAR = (||p2 - p8|| + ||p3 - p7|| + ||p4 - p6||) / (2 * ||p1 - p5||)
```

Où p1-p8 sont les landmarks du contour extérieur de la bouche (4 points verticaux, 2 points horizontaux).

### Landmarks MediaPipe utilisés

| Position | Indice |
|----------|--------|
| Coin gauche | 61 |
| Lèvre supérieure (haut) | 13 |
| Lèvre supérieure (centre) | 0 |
| Coin droit | 291 |
| Lèvre inférieure (centre) | 17 |
| Lèvre inférieure (bas) | 14 |

### Valeurs de référence

| MAR | État |
|-----|------|
| < 0.3 | Bouche fermée |
| 0.3 - 0.5 | Bouche légèrement ouverte (parole, respiration) |
| 0.5 - 0.6 | Ouverture large (possible bâillement) |
| > 0.6 | Bâillement confirmé (si durée > 2s) |

### Détection d'un bâillement

Un bâillement se distingue d'une ouverture normale de la bouche (parler, manger) par sa durée :

```
1. MAR dépasse 0.6                      → début possible de bâillement
2. MAR reste au-dessus de 0.6 pendant > 2s → bâillement confirmé
3. MAR redescend en dessous de 0.6       → fin du bâillement
4. Incrémenter le compteur de bâillements
```

### Fréquence de bâillement

| Bâillements sur 5 minutes | Interprétation |
|--------------------------|----------------|
| 0 - 1 | Normal |
| 2 - 3 | Fatigue légère |
| > 3 | Fatigue significative |

### Poids dans le score final : 15%

Le bâillement est un signal précoce de fatigue mais moins fiable que le PERCLOS ou le Head Pose. Il peut être déclenché par d'autres facteurs (ennui, mimétisme, air ambiant). Son poids dans le score reflète cette fiabilité moindre.

---

## Calcul du Score de Fatigue (0-100)

### Formule globale

```
SCORE = (Score_PERCLOS × 0.40) + (Score_HeadPose × 0.25) + (Score_BlinkPattern × 0.20) + (Score_Yawn × 0.15)
```

### Normalisation de chaque métrique (0-100)

Chaque métrique brute est normalisée sur une échelle de 0 à 100 avant d'être pondérée.

**Score PERCLOS :**

```
Si PERCLOS < 0.15    →  score = 0
Si PERCLOS > 0.45    →  score = 100
Sinon                →  score = (PERCLOS - 0.15) / (0.45 - 0.15) × 100
```

**Score Head Pose (basé sur le pitch principalement) :**

```
Si pitch < 15°       →  score = 0
Si pitch > 40°       →  score = 100
Sinon                →  score = (pitch - 15) / (40 - 15) × 100
```

Note : le yaw et le roll contribuent au score si ils dépassent leurs seuils respectifs, mais avec un poids moindre que le pitch.

**Score Blink Pattern (combinaison Blink Rate + Blink Duration) :**

```
score_rate :
  Si 15 ≤ rate ≤ 20      →  0
  Si rate > 25 ou < 10   →  100
  Sinon                  →  interpolation linéaire

score_duration :
  Si duration < 300ms    →  0
  Si duration > 500ms    →  100
  Sinon                  →  (duration - 300) / (500 - 300) × 100

Score_BlinkPattern = (score_rate + score_duration) / 2
```

**Score Yawn :**

```
Si 0 bâillements en 5 min     →  score = 0
Si 1 bâillement en 5 min      →  score = 25
Si 2 bâillements en 5 min     →  score = 50
Si 3 bâillements en 5 min     →  score = 75
Si 4+ bâillements en 5 min    →  score = 100
```

### Exemple de calcul

Un conducteur affiche les métriques suivantes :
- PERCLOS = 0.25 (yeux fermés 25% du temps)
- Pitch = 20° (tête légèrement penchée)
- Blink Rate = 22/min, Blink Duration = 350ms
- 2 bâillements en 5 minutes

```
Score_PERCLOS       = (0.25 - 0.15) / (0.45 - 0.15) × 100 = 33
Score_HeadPose      = (20 - 15) / (40 - 15) × 100 = 20
Score_BlinkRate     = interpolation ≈ 30
Score_BlinkDuration = (350 - 300) / (500 - 300) × 100 = 25
Score_BlinkPattern  = (30 + 25) / 2 = 27.5
Score_Yawn          = 50

SCORE FINAL = (33 × 0.40) + (20 × 0.25) + (27.5 × 0.20) + (50 × 0.15)
            = 13.2 + 5.0 + 5.5 + 7.5
            = 31.2

→ Niveau 1 (Alerte légère)
```

---

## Mapping Score vers Niveaux d'Alerte

### Tableau des niveaux

| Niveau | Score | État conducteur | Actions Sentinel | Délai avant escalade |
|--------|-------|-----------------|-----------------|---------------------|
| 0 | 0 - 29 | Alerte | Monitoring passif, aucune alerte | Aucun |
| 1 | 30 - 54 | Somnolent | Bip buzzer court + LED d'avertissement | 15 secondes |
| 2 | 55 - 74 | Dangereux | Alarme sonore forte + vibration siège | 10 secondes |
| 3 | 75 - 89 | Critique | Message vocal "Reprenez le contrôle" + compte à rebours 10s | 10 secondes |
| 4 | 90 - 100 | Non-réactif | Séquence d'arrêt d'urgence autonome | Immédiat |

### Détail des actions par niveau

**Niveau 0 - Monitoring passif**
Le système surveille en continu sans intervenir. Toutes les métriques sont calculées et enregistrées. Le conducteur n'est pas conscient que le système fonctionne.

**Niveau 1 - Alerte légère**
Le buzzer émet un bip court toutes les 3 secondes. Une LED orange s'allume sur le dispositif. L'objectif est d'attirer l'attention du conducteur sans le surprendre. Si le score redescend en dessous de 30 dans les 15 secondes suivantes, retour au niveau 0.

**Niveau 2 - Alerte forte**
Le buzzer émet un son continu et le moteur vibreur s'active (simulation de la vibration du siège). Le conducteur ressent l'alerte physiquement. Si le score redescend en dessous de 55 dans les 10 secondes, retour au niveau 1.

**Niveau 3 - Alerte critique**
Le haut-parleur diffuse un message vocal : "Attention, reprenez le contrôle du véhicule." Un compte à rebours de 10 secondes démarre. Si le conducteur ne réagit pas (score reste au-dessus de 75), le système passe au niveau 4.

**Niveau 4 - Arrêt d'urgence**
Le système considère que le conducteur est inconscient et déclenche la séquence d'arrêt autonome :
1. Activation des 4 feux de détresse (LEDs orange clignotantes)
2. Décélération progressive du véhicule
3. Changement de voie vers la droite
4. Arrêt complet sur le bord de la route
5. Envoi de la position GPS au contact d'urgence

### Conditions de désescalade

Le système permet de redescendre d'un niveau si le conducteur reprend le contrôle :

```
Niveau 4 → Pas de retour automatique. Arrêt complet obligatoire.
Niveau 3 → Niveau 2 : score < 75 pendant 5 secondes consécutives
Niveau 2 → Niveau 1 : score < 55 pendant 5 secondes consécutives
Niveau 1 → Niveau 0 : score < 30 pendant 10 secondes consécutives
```

La désescalade est volontairement plus lente que l'escalade pour éviter les oscillations entre les niveaux (le conducteur se réveille brièvement puis se rendort).

### Règles supplémentaires

**Escalade directe :** si le PERCLOS dépasse 0.50 ou si le pitch dépasse 40° pendant plus de 3 secondes, le système saute directement au niveau 3 quel que soit le score global. Ces conditions indiquent un danger immédiat.

**Cooldown après alerte :** après un retour au niveau 0, le système maintient une sensibilité accrue pendant 5 minutes (seuils abaissés de 10%). Un conducteur qui s'est assoupi une fois risque fortement de se rendormir.

---

## Résumé des métriques MVP

| Métrique | Source | Rôle | Poids |
|----------|--------|------|-------|
| EAR | 6 landmarks par oeil | Matière première, ne rentre pas directement dans le score | N/A |
| PERCLOS | Dérivé de l'EAR sur 30s | Indicateur principal de somnolence | 40% |
| Blink Rate | Compteur de clignements/min | Détecte la phase de lutte contre le sommeil | 10% |
| Blink Duration | Durée moyenne des clignements | Détecte le ralentissement des paupières | 10% |
| Head Pose | solvePnP sur landmarks faciaux | Détecte la perte de contrôle musculaire | 25% |
| MAR (Yawn) | Landmarks de la bouche | Signal précoce de fatigue | 15% |





##-------------------------------------------------------------------
##-------------------------------------------------------------------
##-------------------------------------------------------------------

██╗   ██╗███████╗██████╗ ███████╗██╗ ██████╗ ███╗   ██╗    ██████╗ 
██║   ██║██╔════╝██╔══██╗██╔════╝██║██╔═══██╗████╗  ██║    ╚════██╗
██║   ██║█████╗  ██████╔╝███████╗██║██║   ██║██╔██╗ ██║     █████╔╝
╚██╗ ██╔╝██╔══╝  ██╔══██╗╚════██║██║██║   ██║██║╚██╗██║    ██╔═══╝ 
 ╚████╔╝ ███████╗██║  ██║███████║██║╚██████╔╝██║ ╚████║    ███████╗
  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝    ╚══════╝


##-------------------------------------------------------------------
##-------------------------------------------------------------------
##-------------------------------------------------------------------

---

## 7. LSTM — Scorer Temporel par Apprentissage Automatique

### Problème du scorer actuel

Le scorer actuel (`Scorer.py`) traite chaque `MetricsSnapshot` de manière **indépendante** : le score à l'instant *t* ne dépend que des métriques à l'instant *t+1*. Or, la fatigue est un phénomène **temporel** : une chute du blink rate qui survient 15 secondes après un pic de PERCLOS est bien plus significative que ces deux signaux pris séparément.

```
Exemple :
  t=0s  : PERCLOS=0.10, blink_rate=18  → score=5   (normal)
  t=15s : PERCLOS=0.30, blink_rate=8   → score=42  (somnolent)

Scorer actuel : ne voit que t=15s, score=42
LSTM          : voit la trajectoire t=0→15s, prédit niveau 2 car la chute est rapide
```

Le LSTM remplace `compute_fatigue_score()` dans `Scorer.py` par un modèle entraîné sur des séquences temporelles.

---

### Architecture du modèle

```
Entrée : séquence de T snapshots
         shape = (batch, T, 8 features)

                    ┌──────────────┐
Snapshot t-T   ───▶ │              │
Snapshot t-T+1 ───▶ │  LSTM x 2    │ hidden_size=64
      ...      ───▶ │  couches     │
Snapshot t     ───▶ │              │
                    └──────┬───────┘
                           │ dernier hidden state (64)
                           ▼
                    ┌──────────────┐
                    │  Dropout 0.3 │
                    └──────┬───────┘
                           │
                    ┌──────────────┐
                    │  Linear(64→1)│
                    └──────┬───────┘
                           │
                    ┌──────────────┐
                    │  Sigmoid ×100│
                    └──────┬───────┘
                           ▼
                    Score fatigue (0–100)
```

### Paramètres

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| Fenêtre temporelle T | 90 frames (~30s à 30fps) | Cohérent avec la fenêtre PERCLOS |
| Features d'entrée | 8 | EAR, PERCLOS, blink_rate, blink_duration, pitch, yaw, roll, mar |
| Hidden size | 64 | Suffisant pour capturer les patterns sans surapprentissage |
| Nombre de couches LSTM | 2 | Permet d'apprendre des dépendances à deux échelles de temps |
| Dropout | 0.3 | Régularisation entre les couches |
| Sortie | 1 scalaire × 100 | Score 0–100, compatible avec AlertStateMachine existante |

---

### Données d'entraînement

#### Datasets publics recommandés

| Dataset | Contenu | Labels |
|---------|---------|--------|
| **NTHU Drowsy Driver** | Vidéos de conduite, multiples caméras | Drowsy / Non-drowsy par frame |
| **UTA Real-Life Drowsiness** | Conduite réelle sur autoroute | Score de somnolence 0–4 |
| **YawDD** | Conducteurs en situation de conduite simulée | Bâillements annotés |

#### Format des données d'entraînement

Chaque échantillon est une séquence de T `MetricsSnapshot` + un label de fatigue :

```python
X : np.array, shape (N, T, 8)
    N = nombre de séquences
    T = longueur de la fenêtre (90 frames)
    8 = [ear, perclos, blink_rate, blink_duration_ms,
         pitch, yaw, roll, mar]

y : np.array, shape (N,)
    Valeurs continues 0.0–1.0 (score normalisé)
    ou classes {0, 1, 2, 3, 4} pour classification
```

#### Génération de données depuis Sentinel

En l'absence de dataset externe, Sentinel peut **générer ses propres données** en mode enregistrement :

```
1. Lancer Orchestration.py en mode --record
2. Enregistrer les MetricsSnapshot à chaque frame dans un CSV
3. L'opérateur annote manuellement les fenêtres (fatigue / non-fatigue)
4. Construire les séquences de longueur T avec stride=15 frames
```

---

### Prétraitement des features

Chaque feature est normalisée **indépendamment** sur ses valeurs physiologiques connues avant d'être passée au LSTM :

```python
FEATURE_RANGES = {
    "ear":              (0.05, 0.40),
    "perclos":          (0.00, 1.00),
    "blink_rate":       (0.0,  40.0),
    "blink_duration":   (50.0, 800.0),
    "pitch":            (-45.0, 45.0),
    "yaw":              (-60.0, 60.0),
    "roll":             (-30.0, 30.0),
    "mar":              (0.0,  1.0),
}

def normalize_snapshot(snapshot):
    # Chaque valeur ramenée à [0, 1]
    features = []
    for key, (lo, hi) in FEATURE_RANGES.items():
        value = getattr(snapshot, key)
        features.append(max(0.0, min(1.0, (value - lo) / (hi - lo))))
    return features
```

---

### Intégration dans le pipeline Sentinel

Le LSTM remplace `compute_fatigue_score()` dans `Orchestration.py` sans modifier aucun autre module :

```
Avant :
  snapshot = tracker.update(landmarks, w, h)
  score    = compute_fatigue_score(snapshot)       ← scorer à formule fixe

Après :
  snapshot = tracker.update(landmarks, w, h)
  sequence_buffer.append(snapshot)                 ← file glissante de T frames
  score    = lstm_scorer.predict(sequence_buffer)  ← scorer neuronal
```

```python
class LSTMScorer:
    def __init__(self, model_path, window=90):
        self.window   = window
        self.buffer   = deque(maxlen=window)
        self.model    = load_model(model_path)   # TorchScript ou ONNX
        self._warm    = False

    def predict(self, snapshot):
        self.buffer.append(normalize_snapshot(snapshot))
        if len(self.buffer) < self.window:
            # Fenêtre pas encore pleine : utiliser le scorer classique
            return compute_fatigue_score(snapshot)
        x = np.array(self.buffer, dtype=np.float32)   # (T, 8)
        x = x[np.newaxis, ...]                         # (1, T, 8)
        return float(self.model(x)) * 100.0
```

Le scorer classique fait office de **fallback** pendant les 30 premières secondes (fenêtre incomplète), garantissant un comportement correct dès le démarrage.

---

### Entraînement

```python
import torch
import torch.nn as nn

class SentinelLSTM(nn.Module):
    def __init__(self, input_size=8, hidden=64, layers=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden, layers,
                            batch_first=True, dropout=dropout)
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        # x : (batch, T, 8)
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)  # dernier hidden state


# Entraînement
model     = SentinelLSTM()
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
loss_fn   = nn.MSELoss()   # régression de score

for epoch in range(50):
    for X_batch, y_batch in dataloader:
        pred = model(X_batch)
        loss = loss_fn(pred, y_batch)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

# Export pour production
torch.jit.script(model).save("sentinel_lstm.pt")
```

### Métriques d'évaluation

| Métrique | Cible | Description |
|----------|-------|-------------|
| MAE | < 8 points | Erreur moyenne sur le score 0–100 |
| Précision niveau | > 85% | % de niveaux d'alerte correctement prédits |
| Taux faux positifs | < 5% | Alertes déclenchées sur conducteur alerte |
| Latence inférence | < 10ms | Temps de prédiction sur CPU embarqué |

---

### Comparaison scorer actuel vs LSTM

| Critère | Scorer à formule | LSTM |
|---------|-----------------|------|
| Données requises | Aucune | Dataset annoté |
| Dépendances temporelles | Non | Oui |
| Adaptabilité au conducteur | Non | Possible (fine-tuning) |
| Interprétabilité | Totale | Limitée (boîte noire) |
| Latence | < 1ms | 5–10ms |
| Robustesse sans visage | Bonne (score=0) | Nécessite padding |
| Recommandé pour MVP | Oui | Non (v2+) |

Le scorer à formule reste la référence pour le MVP. Le LSTM est l'amélioration naturelle une fois qu'un jeu de données de sessions de conduite réelles est disponible.




exacution.  steps. : 
Step 1 — Record a session (generates labeled CSV)
    python3 Orchestration.py --record session.csv

  Step 2 — Train the model on that CSV
    python3 lstm_train.py --data session.csv --out sentinel_lstm.pt

  Step 3 — Run with the trained LSTM
    python3 Orchestration.py --lstm sentinel_lstm.pt

  Step 4 — Once model is good, record with LSTM labels for refinement
    python3 Orchestration.py --lstm sentinel_lstm.pt --record session2.csv

  For Step 1, the session should ideally cover both alert and fatigued states to
   give the LSTM varied training data — simulate drowsiness (slow blinks, head
  drops, yawns) as well as normal attentive driving. A 10–15 minute session at
  30fps generates ~18,000–27,000 rows, which builds ~1,200–1,800 sequences of 90
   frames with stride=15.

  For Step 2, the minimum viable command is:
  python3 lstm_train.py --data session.csv

  All other parameters have sensible defaults (50 epochs, hidden=64, window=90).
   If training loss plateaus early you can increase --epochs 100.

  Ready to record a session? Run Step 1, and once you have session.csv ready,
  come back for Step 2.

##retrain with :

python3 lstm_train.py --data session2.csv --epochs 100



  