"""
game.py — Autonomous Mars Rover: Propositional Logic Agent (Pygame GUI)
=========================================================================

The flagship, "full-fledged GUI game" front-end for the Track 2 hackathon
submission. Everything drawn here is procedural (pygame primitives only —
no external image/asset files are downloaded or bundled), so the whole
visual is self-contained in this one file.

This module is intentionally a thin *presentation* layer: all of the actual
propositional-logic reasoning lives in logic.py / inference.py /
knowledge_base.py / agent.py, completely unchanged in behavior by anything
in here. game.py only calls KBAgent.step() each turn and animates/logs what
comes back.

IMPORTANT for the hackathon's split-screen video requirement: this script
never touches sys.stdout. Run `python game.py` from a normal terminal and
that terminal keeps scrolling the same rich, professional per-step KB log
(clause deltas, derivations, replanning table, chosen action) in real time
— exactly the second half of the required "grid window + live console log"
recording, with zero extra setup.

Controls
--------
  SPACE        Single step (when not auto-running)
  A            Toggle AUTO RUN / PAUSE
  R            Restart with a freshly generated environment
  M            Cycle inference mode: DPLL -> Resolution -> Both -> DPLL
  + / -        Speed up / slow down auto-run
  K            Dump the ENTIRE current KB (all CNF clauses) to the terminal
  Mouse clicks on the on-screen buttons do the same as above.
"""

import io
import math
import os
import random
import sys
import time
from collections import deque

# Match main.py's console setup: force UTF-8 so the bullet/arrow characters
# in the KB log render correctly on Windows terminals (which otherwise
# default to a legacy codepage and mangle them). Skipped when stdout has
# already been redirected to something without a raw buffer (e.g. under a
# test harness) so this stays safe to import anywhere.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import pygame

from environment import Environment
from agent import KBAgent

try:
    import pygame.gfxdraw as gfx
    HAVE_GFX = True
except ImportError:
    HAVE_GFX = False


# ============================================================================
# Configuration
# ============================================================================

GRID_W, GRID_H = 8, 8
NUM_HAZARDS, NUM_RADIATION, NUM_OBSTACLES = 6, 5, 3

WINDOW_W, WINDOW_H = 1320, 800
GRID_AREA = 760
MARGIN = 20
HUD_X = GRID_AREA + MARGIN * 2
HUD_W = WINDOW_W - HUD_X - MARGIN
FPS = 60

MOVE_DURATION = 0.42          # seconds for the rover to tween one cell
AUTO_STEP_PAUSE = 0.35        # pause after a tween completes before next auto step
SCAN_DURATION = 0.65          # how long a neighbor-evaluation ring animation lasts
SPEED_LEVELS = [0.85, 0.55, 0.35, 0.18, 0.05]  # AUTO_STEP_PAUSE choices, slow -> fast
DEFAULT_SPEED_IDX = 2

MODES = ["dpll", "resolution", "both"]
MODE_LABEL = {"dpll": "DPLL (Model Checking)", "resolution": "Resolution (Theorem Proving)",
              "both": "BOTH (cross-validated)"}

# ---------------------------------------------------------------------- colors
BG = (9, 11, 18)
PANEL_BG = (16, 19, 29)
PANEL_BORDER = (46, 54, 74)
GRID_BG = (13, 15, 23)
GRID_LINE = (32, 37, 52)

C_UNKNOWN = (26, 24, 32)
C_UNKNOWN_STATIC = (38, 35, 46)
C_KNOWN_SAFE_UNVISITED = (34, 66, 60)
C_VISITED_SAFE = (36, 92, 66)
C_START = (34, 74, 130)
C_GOAL = (150, 118, 30)
C_HAZARD = (120, 34, 34)
C_RADIATION = (140, 128, 24)
C_OBSTACLE = (74, 58, 46)

TEXT = (226, 232, 245)
TEXT_DIM = (128, 138, 158)
TEXT_FAINT = (80, 88, 104)
ACCENT_CYAN = (86, 214, 255)
ACCENT_GREEN = (96, 224, 148)
ACCENT_RED = (240, 96, 96)
ACCENT_GOLD = (230, 182, 68)
ACCENT_GRAY = (140, 150, 168)

ROVER_COLOR = (110, 226, 255)
ROVER_GLOW = (60, 160, 210)

FONT_NAME = "consolas"


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ============================================================================
# Small animation helpers
# ============================================================================

class ScanPulse:
    """A brief, color-coded expanding ring drawn over a cell — the visual
    proof that the KB is being *asked* about that cell right now."""

    def __init__(self, gx, gy, color, label=""):
        self.gx, self.gy = gx, gy
        self.color = color
        self.label = label
        self.t0 = time.time()

    def age(self):
        return time.time() - self.t0

    def done(self):
        return self.age() > SCAN_DURATION


class Particle:
    """A tiny fading dot for the rover's thruster trail."""

    __slots__ = ("x", "y", "vx", "vy", "t0", "life", "color")

    def __init__(self, x, y, vx, vy, color, life=0.5):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.t0 = time.time()
        self.life = life
        self.color = color

    def age(self):
        return time.time() - self.t0

    def done(self):
        return self.age() > self.life


# ============================================================================
# Main game
# ============================================================================

class RoverGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Autonomous Mars Rover — Propositional Logic Agent")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()

        self.font_tiny = pygame.font.SysFont(FONT_NAME, 13)
        self.font_small = pygame.font.SysFont(FONT_NAME, 15)
        self.font_small_b = pygame.font.SysFont(FONT_NAME, 15, bold=True)
        self.font_med = pygame.font.SysFont(FONT_NAME, 18, bold=True)
        self.font_title = pygame.font.SysFont(FONT_NAME, 24, bold=True)
        self.font_cell = pygame.font.SysFont(FONT_NAME, 12, bold=True)
        self.font_huge = pygame.font.SysFont(FONT_NAME, 42, bold=True)

        self.mode_idx = 0  # index into MODES
        self.speed_idx = DEFAULT_SPEED_IDX

        self.buttons = {}  # name -> pygame.Rect, built in layout()
        self._layout_buttons()

        self.new_simulation()

    # ------------------------------------------------------------ lifecycle
    def _generate_solvable_environment(self, attempts=80):
        """Regenerate a random environment until start->goal is reachable
        through safe cells (ground truth, not the agent's belief). A dense
        random placement can otherwise trap the start cell behind hazards on
        its very first move — logically correct (the agent rightly refuses
        an unproven move) but a bad look for a live demo/recording. This
        only resamples the *placement*; environment.py's own generation
        logic and its random-seed sequence are untouched."""
        env = None
        for _ in range(attempts):
            env = Environment(width=GRID_W, height=GRID_H)
            env.generate_random_env(num_hazards=NUM_HAZARDS, num_radiations=NUM_RADIATION,
                                     num_obstacles=NUM_OBSTACLES)
            danger = env.hazards | env.radiations | env.obstacles
            if env.start_pos in danger or env.goal_pos in danger:
                continue
            frontier = deque([env.start_pos])
            seen = {env.start_pos}
            while frontier:
                cx, cy = frontier.popleft()
                if (cx, cy) == env.goal_pos:
                    return env
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nxt = (cx + dx, cy + dy)
                    if env.is_in_bounds(*nxt) and nxt not in seen and nxt not in danger:
                        seen.add(nxt)
                        frontier.append(nxt)
        return env  # fall back to the last attempt even if not fully solvable

    def new_simulation(self):
        self.env = self._generate_solvable_environment()
        self.agent = KBAgent(self.env, inference_method=MODES[self.mode_idx] if MODES[self.mode_idx] != "both" else "dpll")

        self.cell_size = GRID_AREA // max(self.env.width, self.env.height)
        self.grid_px_w = self.cell_size * self.env.width
        self.grid_px_h = self.cell_size * self.env.height
        self.grid_origin = (MARGIN + (GRID_AREA - self.grid_px_w) // 2,
                             MARGIN + (GRID_AREA - self.grid_px_h) // 2)

        self.auto_running = False
        self.game_over = False
        self.outcome = None  # "SUCCESS" / "BLOCKED"

        self.rover_visual = list(self.env.start_pos)
        self.rover_from = list(self.env.start_pos)
        self.rover_to = list(self.env.start_pos)
        self.move_t0 = time.time()
        self.moving = False
        self.heading = (1, 0)

        self.confirmed_unsafe = {}   # (x,y) -> 'hazard'/'radiation'/'obstacle'/'unknown'
        self.pulses = []
        self.particles = []
        self.mission_log = deque(maxlen=9)
        self.last_query_line = "—"
        self.last_compare_line = None
        self.step_flash_t = 0.0

        self.next_action_ready_at = time.time() + 0.3

        self._print_banner()

    def _print_banner(self):
        print()
        print("=" * 78)
        print("  AUTONOMOUS MARS ROVER — PROPOSITIONAL LOGIC AGENT (Pygame GUI)")
        print("=" * 78)
        print(f"  Grid: {self.env.width}x{self.env.height}   Start: {self.env.start_pos}   "
              f"Goal: {self.env.goal_pos}")
        print(f"  Hazards={len(self.env.hazards)}  Radiation={len(self.env.radiations)}  "
              f"Obstacles={len(self.env.obstacles)}   Inference mode: {MODE_LABEL[MODES[self.mode_idx]]}")
        print("-" * 78)
        print("  This terminal is the LIVE KNOWLEDGE-BASE LOG. Keep it visible next to")
        print("  the game window for the split-screen recording.")
        print("=" * 78)

    # ------------------------------------------------------------- layout
    def _layout_buttons(self):
        bx = HUD_X
        bw = HUD_W
        y = 470
        h = 38
        gap = 10
        labels = [
            ("step", "STEP"),
            ("auto", "AUTO RUN"),
            ("mode", "MODE"),
            ("restart", "RESTART"),
        ]
        for i, (key, _label) in enumerate(labels):
            row, col = divmod(i, 2)
            w = (bw - gap) // 2
            rect = pygame.Rect(bx + col * (w + gap), y + row * (h + gap), w, h)
            self.buttons[key] = rect

        speed_y = y + 2 * (h + gap) + 6
        self.buttons["speed_minus"] = pygame.Rect(bx, speed_y, 50, 32)
        self.buttons["speed_plus"] = pygame.Rect(bx + bw - 50, speed_y, 50, 32)

    # ------------------------------------------------------------- events
    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.quit()
        elif ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_SPACE:
                self.try_step()
            elif ev.key == pygame.K_a:
                self.toggle_auto()
            elif ev.key == pygame.K_r:
                self.new_simulation()
            elif ev.key == pygame.K_m:
                self.cycle_mode()
            elif ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self.change_speed(1)
            elif ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.change_speed(-1)
            elif ev.key == pygame.K_k:
                self.dump_full_kb()
            elif ev.key in (pygame.K_ESCAPE, pygame.K_q):
                self.quit()
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            pos = ev.pos
            if self.buttons["step"].collidepoint(pos):
                self.try_step()
            elif self.buttons["auto"].collidepoint(pos):
                self.toggle_auto()
            elif self.buttons["mode"].collidepoint(pos):
                self.cycle_mode()
            elif self.buttons["restart"].collidepoint(pos):
                self.new_simulation()
            elif self.buttons["speed_minus"].collidepoint(pos):
                self.change_speed(-1)
            elif self.buttons["speed_plus"].collidepoint(pos):
                self.change_speed(1)

    def quit(self):
        pygame.quit()
        sys.exit(0)

    def toggle_auto(self):
        if self.game_over:
            return
        self.auto_running = not self.auto_running

    def change_speed(self, direction):
        self.speed_idx = clamp(self.speed_idx + direction, 0, len(SPEED_LEVELS) - 1)

    def cycle_mode(self):
        self.mode_idx = (self.mode_idx + 1) % len(MODES)
        new_mode = MODES[self.mode_idx]
        self.agent.set_inference_method("resolution" if new_mode == "resolution" else "dpll")
        print(f"\n[MODE] Inference mode switched to: {MODE_LABEL[new_mode]}\n")

    def dump_full_kb(self):
        clauses = self.agent.kb.get_clauses()
        print("\n" + "#" * 78)
        print(f"# FULL KNOWLEDGE BASE DUMP — {len(clauses)} CNF clauses (t={self.agent.t})")
        print("#" * 78)
        for i, c in enumerate(clauses, 1):
            print(f"  {i:4d}. {c}")
        print("#" * 78 + "\n")

    # --------------------------------------------------------------- step
    def try_step(self):
        if self.game_over or self.moving:
            return
        self._do_step()

    def _do_step(self):
        prev_pos = (self.agent.x, self.agent.y)
        mode = MODES[self.mode_idx]
        prev_clause_count = len(self.agent.kb.get_clauses())

        target, eval_results, percept, derivation, action_dir = self.agent.step()
        new_clauses = self.agent.kb.get_clauses()[prev_clause_count:]

        new_pos = (self.agent.x, self.agent.y)
        moved = new_pos != prev_pos

        # ---- spawn scan pulses for every neighbor the KB was asked about
        dir_delta = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
        pulse_color = {
            "ALLOWED": ACCENT_GREEN, "UNSAFE": ACCENT_RED,
            "UNKNOWN": ACCENT_GRAY, "VISITED": TEXT_FAINT,
        }
        for direction, status in eval_results.items():
            dx, dy = dir_delta[direction]
            nx, ny = prev_pos[0] + dx, prev_pos[1] + dy
            if not self.env.is_in_bounds(nx, ny):
                continue
            self.pulses.append(ScanPulse(nx, ny, pulse_color.get(status, ACCENT_GRAY), status))
            if status == "UNSAFE":
                kind = "unknown"
                if (nx, ny) in self.env.hazards:
                    kind = "hazard"
                elif (nx, ny) in self.env.radiations:
                    kind = "radiation"
                elif (nx, ny) in self.env.obstacles:
                    kind = "obstacle"
                self.confirmed_unsafe[(nx, ny)] = kind

        # ---- optional cross-validation in "both" mode
        compare_line = None
        if mode == "both" and moved:
            from logic import Symbol
            q = Symbol(f"S_{new_pos[0]}_{new_pos[1]}")
            dpll_r, res_r, agree = self.agent.compare_methods(q)
            compare_line = f"DPLL={'YES' if dpll_r else 'no'}  Resolution={'YES' if res_r else 'no'}  " \
                           f"{'✓ AGREE' if agree else '✗ DISAGREE'}"
            self.last_compare_line = compare_line

        # ---- start rover tween
        if moved:
            self.rover_from = list(prev_pos)
            self.rover_to = list(new_pos)
            self.move_t0 = time.time()
            self.moving = True
            hx = new_pos[0] - prev_pos[0]
            hy = new_pos[1] - prev_pos[1]
            if hx or hy:
                self.heading = (hx, hy)

        # ---- last query line for HUD
        if action_dir not in ("NONE",):
            self.last_query_line = f"Move {action_dir} -> {new_pos}? -> PROVEN SAFE ({MODE_LABEL[mode].split()[0]})"
        else:
            self.last_query_line = "No provably-safe unvisited neighbor remains."

        # ---- mission log ticker (compact)
        summary = f"[{self.agent.t:02d}] {prev_pos}->{new_pos}  act={action_dir:<18s} KB={len(self.agent.kb.get_clauses())}"
        self.mission_log.append(summary)

        # ---- rich professional block to the REAL terminal (the second
        # window in the split-screen recording)
        self._print_step_block(prev_pos, percept, eval_results, derivation, action_dir, new_pos,
                                mode, compare_line, new_clauses)

        self.step_flash_t = time.time()

        # ---- terminal conditions
        if new_pos == self.env.goal_pos:
            self.game_over = True
            self.outcome = "SUCCESS"
            self.auto_running = False
            self._print_mission_complete()
        elif not target and action_dir == "NONE":
            self.game_over = True
            self.outcome = "BLOCKED"
            self.auto_running = False
            self._print_mission_complete()

        self.next_action_ready_at = time.time() + MOVE_DURATION + SPEED_LEVELS[self.speed_idx]

    # ------------------------------------------------------- terminal log
    def _print_step_block(self, prev_pos, percept, eval_results, derivation, action_dir, new_pos,
                           mode, compare_line, new_clauses):
        a = self.agent
        clauses = a.kb.get_clauses()

        print("\n" + "=" * 72)
        print(f"TIME STEP {a.t:02d} | Rover at {prev_pos} | Mode: {MODE_LABEL[mode]}")
        print("-" * 72)
        print(f"PERCEPT  HazardSignal={percept['HazardSignal']}  RadiationSignal={percept['RadiationSignal']}  "
              f"ObstacleSignal={percept['ObstacleSignal']}  Safe={percept['Safe']}")

        if new_clauses:
            print(f"\nNEW SENTENCES ADDED TO KB ({len(new_clauses)}):")
            for c in new_clauses:
                print(f"  • {c}")
        else:
            print("\nNEW SENTENCES ADDED TO KB: (none — fully subsumed by existing knowledge)")

        print(f"\nKNOWLEDGE BASE: {len(clauses)} CNF clauses total   "
              f"(+{a.metrics['kb_updates']} since mission start; press K to dump every clause)")

        if derivation:
            print("\nLOGICAL DERIVATION (why a neighbor was rejected):")
            for rule in derivation:
                parts = rule.split(" -> ")
                print("  " + parts[0])
                for part in parts[1:]:
                    print("    -> " + part)

        print("\nINFERENCE — evaluating each neighbor via ASK(KB, Safe(x,y)):")
        dir_delta = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
        for direction, status in eval_results.items():
            dx, dy = dir_delta[direction]
            cell = (prev_pos[0] + dx, prev_pos[1] + dy)
            print(f"  {direction:<6s} {str(cell):<8s} -> {status}")

        if compare_line:
            print(f"\nCROSS-VALIDATION (Resolution vs DPLL): {compare_line}")

        print(f"\nDECISION: {'Move ' + action_dir + ' -> ' + str(new_pos) if action_dir != 'NONE' else 'HALT — no provably-safe move'}")
        print(f"\nPath so far ({len(a.path)} cells): " + " -> ".join(str(p) for p in a.path))
        print("=" * 72)

    def _print_mission_complete(self):
        a = self.agent
        print("\n" + "=" * 72)
        print("MISSION COMPLETE")
        print("=" * 72)
        print(f"Steps              : {a.metrics['steps']}")
        print(f"Path Cost          : {a.metrics['path_cost']}")
        print(f"Cells Visited      : {len(a.visited)}")
        print(f"Hazards Avoided    : {a.metrics['hazards_avoided']}")
        print(f"Radiation Avoided  : {a.metrics['radiation_avoided']}")
        print(f"Obstacles Avoided  : {a.metrics['obstacles_avoided']}")
        print(f"KB Updates         : {a.metrics['kb_updates']} CNF clauses added")
        print(f"Final KB Size      : {len(a.kb.get_clauses())} clauses")
        print(f"Inferences         : {a.metrics['inferences']} ASK() queries executed")
        print(f"\nSTATUS: {self.outcome}")
        print("=" * 72 + "\n")

    # -------------------------------------------------------------- update
    def update(self, dt):
        now = time.time()

        if self.moving:
            t = clamp((now - self.move_t0) / MOVE_DURATION, 0.0, 1.0)
            te = ease_out_cubic(t)
            self.rover_visual[0] = lerp(self.rover_from[0], self.rover_to[0], te)
            self.rover_visual[1] = lerp(self.rover_from[1], self.rover_to[1], te)

            # thruster particle trail
            if random.random() < 0.6:
                ox, oy = self._cell_center(*self.rover_visual)
                back = (-self.heading[0], -self.heading[1])
                vx = back[0] * 40 + random.uniform(-12, 12)
                vy = back[1] * 40 + random.uniform(-12, 12)
                self.particles.append(Particle(ox, oy, vx, vy, ROVER_GLOW, life=0.45))

            if t >= 1.0:
                self.moving = False
                self.rover_visual = list(self.rover_to)

        self.particles = [p for p in self.particles if not p.done()]
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt

        self.pulses = [p for p in self.pulses if not p.done()]

        if self.auto_running and not self.game_over and not self.moving:
            if now >= self.next_action_ready_at:
                self._do_step()

    # -------------------------------------------------------------- drawing
    def _cell_rect(self, gx, gy):
        ox, oy = self.grid_origin
        return pygame.Rect(ox + gx * self.cell_size, oy + gy * self.cell_size,
                            self.cell_size, self.cell_size)

    def _cell_center(self, gx, gy):
        ox, oy = self.grid_origin
        return (ox + (gx + 0.5) * self.cell_size, oy + (gy + 0.5) * self.cell_size)

    def draw(self):
        self.screen.fill(BG)
        self._draw_starfield()
        self._draw_grid_panel()
        self._draw_hud()
        if self.game_over:
            self._draw_end_overlay()
        pygame.display.flip()

    def _draw_starfield(self):
        rnd = random.Random(1234)
        for _ in range(70):
            x = rnd.randint(0, WINDOW_W)
            y = rnd.randint(0, MARGIN)
            pygame.draw.circle(self.screen, (50, 55, 70), (x, y), 1)

    def _draw_grid_panel(self):
        panel = pygame.Rect(MARGIN - 6, MARGIN - 6, GRID_AREA + 12, GRID_AREA + 12)
        pygame.draw.rect(self.screen, PANEL_BG, panel, border_radius=10)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel, width=2, border_radius=10)

        ox, oy = self.grid_origin
        grid_rect = pygame.Rect(ox, oy, self.grid_px_w, self.grid_px_h)
        pygame.draw.rect(self.screen, GRID_BG, grid_rect)

        for gy in range(self.env.height):
            for gx in range(self.env.width):
                self._draw_cell(gx, gy)

        for gx in range(self.env.width + 1):
            x = ox + gx * self.cell_size
            pygame.draw.line(self.screen, GRID_LINE, (x, oy), (x, oy + self.grid_px_h))
        for gy in range(self.env.height + 1):
            y = oy + gy * self.cell_size
            pygame.draw.line(self.screen, GRID_LINE, (ox, y), (ox + self.grid_px_w, y))

        for pulse in self.pulses:
            self._draw_pulse(pulse)

        self._draw_rover()

        for p in self.particles:
            age_ratio = clamp(1 - (p.age() / p.life), 0.0, 1.0)
            r = max(1, int(3 * age_ratio))
            alpha_color = tuple(clamp(int(c * age_ratio), 0, 255) for c in p.color)
            pygame.draw.circle(self.screen, alpha_color, (int(p.x), int(p.y)), r)

    def _cell_state(self, gx, gy):
        pos = (gx, gy)
        a = self.agent
        if pos == self.env.start_pos:
            return "start"
        if pos == self.env.goal_pos and pos not in a.visited:
            return "goal"
        if pos in a.visited:
            if pos in self.env.hazards:
                return "hazard"
            if pos in self.env.radiations:
                return "radiation"
            if pos in self.env.obstacles:
                return "obstacle"
            return "visited_safe"
        if pos in self.confirmed_unsafe:
            return self.confirmed_unsafe[pos]
        if pos in a.safe_unvisited:
            return "known_safe"
        return "unknown"

    def _draw_cell(self, gx, gy):
        rect = self._cell_rect(gx, gy)
        state = self._cell_state(gx, gy)
        t = time.time()
        pulse = (math.sin(t * 3.0) + 1) / 2  # 0..1

        color = C_UNKNOWN
        if state == "unknown":
            shade = C_UNKNOWN if (gx + gy) % 2 == 0 else C_UNKNOWN_STATIC
            pygame.draw.rect(self.screen, shade, rect)
            q = self.font_small.render("?", True, (55, 52, 66))
            self.screen.blit(q, q.get_rect(center=rect.center))
            return
        elif state == "known_safe":
            color = C_KNOWN_SAFE_UNVISITED
        elif state == "visited_safe":
            color = C_VISITED_SAFE
        elif state == "start":
            color = C_START
        elif state == "goal":
            color = C_GOAL
        elif state == "hazard":
            color = C_HAZARD
        elif state == "radiation":
            color = C_RADIATION
        elif state == "obstacle":
            color = C_OBSTACLE

        pygame.draw.rect(self.screen, color, rect)

        if state == "goal":
            glow_r = int(self.cell_size * (0.28 + 0.06 * pulse))
            self._glow_circle(rect.center, glow_r, ACCENT_GOLD, 70)
            self._draw_flag(rect, ACCENT_GOLD)
        elif state == "start":
            self._draw_flag(rect, ACCENT_CYAN)
        elif state == "visited_safe":
            self._draw_check(rect)
        elif state == "known_safe":
            glow_r = int(self.cell_size * (0.22 + 0.05 * pulse))
            self._glow_circle(rect.center, glow_r, ACCENT_GREEN, 45)
        elif state == "hazard":
            glow_r = int(self.cell_size * (0.32 + 0.08 * pulse))
            self._glow_circle(rect.center, glow_r, ACCENT_RED, 60)
            self._draw_warning_triangle(rect)
        elif state == "radiation":
            glow_r = int(self.cell_size * (0.32 + 0.08 * pulse))
            self._glow_circle(rect.center, glow_r, ACCENT_GOLD, 55)
            self._draw_radiation_icon(rect)
        elif state == "obstacle":
            self._draw_rock(rect)

    def _glow_circle(self, center, radius, color, alpha):
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*color, alpha), (radius, radius), radius)
        self.screen.blit(surf, (center[0] - radius, center[1] - radius))

    def _draw_flag(self, rect, color):
        cx, cy = rect.center
        pole_bottom = (cx - rect.w * 0.12, rect.bottom - rect.h * 0.18)
        pole_top = (cx - rect.w * 0.12, rect.top + rect.h * 0.18)
        pygame.draw.line(self.screen, TEXT, pole_bottom, pole_top, 2)
        flag_pts = [pole_top, (pole_top[0] + rect.w * 0.3, pole_top[1] + rect.h * 0.1),
                    (pole_top[0], pole_top[1] + rect.h * 0.22)]
        pygame.draw.polygon(self.screen, color, flag_pts)

    def _draw_check(self, rect):
        cx, cy = rect.center
        w, h = rect.w, rect.h
        p1 = (cx - w * 0.18, cy)
        p2 = (cx - w * 0.03, cy + h * 0.14)
        p3 = (cx + w * 0.20, cy - h * 0.16)
        pygame.draw.lines(self.screen, (210, 245, 220), False, [p1, p2, p3], 3)

    def _draw_warning_triangle(self, rect):
        cx, cy = rect.center
        w, h = rect.w, rect.h
        pts = [(cx, cy - h * 0.26), (cx - w * 0.24, cy + h * 0.2), (cx + w * 0.24, cy + h * 0.2)]
        pygame.draw.polygon(self.screen, (30, 10, 10), pts)
        pygame.draw.polygon(self.screen, (255, 210, 90), pts, 2)
        excl = self.font_cell.render("!", True, (255, 210, 90))
        self.screen.blit(excl, excl.get_rect(center=(cx, cy + h * 0.04)))

    def _draw_radiation_icon(self, rect):
        cx, cy = rect.center
        r_out = rect.w * 0.26
        r_in = rect.w * 0.08
        pygame.draw.circle(self.screen, (40, 30, 5), (cx, cy), r_out)
        for i in range(3):
            ang = math.radians(90 + i * 120 + time.time() * 25)
            pts = []
            for spread in (-24, 24):
                a2 = ang + math.radians(spread)
                pts.append((cx + math.cos(a2) * r_in, cy + math.sin(a2) * r_in))
                a3 = ang + math.radians(spread * 0.4)
                pts.append((cx + math.cos(a3) * r_out, cy + math.sin(a3) * r_out))
            pygame.draw.polygon(self.screen, (255, 224, 90), pts)
        pygame.draw.circle(self.screen, (20, 15, 2), (cx, cy), r_in)

    def _draw_rock(self, rect):
        cx, cy = rect.center
        rnd = random.Random(hash((rect.x, rect.y)) & 0xFFFF)
        pts = []
        n = 7
        for i in range(n):
            ang = (2 * math.pi * i) / n
            rad = rect.w * (0.16 + 0.08 * rnd.random())
            pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad * 0.85))
        pygame.draw.polygon(self.screen, (110, 92, 76), pts)
        pygame.draw.polygon(self.screen, (60, 48, 38), pts, 2)

    def _draw_pulse(self, pulse):
        age = pulse.age()
        t = clamp(age / SCAN_DURATION, 0, 1)
        cx, cy = self._cell_center(pulse.gx, pulse.gy)
        max_r = self.cell_size * 0.55
        r = int(6 + max_r * t)
        alpha = int(220 * (1 - t))
        if alpha <= 0:
            return
        surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*pulse.color, alpha), (r + 2, r + 2), r, width=3)
        self.screen.blit(surf, (cx - r - 2, cy - r - 2))

    def _draw_rover(self):
        cx, cy = self._cell_center(*self.rover_visual)
        radius = self.cell_size * 0.30
        bob = math.sin(time.time() * 6) * 2

        self._glow_circle((cx, cy + bob), int(radius * 1.8), ROVER_GLOW, 60)
        if HAVE_GFX:
            gfx.filled_circle(self.screen, int(cx), int(cy + bob), int(radius), ROVER_COLOR)
            gfx.aacircle(self.screen, int(cx), int(cy + bob), int(radius), (255, 255, 255))
        else:
            pygame.draw.circle(self.screen, ROVER_COLOR, (int(cx), int(cy + bob)), int(radius))
            pygame.draw.circle(self.screen, (255, 255, 255), (int(cx), int(cy + bob)), int(radius), 1)

        hx, hy = self.heading
        norm = math.hypot(hx, hy) or 1
        hx, hy = hx / norm, hy / norm
        tip = (cx + hx * radius * 0.85, cy + bob + hy * radius * 0.85)
        pygame.draw.circle(self.screen, (20, 30, 40), (int(tip[0]), int(tip[1])), 3)

    # ---------------------------------------------------------------- HUD
    def _draw_hud(self):
        panel = pygame.Rect(HUD_X - MARGIN, MARGIN - 6, HUD_W + MARGIN, WINDOW_H - 2 * MARGIN + 12)
        pygame.draw.rect(self.screen, PANEL_BG, panel, border_radius=10)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel, width=2, border_radius=10)

        x = HUD_X
        y = MARGIN + 10

        title = self.font_title.render("MARS ROVER", True, ACCENT_CYAN)
        self.screen.blit(title, (x, y))
        y += 30
        sub = self.font_small.render("Propositional Logic Agent", True, TEXT_DIM)
        self.screen.blit(sub, (x, y))
        y += 30

        a = self.agent
        flash = max(0.0, 1 - (time.time() - self.step_flash_t) / 0.4)
        step_color = tuple(int(lerp(TEXT[i], ACCENT_CYAN[i], flash)) for i in range(3))
        self._hud_line(f"STEP {a.t:03d}", x, y, self.font_med, step_color)
        y += 26
        self._hud_line(f"Position: {(a.x, a.y)}    Goal: {self.env.goal_pos}", x, y, self.font_small, TEXT_DIM)
        y += 22
        self._hud_line(f"Mode: {MODE_LABEL[MODES[self.mode_idx]]}", x, y, self.font_small, ACCENT_GOLD)
        y += 28

        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x + HUD_W, y))
        y += 12

        stats = [
            ("Cells Visited", len(a.visited)),
            ("Path Cost", a.metrics["path_cost"]),
            ("Hazards Avoided", a.metrics["hazards_avoided"]),
            ("Radiation Avoided", a.metrics["radiation_avoided"]),
            ("Obstacles Avoided", a.metrics["obstacles_avoided"]),
            ("Inferences (ASK calls)", a.metrics["inferences"]),
        ]
        for label, val in stats:
            row = self.font_small.render(f"{label:<22s}", True, TEXT_DIM)
            self.screen.blit(row, (x, y))
            vtxt = self.font_small_b.render(str(val), True, TEXT)
            self.screen.blit(vtxt, (x + HUD_W - vtxt.get_width(), y))
            y += 20

        y += 8
        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x + HUD_W, y))
        y += 12

        kb_label = self.font_small.render(f"Knowledge Base: {len(a.kb.get_clauses()):d} clauses", True, TEXT)
        self.screen.blit(kb_label, (x, y))
        y += 20
        self._draw_sparkline(x, y, HUD_W, 46, a.metrics["kb_size_history"])
        y += 58

        pygame.draw.line(self.screen, PANEL_BORDER, (x, y), (x + HUD_W, y))
        y += 10
        q_label = self.font_small.render("LAST INFERENCE:", True, TEXT_DIM)
        self.screen.blit(q_label, (x, y))
        y += 18
        self._wrapped_text(self.last_query_line, x, y, HUD_W, self.font_small, ACCENT_GREEN)
        y += 20
        if self.last_compare_line:
            self._wrapped_text(self.last_compare_line, x, y, HUD_W, self.font_small, ACCENT_CYAN)
            y += 20

        # Buttons
        self._draw_buttons()

        # mission log ticker
        log_y = 610
        pygame.draw.line(self.screen, PANEL_BORDER, (x, log_y - 6), (x + HUD_W, log_y - 6))
        log_title = self.font_small.render("MISSION LOG", True, TEXT_DIM)
        self.screen.blit(log_title, (x, log_y))
        ly = log_y + 20
        for line in self.mission_log:
            txt = self.font_tiny.render(line[:60], True, ACCENT_GRAY)
            self.screen.blit(txt, (x, ly))
            ly += 16

        hint = self.font_tiny.render("SPACE step  A auto  M mode  R restart  K dump full KB", True, TEXT_FAINT)
        self.screen.blit(hint, (x, WINDOW_H - MARGIN - 18))

    def _hud_line(self, text, x, y, font, color):
        surf = font.render(text, True, color)
        self.screen.blit(surf, (x, y))

    def _wrapped_text(self, text, x, y, max_w, font, color):
        words = text.split(" ")
        line = ""
        for w in words:
            trial = (line + " " + w).strip()
            if font.size(trial)[0] > max_w and line:
                surf = font.render(line, True, color)
                self.screen.blit(surf, (x, y))
                y += font.get_height() + 2
                line = w
            else:
                line = trial
        if line:
            surf = font.render(line, True, color)
            self.screen.blit(surf, (x, y))

    def _draw_sparkline(self, x, y, w, h, values):
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, GRID_BG, rect, border_radius=4)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, width=1, border_radius=4)
        if len(values) < 2:
            return
        vmin, vmax = min(values), max(values)
        span = max(1, vmax - vmin)
        pts = []
        n = len(values)
        for i, v in enumerate(values):
            px = x + (i / (n - 1)) * (w - 6) + 3
            py = y + h - 4 - ((v - vmin) / span) * (h - 8)
            pts.append((px, py))
        if len(pts) >= 2:
            pygame.draw.lines(self.screen, ACCENT_GREEN, False, pts, 2)
        pygame.draw.circle(self.screen, ACCENT_GREEN, (int(pts[-1][0]), int(pts[-1][1])), 3)

    def _draw_buttons(self):
        mouse = pygame.mouse.get_pos()

        def button(rect, label, active=False, enabled=True):
            hovered = rect.collidepoint(mouse) and enabled
            base = ACCENT_CYAN if active else PANEL_BORDER
            fill = (28, 60, 70) if active else ((26, 30, 42) if not hovered else (34, 40, 56))
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            pygame.draw.rect(self.screen, base if enabled else TEXT_FAINT, rect, width=2, border_radius=6)
            color = TEXT if enabled else TEXT_FAINT
            txt = self.font_small_b.render(label, True, color)
            self.screen.blit(txt, txt.get_rect(center=rect.center))

        button(self.buttons["step"], "STEP", enabled=not self.auto_running and not self.game_over)
        button(self.buttons["auto"], "PAUSE" if self.auto_running else "AUTO RUN",
               active=self.auto_running, enabled=not self.game_over)
        button(self.buttons["mode"], MODES[self.mode_idx].upper())
        button(self.buttons["restart"], "RESTART")
        button(self.buttons["speed_minus"], "-")
        button(self.buttons["speed_plus"], "+")

        sx = self.buttons["speed_minus"].right + 10
        sy = self.buttons["speed_minus"].y + 6
        speed_txt = self.font_small.render(f"Speed: {self.speed_idx + 1}/{len(SPEED_LEVELS)}", True, TEXT_DIM)
        self.screen.blit(speed_txt, (sx, sy))

    def _draw_end_overlay(self):
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((5, 6, 10, 190))
        self.screen.blit(overlay, (0, 0))

        success = self.outcome == "SUCCESS"
        title_color = ACCENT_GREEN if success else ACCENT_RED
        title_text = "MISSION SUCCESS" if success else "MISSION BLOCKED"

        box = pygame.Rect(0, 0, 560, 380)
        box.center = (WINDOW_W // 2, WINDOW_H // 2)
        pygame.draw.rect(self.screen, PANEL_BG, box, border_radius=14)
        pygame.draw.rect(self.screen, title_color, box, width=3, border_radius=14)

        title = self.font_huge.render(title_text, True, title_color)
        self.screen.blit(title, title.get_rect(center=(box.centerx, box.top + 55)))

        a = self.agent
        lines = [
            f"Steps taken        : {a.metrics['steps']}",
            f"Path cost          : {a.metrics['path_cost']}",
            f"Cells visited      : {len(a.visited)}",
            f"Hazards avoided    : {a.metrics['hazards_avoided']}",
            f"Radiation avoided  : {a.metrics['radiation_avoided']}",
            f"Obstacles avoided  : {a.metrics['obstacles_avoided']}",
            f"Final KB size      : {len(a.kb.get_clauses())} clauses",
            f"Inference queries  : {a.metrics['inferences']}",
        ]
        ly = box.top + 110
        for line in lines:
            surf = self.font_small.render(line, True, TEXT)
            self.screen.blit(surf, (box.centerx - 150, ly))
            ly += 24

        hint = self.font_small_b.render("Press R to restart", True, TEXT_DIM)
        self.screen.blit(hint, hint.get_rect(center=(box.centerx, box.bottom - 28)))

    # ----------------------------------------------------------------- run
    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for ev in pygame.event.get():
                self.handle_event(ev)
            self.update(dt)
            self.draw()


def main():
    game = RoverGame()
    game.run()


if __name__ == "__main__":
    main()
