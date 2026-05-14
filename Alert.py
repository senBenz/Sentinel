import time , os , threading ,math 

try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False
    



# ============================================================
# CONSTANTS
# ============================================================
 
LEVEL_THRESHOLDS = [0, 30, 55, 75, 90]
#                   0   1   2   3   4


ESCALATION_DELAYS = {
    0: 0.0,    # instant (always in level 0 if score < 30)
    1: 2.0,    # wait 2s before escalating from 0 to 1
    2: 3.0,    # wait 3s before escalating from 1 to 2
    3: 3.0,    # wait 3s before escalating from 2 to 3
    4: 5.0,    # wait 5s (countdown) before escalating from 3 to 4
}


DEESCALATION_DELAYS = {
    3: 5.0,    # level 4 -> 3 : NOT POSSIBLE (level 4 = full stop)
    2: 5.0,    # level 3 -> 2
    1: 5.0,    # level 2 -> 1
    0: 10.0,   # level 1 -> 0
} 



COOLDOWN_REDUCTION = 0.10     
COOLDOWN_DURATION = 300.0   

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")



# ============================================================
# SOUND GENERATOR (no .wav files needed)
# ============================================================


def _generate_beep(frequency=1000, duration_ms=200, volume=0.5):
    """
    Generate a beep tone using pygame.
    No external .wav file needed.
    """
    if not HAS_SOUND:
        return None
    sample_rate = 44100
    n_samples = int(sample_rate * duration_ms / 1000)
    buf = bytearray(n_samples * 2)  #
    for i in range(n_samples):
        value = int(volume * 32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        buf[i * 2] = value & 0xFF
        buf[i * 2 + 1] = (value >> 8) & 0xFF
    sound = pygame.mixer.Sound(buffer=bytes(buf))
    return sound
 
 
class SoundManager:
    """
    Manages all alert sounds using generated tones.
    No .wav files required. Everything is synthesized.
    """
 
    def __init__(self):
        self._playing = False
        self._loop_thread = None
        self.sounds = {}
 
        if HAS_SOUND:
            # Level 1: short gentle beep (800Hz, 150ms)
            self.sounds["beep"] = _generate_beep(800, 150, 0.3)
            # Level 2: alarm tone (1200Hz, 300ms)
            self.sounds["alarm"] = _generate_beep(1200, 300, 0.6)
            # Level 3: urgent tone (1500Hz, 500ms)
            self.sounds["urgent"] = _generate_beep(1500, 500, 0.8)
            # Level 4: emergency siren (2000Hz, 400ms)
            self.sounds["siren"] = _generate_beep(2000, 400, 1.0)
 
    def play_once(self, sound_name):
        """Play a sound once."""
        self.stop()
        if HAS_SOUND and sound_name in self.sounds:
            self.sounds[sound_name].play()
 
    def play_loop(self, sound_name, interval=1.0):
        """Play a sound repeatedly in a background thread."""
        self.stop()
        self._playing = True
        self._loop_thread = threading.Thread(
            target=self._loop, args=(sound_name, interval), daemon=True
        )
        self._loop_thread.start()
 
    def play_voice(self):
        """Play the voice alert file if it exists, otherwise use urgent tone."""
        self.stop()
        voice_path = os.path.join(ASSETS_DIR, "reprenez_le_controle.wav")
        if HAS_SOUND and os.path.exists(voice_path):
            try:
                pygame.mixer.music.load(voice_path)
                pygame.mixer.music.play()
                return
            except Exception:
                pass
        # Fallback: use urgent tone
        self.play_loop("urgent", 0.8)
 
    def stop(self):
        """Stop all sounds."""
        self._playing = False
        if HAS_SOUND:
            pygame.mixer.stop()
            pygame.mixer.music.stop()
 
    def _loop(self, sound_name, interval):
        """Background loop to repeat a sound."""
        while self._playing:
            if HAS_SOUND and sound_name in self.sounds:
                self.sounds[sound_name].play()
            time.sleep(interval)


class AlertStateMachine:
    """
    5-level deterministic state machine for fatigue alerts.
 
    Feed it a score every frame via update().
    It manages escalation/de-escalation timing and triggers alerts.
    """
 
    def __init__(self):
        self.level = 0
        self._escalation_start = None
        self._deescalation_start = None
        self._cooldown_until = 0.0
        self._sound = SoundManager()
 
    def update(self, score, emergency=False):
        """
        Update the state machine with a new fatigue score.
 
        Args:
            score: float 0-100 from scorer.compute_fatigue_score()
            emergency: bool from scorer.check_emergency()
 
        Returns:
            int: current alert level (0-4)
        """
        now = time.time()
 
        # Emergency override: jump to level 3 minimum
        if emergency and self.level < 3:
            self._set_level(3, now)
            return self.level
 
        # Determine target level from score
        target = self._score_to_target(score, now)
 
        if target > self.level:
            self._try_escalate(target, now)
        elif target < self.level:
            self._try_deescalate(target, now)
        else:
            # Same level, reset timers
            self._escalation_start = None
            self._deescalation_start = None
 
        return self.level
 
    def _score_to_target(self, score, now):
        """Convert score to target level, considering cooldown."""
        thresholds = list(LEVEL_THRESHOLDS)
 
        # Apply cooldown: lower thresholds by 10% if in cooldown period
        if now < self._cooldown_until:
            thresholds = [int(t * (1 - COOLDOWN_REDUCTION)) for t in thresholds]
 
        target = 0
        for i in range(len(thresholds) - 1, -1, -1):
            if score >= thresholds[i]:
                target = i
                break
        return target
 
    def _try_escalate(self, target, now):
        """Attempt to escalate to a higher level with delay."""
        if self._escalation_start is None:
            self._escalation_start = now
 
        elapsed = now - self._escalation_start
        next_level = self.level + 1
        delay = ESCALATION_DELAYS.get(next_level, 3.0)
 
        if elapsed >= delay:
            self._set_level(next_level, now)
            self._escalation_start = now
 
        self._deescalation_start = None
 
    def _try_deescalate(self, target, now):
        """Attempt to de-escalate to a lower level with delay."""
        # Level 4 cannot de-escalate (full stop required)
        if self.level == 4:
            return
 
        if self._deescalation_start is None:
            self._deescalation_start = now
 
        elapsed = now - self._deescalation_start
        prev_level = self.level - 1
        delay = DEESCALATION_DELAYS.get(prev_level, 5.0)
 
        if elapsed >= delay:
            self._set_level(prev_level, now)
            self._deescalation_start = now
 
            # Start cooldown when returning to level 0
            if prev_level == 0:
                self._cooldown_until = now + COOLDOWN_DURATION
 
        self._escalation_start = None
 
    def _set_level(self, new_level, now):
        """Change the alert level and trigger corresponding actions."""
        old_level = self.level
        self.level = new_level
 
        # Stop previous alerts
        self._sound.stop()
 
        # Trigger new alerts
        if new_level == 0:
            self._action_level_0()
        elif new_level == 1:
            self._action_level_1()
        elif new_level == 2:
            self._action_level_2()
        elif new_level == 3:
            self._action_level_3()
        elif new_level == 4:
            self._action_level_4()
 
        print(f"[ALERT] Niveau {old_level} -> {new_level}")
 
    # ============================================================
    # ALERT ACTIONS (PC only)
    # ============================================================
 
    def _action_level_0(self):
        """Level 0: Monitoring passif. Silence."""
        print("[ALERT] Monitoring passif")
 
    def _action_level_1(self):
        """Level 1: Short beep every 3 seconds."""
        print("[ALERT] *BIP* (alerte legere)")
        self._sound.play_loop("beep", 3.0)
 
    def _action_level_2(self):
        """Level 2: Continuous alarm tone."""
        print("[ALERT] *ALARME CONTINUE*")
        self._sound.play_loop("alarm", 1.0)
 
    def _action_level_3(self):
        """Level 3: Voice message or urgent tone + countdown."""
        print("[ALERT] 'REPRENEZ LE CONTROLE' - Countdown 10s")
        self._sound.play_voice()
 
    def _action_level_4(self):
        """Level 4: Emergency siren."""
        print("[ALERT] *** ARRET D'URGENCE ***")
        self._sound.play_loop("siren", 0.5)
 
    def cleanup(self):
        """Stop all sounds and release resources."""
        self._sound.stop()            